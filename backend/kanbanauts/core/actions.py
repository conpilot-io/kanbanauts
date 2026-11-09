"""Action registry — modular column behaviors."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

from kanbanauts.core.config import (
    Action,
    CancelAction,
    CommentAction,
    KanbanautsConfig,
    LabelAction,
    MoveToAction,
    RunAction,
)
from kanbanauts.core.state import (
    AgentState,
    labels_to_add,
    labels_to_remove,
    parse_run_name,
    run_name,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TicketContext:
    owner: str
    repo: str
    issue_number: int
    installation_id: int
    item_node_id: str | None = None
    labels: set[str] | None = None
    default_branch: str = "main"
    project_id: str | None = None
    status_field_id: str | None = None
    status_options: dict[str, str] | None = None  # name.casefold() -> option id
    to_column: str | None = None
    from_column: str | None = None
    # How the run was started: "board" (column move) or "command" (issue comment).
    source: str = "board"


class GitHubGateway(Protocol):
    async def installation_token(
        self,
        installation_id: int,
        *,
        repositories: list[str] | None = None,
        permissions: dict[str, str] | None = None,
    ) -> str: ...

    async def list_issue_labels(
        self, token: str, owner: str, repo: str, issue_number: int
    ) -> set[str]: ...

    async def set_issue_state_label(
        self,
        token: str,
        owner: str,
        repo: str,
        issue_number: int,
        *,
        remove: list[str],
        add: list[str],
    ) -> None: ...

    async def add_issue_comment(
        self, token: str, owner: str, repo: str, issue_number: int, body: str
    ) -> Any: ...

    async def dispatch_workflow(
        self,
        token: str,
        owner: str,
        repo: str,
        workflow_id: str,
        *,
        ref: str,
        inputs: dict[str, Any],
    ) -> None: ...

    async def list_workflow_runs(
        self,
        token: str,
        owner: str,
        repo: str,
        *,
        status: str | None = None,
        per_page: int = 50,
    ) -> list[dict[str, Any]]: ...

    async def cancel_workflow_run(
        self, token: str, owner: str, repo: str, run_id: int
    ) -> None: ...

    async def graphql(
        self, token: str, query: str, variables: dict[str, Any] | None = None
    ) -> Any: ...

    async def get_repository(self, token: str, owner: str, repo: str) -> dict[str, Any]: ...


@dataclass(slots=True)
class ActionRunner:
    github: GitHubGateway
    config: KanbanautsConfig

    async def _token(self, ctx: TicketContext) -> str:
        return await self.github.installation_token(ctx.installation_id)

    async def ensure_labels(self, ctx: TicketContext, token: str) -> set[str]:
        if ctx.labels is None:
            ctx.labels = await self.github.list_issue_labels(
                token, ctx.owner, ctx.repo, ctx.issue_number
            )
        return ctx.labels

    async def set_state(self, ctx: TicketContext, token: str, state: AgentState | None) -> None:
        labels = await self.ensure_labels(ctx, token)
        remove = labels_to_remove(labels, state)
        add = labels_to_add(labels, state) if state is not None else []
        if remove or add:
            await self.github.set_issue_state_label(
                token,
                ctx.owner,
                ctx.repo,
                ctx.issue_number,
                remove=remove,
                add=add,
            )
            for label in remove:
                labels.discard(label)
            for label in add:
                labels.add(label)

    async def run_actions(self, ctx: TicketContext, actions: list[Action]) -> None:
        for action in actions:
            await self.run_one(ctx, action)

    async def run_one(self, ctx: TicketContext, action: Action | None) -> None:
        if action is None:
            return
        if isinstance(action, RunAction):
            await self._run_phase(ctx, action.run)
        elif isinstance(action, CancelAction):
            if action.cancel:
                await self._cancel(ctx)
        elif isinstance(action, MoveToAction):
            await self._move_to(ctx, action.move_to)
        elif isinstance(action, LabelAction):
            token = await self._token(ctx)
            await self.github.set_issue_state_label(
                token,
                ctx.owner,
                ctx.repo,
                ctx.issue_number,
                remove=[],
                add=[action.label],
            )
        elif isinstance(action, CommentAction):
            token = await self._token(ctx)
            await self.github.add_issue_comment(
                token, ctx.owner, ctx.repo, ctx.issue_number, action.comment
            )
        else:
            raise TypeError(f"Unsupported action: {type(action)}")

    async def _run_phase(self, ctx: TicketContext, phase: str) -> None:
        phase_cfg = self.config.phase_for_run(phase)
        if phase_cfg is None:
            raise ValueError(f"Unknown phase '{phase}' in kanbanauts.yml")
        token = await self._token(ctx)
        await self.set_state(ctx, token, AgentState.QUEUED)
        repo = await self.github.get_repository(token, ctx.owner, ctx.repo)
        ref = str(repo.get("default_branch") or ctx.default_branch)
        source = ctx.source if ctx.source in ("board", "command") else "board"
        await self.github.dispatch_workflow(
            token,
            ctx.owner,
            ctx.repo,
            phase_cfg.workflow,
            ref=ref,
            inputs={
                "issue_number": str(ctx.issue_number),
                "phase": phase,
                "source": source,
            },
        )
        logger.info(
            "Dispatched %s for %s/%s#%s source=%s",
            phase_cfg.workflow,
            ctx.owner,
            ctx.repo,
            ctx.issue_number,
            source,
        )

    async def _cancel(self, ctx: TicketContext) -> None:
        token = await self._token(ctx)
        cancelled: list[dict[str, Any]] = []
        seen: set[int] = set()
        for status in ("queued", "in_progress", "waiting", "pending"):
            runs = await self.github.list_workflow_runs(
                token, ctx.owner, ctx.repo, status=status
            )
            for run in runs:
                name = str(run.get("display_title") or run.get("name") or "")
                parsed = parse_run_name(name)
                if parsed is None:
                    parsed = parse_run_name(str(run.get("name") or ""))
                if parsed is None:
                    continue
                _phase, issue = parsed
                if issue != ctx.issue_number:
                    continue
                run_id = int(run["id"])
                if run_id in seen:
                    continue
                seen.add(run_id)
                await self.github.cancel_workflow_run(token, ctx.owner, ctx.repo, run_id)
                cancelled.append(run)

        await self.set_state(ctx, token, None)
        dest = ctx.to_column or "another column"
        links = []
        for run in cancelled:
            html = run.get("html_url")
            if html:
                links.append(f"- {html}")
        body = f"Stopped: moved to **{dest}**."
        if links:
            body += "\n\nCancelled runs:\n" + "\n".join(links)
        await self.github.add_issue_comment(
            token, ctx.owner, ctx.repo, ctx.issue_number, body
        )

    async def _move_to(self, ctx: TicketContext, column: str) -> None:
        if not ctx.project_id or not ctx.status_field_id or not ctx.item_node_id:
            raise ValueError("Project context incomplete for move_to")
        options = ctx.status_options or {}
        option_id = options.get(column.casefold())
        if option_id is None:
            raise ValueError(f"Unknown Status option '{column}'")
        token = await self._token(ctx)
        from kanbanauts.core.github_app import UPDATE_ITEM_STATUS_MUTATION

        await self.github.graphql(
            token,
            UPDATE_ITEM_STATUS_MUTATION,
            {
                "projectId": ctx.project_id,
                "itemId": ctx.item_node_id,
                "fieldId": ctx.status_field_id,
                "optionId": option_id,
            },
        )

    async def find_active_runs(
        self, ctx: TicketContext, phase: str | None = None
    ) -> list[dict[str, Any]]:
        token = await self._token(ctx)
        found: list[dict[str, Any]] = []
        for status in ("queued", "in_progress", "waiting", "pending"):
            runs = await self.github.list_workflow_runs(
                token, ctx.owner, ctx.repo, status=status
            )
            for run in runs:
                for candidate in (
                    str(run.get("display_title") or ""),
                    str(run.get("name") or ""),
                ):
                    parsed = parse_run_name(candidate)
                    if parsed is None:
                        continue
                    run_phase, issue = parsed
                    if issue != ctx.issue_number:
                        continue
                    if phase is not None and run_phase != phase:
                        continue
                    found.append(run)
                    break
        return found

    def expected_run_name(self, phase: str, issue_number: int) -> str:
        return run_name(phase, issue_number)
