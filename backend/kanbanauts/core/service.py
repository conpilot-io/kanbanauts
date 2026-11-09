"""Kanbanauts application service — webhook handlers + HTTP API."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from kanbanauts.core.actions import ActionRunner, TicketContext
from kanbanauts.core.broker import BROKER_PERMISSIONS, OidcError, TokenBroker
from kanbanauts.core.commands import (
    HELP_TEXT,
    CommandName,
    command_prefixes_for_config,
    has_write_permission,
    parse_command,
    phase_for_command,
)
from kanbanauts.core.config import KanbanautsConfig, load_config_yaml
from kanbanauts.core.filters import filter_ticket, validate_column_names
from kanbanauts.core.github_app import (
    ITEM_WITH_CONTENT_QUERY,
    PROJECT_STATUS_FIELD_QUERY,
    GitHubApp,
)
from kanbanauts.core.ports import HttpRequest, HttpResponse
from kanbanauts.core.state import AgentState, current_state, is_active, parse_run_name
from kanbanauts.core.webhook import WebhookRouter

logger = logging.getLogger(__name__)

CONFIG_PATH = ".github/kanbanauts.yml"


@dataclass(slots=True)
class Settings:
    app_id: str
    private_key_pem: str
    webhook_secret: str
    oidc_audience: str  # e.g. https://kanbanauts.example.com


@dataclass(slots=True)
class KanbanautsService:
    settings: Settings
    github: GitHubApp
    broker: TokenBroker

    @classmethod
    def create(cls, settings: Settings, github: GitHubApp | None = None) -> KanbanautsService:
        app = github or GitHubApp(app_id=settings.app_id, private_key_pem=settings.private_key_pem)
        broker = TokenBroker(expected_audience=settings.oidc_audience)
        return cls(settings=settings, github=app, broker=broker)

    def webhook_router(self) -> WebhookRouter:
        return WebhookRouter(
            secret=self.settings.webhook_secret,
            handlers={
                "projects_v2_item": self.handle_projects_v2_item,
                "issue_comment": self.handle_issue_comment,
                "pull_request_review": self.handle_pull_request_review,
                "workflow_run": self.handle_workflow_run,
                "installation": self.handle_installation,
                "installation_repositories": self.handle_installation,
            },
        )

    async def handle_http(self, request: HttpRequest) -> HttpResponse:
        path = request.path.rstrip("/") or "/"
        if request.method == "POST" and path.endswith("/webhook"):
            return await self.webhook_router().handle(request)
        if request.method == "POST" and path.endswith("/token"):
            return await self.handle_token(request)
        if request.method == "POST" and path.endswith("/report"):
            return await self.handle_report(request)
        if request.method == "GET" and path.endswith("/preflight"):
            return await self.handle_preflight(request)
        if request.method == "POST" and path.endswith("/admin/rollout"):
            return await self.handle_rollout(request)
        if request.method == "GET" and path in ("/", "/health", "/api/health"):
            return HttpResponse.json(200, {"ok": True, "service": "kanbanauts"})
        return HttpResponse.text(404, "not found")

    # ------------------------------------------------------------------
    # Config helpers
    # ------------------------------------------------------------------

    async def load_config(
        self, token: str, owner: str, repo: str, *, ref: str | None = None
    ) -> KanbanautsConfig | None:
        text = await self.github.get_repo_file(token, owner, repo, CONFIG_PATH, ref=ref)
        if text is None:
            return None
        return load_config_yaml(text)

    async def project_field_context(
        self, token: str, config: KanbanautsConfig
    ) -> tuple[str, str, dict[str, str], set[str]]:
        """Return (project_id, field_id, options_by_name_folded, option_names)."""
        data = await self.github.graphql(
            token,
            PROJECT_STATUS_FIELD_QUERY,
            {"owner": config.project_owner, "number": config.project_number},
        )
        project = data["organization"]["projectV2"]
        project_id = str(project["id"])
        field_id = ""
        options: dict[str, str] = {}
        names: set[str] = set()
        for node in project["fields"]["nodes"]:
            if not isinstance(node, dict):
                continue
            if node.get("name") != config.status_field:
                continue
            field_id = str(node["id"])
            for opt in node.get("options") or []:
                names.add(str(opt["name"]))
                options[str(opt["name"]).casefold()] = str(opt["id"])
            break
        if not field_id:
            raise ValueError(f"Status field {config.status_field!r} not found on project")
        return project_id, field_id, options, names

    # ------------------------------------------------------------------
    # projects_v2_item
    # ------------------------------------------------------------------

    async def handle_projects_v2_item(
        self, event: str, payload: dict[str, Any], headers: Mapping[str, str]
    ) -> HttpResponse:
        action = payload.get("action")
        if action != "edited":
            return HttpResponse.json(200, {"ok": True, "ignored": action})

        changes = payload.get("changes") or {}
        field_value = changes.get("field_value") or {}
        if field_value.get("field_type") != "single_select":
            return HttpResponse.json(200, {"ok": True, "ignored": "not_single_select"})

        from_obj = field_value.get("from")
        to_obj = field_value.get("to")
        from_name = from_obj.get("name") if isinstance(from_obj, dict) else None
        to_name = to_obj.get("name") if isinstance(to_obj, dict) else None
        if not to_name:
            return HttpResponse.json(200, {"ok": True, "ignored": "no_to"})

        project_number = int(field_value.get("project_number") or 0)
        org = (payload.get("organization") or {}).get("login") or ""
        installation_id = int((payload.get("installation") or {}).get("id") or 0)
        item = payload.get("projects_v2_item") or {}
        item_node_id = str(item.get("node_id") or "")

        if not installation_id or not item_node_id or not org:
            return HttpResponse.json(200, {"ok": True, "ignored": "incomplete"})

        token = await self.github.installation_token(installation_id)
        content = await self._resolve_item_content(token, item_node_id)
        if content is None:
            return HttpResponse.json(200, {"ok": True, "ignored": "draft_or_no_issue"})

        owner, repo, issue_number = content
        config = await self.load_config(token, owner, repo)
        if config is None:
            return HttpResponse.json(200, {"ok": True, "ignored": "no_config"})
        if not config.has_project:
            return HttpResponse.json(200, {"ok": True, "ignored": "no_project"})

        if field_value.get("field_name") and field_value["field_name"] != config.status_field:
            # Only react to the configured status field.
            if field_value["field_name"].casefold() != config.status_field.casefold():
                return HttpResponse.json(200, {"ok": True, "ignored": "wrong_field"})

        labels = await self.github.list_issue_labels(token, owner, repo, issue_number)
        filt = filter_ticket(
            config,
            labels=labels,
            has_issue=True,
            project_owner=org,
            project_number=project_number,
        )
        if not filt.allow:
            return HttpResponse.json(200, {"ok": True, "ignored": filt.reason})

        try:
            project_id, field_id, options, option_names = await self.project_field_context(
                token, config
            )
        except ValueError as exc:
            await self.github.add_issue_comment(
                token, owner, repo, issue_number, f"Kanbanauts config error: {exc}"
            )
            return HttpResponse.json(200, {"ok": False, "error": str(exc)})

        missing = validate_column_names(config, option_names)
        if missing:
            msg = (
                "Kanbanauts config error: these columns are not options on "
                f"`{config.status_field}`: {', '.join(missing)}. "
                "Fix `.github/kanbanauts.yml` or the Project field."
            )
            await self.github.add_issue_comment(token, owner, repo, issue_number, msg)
            return HttpResponse.json(200, {"ok": False, "error": "bad_columns"})

        ctx = TicketContext(
            owner=owner,
            repo=repo,
            issue_number=issue_number,
            installation_id=installation_id,
            item_node_id=item_node_id,
            labels=labels,
            project_id=project_id,
            status_field_id=field_id,
            status_options=options,
            from_column=from_name,
            to_column=to_name,
        )
        runner = ActionRunner(github=self.github, config=config)

        # on_leave for the previous column
        if from_name:
            from_cfg = config.column(from_name)
            if from_cfg and from_cfg.on_leave:
                await runner.run_actions(ctx, from_cfg.on_leave)

        # on_enter for the new column
        to_cfg = config.column(to_name)
        if to_cfg is None:
            return HttpResponse.json(200, {"ok": True, "ignored": "unconfigured_column"})
        if to_cfg.on_enter:
            await runner.run_actions(ctx, to_cfg.on_enter)

        return HttpResponse.json(
            200,
            {"ok": True, "from": from_name, "to": to_name, "issue": issue_number},
        )

    async def _resolve_item_content(
        self, token: str, item_node_id: str
    ) -> tuple[str, str, int] | None:
        data = await self.github.graphql(token, ITEM_WITH_CONTENT_QUERY, {"id": item_node_id})
        node = data.get("node") or {}
        content = node.get("content")
        if not content or content.get("__typename") not in ("Issue", "PullRequest"):
            return None
        repo = content["repository"]
        owner = str(repo["owner"]["login"])
        name = str(repo["name"])
        number = int(content["number"])
        return owner, name, number

    # ------------------------------------------------------------------
    # issue_comment
    # ------------------------------------------------------------------

    async def handle_issue_comment(
        self, event: str, payload: dict[str, Any], headers: Mapping[str, str]
    ) -> HttpResponse:
        if payload.get("action") != "created":
            return HttpResponse.json(200, {"ok": True, "ignored": "not_created"})

        comment = payload.get("comment") or {}
        comment_user = comment.get("user") or {}
        # Ignore bot comments to avoid loops when agent output looks like a command.
        if str(comment_user.get("type") or "").casefold() == "bot":
            return HttpResponse.json(200, {"ok": True, "ignored": "bot"})

        body = str(comment.get("body") or "")
        installation_id = int((payload.get("installation") or {}).get("id") or 0)
        repo_obj = payload.get("repository") or {}
        owner = str((repo_obj.get("owner") or {}).get("login") or "")
        repo = str(repo_obj.get("name") or "")
        issue = payload.get("issue") or {}
        issue_number = int(issue.get("number") or 0)
        user = str(comment_user.get("login") or "")
        is_pr = bool(issue.get("pull_request"))
        comment_id = int(comment.get("id") or 0)

        if not all([installation_id, owner, repo, issue_number, user]):
            return HttpResponse.json(200, {"ok": True, "ignored": "incomplete"})

        token = await self.github.installation_token(installation_id)
        config = await self.load_config(token, owner, repo)
        if config is None:
            return HttpResponse.json(200, {"ok": True, "ignored": "no_config"})

        prefixes = command_prefixes_for_config(config.command_prefix)
        parsed = parse_command(body, prefixes=prefixes)
        if parsed is None:
            return HttpResponse.json(200, {"ok": True, "ignored": "no_command"})

        perm = await self.github.collaborator_permission(token, owner, repo, user)
        if not has_write_permission(perm):
            await self.github.add_issue_comment(
                token,
                owner,
                repo,
                issue_number,
                f"@{user} you need write access to run Kanbanauts commands.",
            )
            return HttpResponse.json(200, {"ok": False, "error": "forbidden"})

        if comment_id:
            try:
                await self.github.add_comment_reaction(
                    token, owner, repo, comment_id, "eyes"
                )
            except Exception:  # noqa: BLE001
                logger.exception("failed to add eyes reaction")

        labels = {str(lbl["name"]) for lbl in (issue.get("labels") or []) if isinstance(lbl, dict)}
        # Also refresh from API for accuracy
        labels |= await self.github.list_issue_labels(token, owner, repo, issue_number)

        if config.skip_label in labels:
            await self.github.add_issue_comment(
                token,
                owner,
                repo,
                issue_number,
                f"skipped: ticket has `{config.skip_label}`",
            )
            return HttpResponse.json(200, {"ok": True, "ignored": "skip_label"})

        # Manual commands are explicit intent — skip the opt_in label gate.
        # (Board moves still require the opt_in label when mode is opt_in.)

        ctx = TicketContext(
            owner=owner,
            repo=repo,
            issue_number=issue_number,
            installation_id=installation_id,
            labels=labels,
            source="command",
        )
        runner = ActionRunner(github=self.github, config=config)

        if parsed.name == CommandName.HELP:
            await self.github.add_issue_comment(token, owner, repo, issue_number, HELP_TEXT)
            return HttpResponse.json(200, {"ok": True, "command": "help"})

        if parsed.name == CommandName.STATUS:
            state = current_state(labels)
            runs = await runner.find_active_runs(ctx)
            lines = [
                f"**State:** `{state.value if state else 'none'}`",
                f"**Active runs:** {len(runs)}",
            ]
            for run in runs:
                lines.append(f"- {run.get('html_url')}")
            await self.github.add_issue_comment(
                token, owner, repo, issue_number, "\n".join(lines)
            )
            return HttpResponse.json(200, {"ok": True, "command": "status"})

        if parsed.name == CommandName.CANCEL:
            from kanbanauts.core.config import CancelAction

            ctx.to_column = "cancelled by command"
            await runner.run_one(ctx, CancelAction(cancel=True))
            return HttpResponse.json(200, {"ok": True, "command": "cancel"})

        phase: str | None
        if parsed.name == CommandName.RETRY:
            # Retry last failed: re-run the phase named in args or default to plan.
            phase = parsed.args.strip().casefold() or "plan"
            if phase == "do":
                phase = "doit"
            if phase not in config.phases:
                phase = "plan"
        else:
            phase = phase_for_command(parsed.name)

        if phase in ("plan", "doit") and is_pr:
            await self.github.add_issue_comment(
                token,
                owner,
                repo,
                issue_number,
                f"@{user} run `/ai {phase}` on the **issue**, not on the pull request.",
            )
            return HttpResponse.json(200, {"ok": False, "error": "use_issue"})

        if phase:
            if is_active(labels):
                await self.github.add_issue_comment(
                    token,
                    owner,
                    repo,
                    issue_number,
                    "An agent is already queued or running. Use `/ai cancel` first.",
                )
                return HttpResponse.json(200, {"ok": False, "error": "busy"})
            await runner._run_phase(ctx, phase)
            return HttpResponse.json(
                200,
                {"ok": True, "command": parsed.name.value, "phase": phase},
            )

        return HttpResponse.json(200, {"ok": True, "ignored": "unhandled_command"})

    # ------------------------------------------------------------------
    # pull_request_review
    # ------------------------------------------------------------------

    async def handle_pull_request_review(
        self, event: str, payload: dict[str, Any], headers: Mapping[str, str]
    ) -> HttpResponse:
        if payload.get("action") != "submitted":
            return HttpResponse.json(200, {"ok": True, "ignored": "not_submitted"})
        review = payload.get("review") or {}
        if review.get("state") != "approved":
            return HttpResponse.json(200, {"ok": True, "ignored": "not_approved"})

        installation_id = int((payload.get("installation") or {}).get("id") or 0)
        repo_obj = payload.get("repository") or {}
        owner = str((repo_obj.get("owner") or {}).get("login") or "")
        repo = str(repo_obj.get("name") or "")
        pr = payload.get("pull_request") or {}
        if not all([installation_id, owner, repo]):
            return HttpResponse.json(200, {"ok": True, "ignored": "incomplete"})

        token = await self.github.installation_token(installation_id)
        config = await self.load_config(token, owner, repo)
        if config is None:
            return HttpResponse.json(200, {"ok": True, "ignored": "no_config"})

        review_cfg = config.column("Review")
        if review_cfg is None or review_cfg.on_pr_approved is None:
            return HttpResponse.json(200, {"ok": True, "ignored": "no_on_pr_approved"})

        # Resolve linked issue from PR body "Closes #N" / "Fixes #N"
        issue_number = _closing_issue_number(str(pr.get("body") or ""))
        if issue_number is None:
            # Fall back to first linked issue via timeline — keep simple for v1
            return HttpResponse.json(200, {"ok": True, "ignored": "no_linked_issue"})

        try:
            project_id, field_id, options, _ = await self.project_field_context(token, config)
        except ValueError as exc:
            return HttpResponse.json(200, {"ok": False, "error": str(exc)})

        # Find project item for the issue via GraphQL node search — use issue node id
        issue_data = await self.github.get(
            f"/repos/{owner}/{repo}/issues/{issue_number}", token
        )
        issue_node_id = str(issue_data["node_id"])
        item_id = await self._find_project_item(token, config, issue_node_id)

        ctx = TicketContext(
            owner=owner,
            repo=repo,
            issue_number=issue_number,
            installation_id=installation_id,
            item_node_id=item_id,
            project_id=project_id,
            status_field_id=field_id,
            status_options=options,
        )
        runner = ActionRunner(github=self.github, config=config)
        await runner.run_one(ctx, review_cfg.on_pr_approved)
        return HttpResponse.json(200, {"ok": True, "moved": True})

    # ------------------------------------------------------------------
    # workflow_run safety net
    # ------------------------------------------------------------------

    async def handle_workflow_run(
        self, event: str, payload: dict[str, Any], headers: Mapping[str, str]
    ) -> HttpResponse:
        if payload.get("action") != "completed":
            return HttpResponse.json(200, {"ok": True, "ignored": "not_completed"})

        run = payload.get("workflow_run") or {}
        conclusion = run.get("conclusion")
        name = str(run.get("display_title") or run.get("name") or "")
        parsed = parse_run_name(name)
        if parsed is None:
            # Try name field alone
            parsed = parse_run_name(str(run.get("name") or ""))
        if parsed is None:
            return HttpResponse.json(200, {"ok": True, "ignored": "not_agent_run"})

        phase, issue_number = parsed
        installation_id = int((payload.get("installation") or {}).get("id") or 0)
        repo_obj = payload.get("repository") or {}
        owner = str((repo_obj.get("owner") or {}).get("login") or "")
        repo = str(repo_obj.get("name") or "")
        if not all([installation_id, owner, repo]):
            return HttpResponse.json(200, {"ok": True, "ignored": "incomplete"})

        token = await self.github.installation_token(installation_id)
        config = await self.load_config(token, owner, repo)
        if config is None:
            return HttpResponse.json(200, {"ok": True, "ignored": "no_config"})

        if conclusion == "success":
            # /report is the primary success path; ignore success here.
            return HttpResponse.json(200, {"ok": True, "ignored": "success_via_report"})

        if conclusion == "cancelled":
            # Intentional cancel if ticket left the phase column.
            current_col = await self._current_column_for_issue(
                token, config, owner, repo, issue_number
            )
            phase_col = None
            for col_name, col_cfg in config.columns.items():
                for action in col_cfg.on_enter:
                    from kanbanauts.core.config import RunAction

                    if isinstance(action, RunAction) and action.run == phase:
                        phase_col = col_name
                        break
            if current_col and phase_col and current_col.casefold() != phase_col.casefold():
                return HttpResponse.json(200, {"ok": True, "ignored": "intentional_cancel"})

        # failure / timed_out / cancelled-while-still-in-column / etc.
        if conclusion in ("failure", "timed_out", "cancelled", "startup_failure"):
            labels = await self.github.list_issue_labels(token, owner, repo, issue_number)
            ctx = TicketContext(
                owner=owner,
                repo=repo,
                issue_number=issue_number,
                installation_id=installation_id,
                labels=labels,
            )
            runner = ActionRunner(github=self.github, config=config)
            await runner.set_state(ctx, token, AgentState.FAILED)
            html = run.get("html_url") or ""
            await self.github.add_issue_comment(
                token,
                owner,
                repo,
                issue_number,
                f"Agent run **{conclusion}** for phase `{phase}`.\n\n{html}",
            )
            return HttpResponse.json(200, {"ok": True, "marked": "failed"})

        return HttpResponse.json(200, {"ok": True, "ignored": conclusion})

    async def _current_column_for_issue(
        self,
        token: str,
        config: KanbanautsConfig,
        owner: str,
        repo: str,
        issue_number: int,
    ) -> str | None:
        if not config.has_project:
            return None
        issue_data = await self.github.get(f"/repos/{owner}/{repo}/issues/{issue_number}", token)
        item_id = await self._find_project_item(token, config, str(issue_data["node_id"]))
        if not item_id:
            return None
        data = await self.github.graphql(token, ITEM_WITH_CONTENT_QUERY, {"id": item_id})
        for node in (data.get("node") or {}).get("fieldValues", {}).get("nodes") or []:
            field = (node.get("field") or {}).get("name")
            if field and field.casefold() == config.status_field.casefold():
                return str(node.get("name") or "") or None
        return None

    async def _find_project_item(
        self, token: str, config: KanbanautsConfig, issue_node_id: str
    ) -> str | None:
        if not config.has_project:
            return None
        query = """
        query($owner: String!, $number: Int!) {
          organization(login: $owner) {
            projectV2(number: $number) {
              items(first: 100) {
                nodes {
                  id
                  content { ... on Issue { id } }
                }
              }
            }
          }
        }
        """
        data = await self.github.graphql(
            token, query, {"owner": config.project_owner, "number": config.project_number}
        )
        for node in data["organization"]["projectV2"]["items"]["nodes"]:
            content = node.get("content") or {}
            if content.get("id") == issue_node_id:
                return str(node["id"])
        return None

    async def handle_installation(
        self, event: str, payload: dict[str, Any], headers: Mapping[str, str]
    ) -> HttpResponse:
        from kanbanauts.core.onboarding import OnboardingService

        onboarding = OnboardingService(github=self.github)
        return await onboarding.handle_event(event, payload)

    # ------------------------------------------------------------------
    # OIDC helpers
    # ------------------------------------------------------------------

    def _extract_oidc_token(self, request: HttpRequest, body: dict[str, Any] | None = None) -> str:
        if body:
            from_body = str(body.get("oidc_token") or "").strip()
            if from_body:
                return from_body
        auth = request.headers.get("authorization") or request.headers.get("Authorization") or ""
        if auth.lower().startswith("bearer "):
            return auth[7:].strip()
        return ""

    async def _resolve_installation_for_claims(
        self, claims: Any
    ) -> tuple[int, int, str]:
        """Return (installation_id, owner_id, default_branch). Always look up via API."""
        from kanbanauts.core.broker import OidcClaims

        assert isinstance(claims, OidcClaims)
        token_app = self.github.app_jwt()
        client = self.github._client()
        inst_resp = await client.get(
            f"/repos/{claims.repository}/installation",
            headers={"Authorization": f"Bearer {token_app}"},
        )
        if inst_resp.status_code == 404:
            raise OidcError("App not installed on repository")
        inst_resp.raise_for_status()
        installation = inst_resp.json()
        installation_id = int(installation["id"])
        account = installation.get("account") or {}
        owner_id = account.get("id")
        if owner_id is None:
            raise OidcError("installation account id missing")
        tmp = await self.github.installation_token(installation_id)
        repo_data = await self.github.get_repository(tmp, claims.owner, claims.repo)
        default_branch = str(repo_data.get("default_branch") or "main")
        self.broker.authorize(
            claims,
            default_branch=default_branch,
            installation_owner_id=int(owner_id),
        )
        return installation_id, int(owner_id), default_branch

    # ------------------------------------------------------------------
    # /token /report /preflight /admin/rollout
    # ------------------------------------------------------------------

    async def handle_token(self, request: HttpRequest) -> HttpResponse:
        try:
            body = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return HttpResponse.text(400, "invalid json")
        oidc = self._extract_oidc_token(request, body)
        if not oidc:
            return HttpResponse.text(401, "missing oidc_token")

        try:
            claims = self.broker.verify_oidc(oidc)
            installation_id, _owner_id, _branch = await self._resolve_installation_for_claims(
                claims
            )
            minted = await self.github.installation_token(
                installation_id,
                repositories=[claims.repo],
                permissions=BROKER_PERMISSIONS,
            )
        except OidcError as exc:
            return HttpResponse.json(403, {"ok": False, "error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            logger.exception("token mint failed")
            return HttpResponse.json(500, {"ok": False, "error": str(exc)})

        return HttpResponse.json(200, {"token": minted, "repository": claims.repository})

    async def handle_report(self, request: HttpRequest) -> HttpResponse:
        try:
            body = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return HttpResponse.text(400, "invalid json")

        oidc = self._extract_oidc_token(request, body)
        if not oidc:
            return HttpResponse.text(401, "missing oidc_token")

        status = str(body.get("status") or "")
        phase = str(body.get("phase") or "")
        issue_number = int(body.get("issue_number") or 0)
        pr_number = body.get("pr_number")
        message = str(body.get("message") or "").strip()
        # Ignore owner/repo/installation_id from the body — take them from OIDC only.

        try:
            claims = self.broker.verify_oidc(oidc)
            installation_id, _owner_id, _branch = await self._resolve_installation_for_claims(
                claims
            )
        except OidcError as exc:
            return HttpResponse.json(403, {"ok": False, "error": str(exc)})

        owner = claims.owner
        repo = claims.repo

        if not all([status, phase, issue_number, owner, repo]):
            return HttpResponse.text(400, "missing fields")

        token = await self.github.installation_token(installation_id)
        config = await self.load_config(token, owner, repo)
        if config is None:
            return HttpResponse.json(404, {"ok": False, "error": "no_config"})

        labels = await self.github.list_issue_labels(token, owner, repo, issue_number)
        ctx = TicketContext(
            owner=owner,
            repo=repo,
            issue_number=issue_number,
            installation_id=installation_id,
            labels=labels,
        )
        runner = ActionRunner(github=self.github, config=config)

        if status == "succeeded":
            await runner.set_state(ctx, token, AgentState.SUCCEEDED)
            # Find column for this phase and run on_success (only if on the board).
            for _col_name, col_cfg in config.columns.items():
                from kanbanauts.core.config import RunAction

                for action in col_cfg.on_enter:
                    if isinstance(action, RunAction) and action.run == phase:
                        if col_cfg.on_success:
                            await self._maybe_run_column_action(
                                runner, ctx, token, config, owner, repo, issue_number,
                                col_cfg.on_success,
                            )
                        break
        elif status == "no_code":
            await runner.set_state(ctx, token, AgentState.SUCCEEDED)
            for _col_name, col_cfg in config.columns.items():
                from kanbanauts.core.config import RunAction

                for action in col_cfg.on_enter:
                    if isinstance(action, RunAction) and action.run == phase:
                        if col_cfg.on_no_code:
                            await self._maybe_run_column_action(
                                runner, ctx, token, config, owner, repo, issue_number,
                                col_cfg.on_no_code,
                            )
                        break
        elif status == "blocked":
            await runner.set_state(ctx, token, AgentState.BLOCKED)
            if message:
                await self.github.add_issue_comment(
                    token, owner, repo, issue_number, message
                )
        elif status == "failed":
            await runner.set_state(ctx, token, AgentState.FAILED)
            if message:
                await self.github.add_issue_comment(
                    token, owner, repo, issue_number, message
                )
        elif status == "running":
            await runner.set_state(ctx, token, AgentState.RUNNING)
        else:
            return HttpResponse.json(400, {"ok": False, "error": f"unknown status {status}"})

        return HttpResponse.json(
            200,
            {
                "ok": True,
                "status": status,
                "phase": phase,
                "issue": issue_number,
                "pr_number": pr_number,
            },
        )

    async def _maybe_run_column_action(
        self,
        runner: ActionRunner,
        ctx: TicketContext,
        token: str,
        config: KanbanautsConfig,
        owner: str,
        repo: str,
        issue_number: int,
        action: Any,
    ) -> None:
        """Run on_success / on_no_code only when the issue is on the configured board."""
        if not config.has_project:
            return
        try:
            project_id, field_id, options, _ = await self.project_field_context(
                token, config
            )
            issue_data = await self.github.get(
                f"/repos/{owner}/{repo}/issues/{issue_number}", token
            )
            item_id = await self._find_project_item(
                token, config, str(issue_data["node_id"])
            )
            if not item_id:
                logger.info(
                    "skip column action: %s/%s#%s not on board",
                    owner,
                    repo,
                    issue_number,
                )
                return
            ctx.project_id = project_id
            ctx.status_field_id = field_id
            ctx.status_options = options
            ctx.item_node_id = item_id
        except Exception:  # noqa: BLE001
            logger.exception("project context for column action")
            return
        await runner.run_one(ctx, action)

    async def handle_preflight(self, request: HttpRequest) -> HttpResponse:
        oidc = self._extract_oidc_token(request)
        issue_s = request.query.get("issue") or ""
        phase = request.query.get("phase") or ""
        source = (request.query.get("source") or "board").casefold()
        if not oidc or not issue_s or not phase:
            return HttpResponse.text(400, "issue, phase, and Bearer OIDC required")
        try:
            issue_number = int(issue_s)
            claims = self.broker.verify_oidc(oidc)
            installation_id, _owner_id, _branch = await self._resolve_installation_for_claims(
                claims
            )
        except (ValueError, OidcError) as exc:
            return HttpResponse.json(403, {"ok": False, "error": str(exc), "skip": True})

        token = await self.github.installation_token(installation_id)
        config = await self.load_config(token, claims.owner, claims.repo)
        if config is None:
            return HttpResponse.json(200, {"ok": True, "skip": True, "reason": "no_config"})

        # Comment-triggered runs do not require the issue to be in a column.
        if source != "command":
            if not config.has_project:
                return HttpResponse.json(
                    200, {"ok": True, "skip": True, "reason": "no_project"}
                )
            current_col = await self._current_column_for_issue(
                token, config, claims.owner, claims.repo, issue_number
            )
            expected_col = None
            for col_name, col_cfg in config.columns.items():
                from kanbanauts.core.config import RunAction

                for action in col_cfg.on_enter:
                    if isinstance(action, RunAction) and action.run == phase:
                        expected_col = col_name
                        break
            if expected_col is None:
                return HttpResponse.json(
                    200, {"ok": True, "skip": True, "reason": "unknown_phase"}
                )
            if current_col is None or current_col.casefold() != expected_col.casefold():
                return HttpResponse.json(
                    200,
                    {
                        "ok": True,
                        "skip": True,
                        "reason": "column_mismatch",
                        "current": current_col,
                        "expected": expected_col,
                    },
                )
        # Mark running
        labels = await self.github.list_issue_labels(
            token, claims.owner, claims.repo, issue_number
        )
        ctx = TicketContext(
            owner=claims.owner,
            repo=claims.repo,
            issue_number=issue_number,
            installation_id=installation_id,
            labels=labels,
            source=source if source in ("board", "command") else "board",
        )
        runner = ActionRunner(github=self.github, config=config)
        await runner.set_state(ctx, token, AgentState.RUNNING)
        return HttpResponse.json(200, {"ok": True, "skip": False})

    async def handle_rollout(self, request: HttpRequest) -> HttpResponse:
        from kanbanauts.core.rollout import RolloutService, StaleDeploymentError

        try:
            body = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return HttpResponse.text(400, "invalid json")
        oidc = self._extract_oidc_token(request, body)
        if not oidc:
            return HttpResponse.text(401, "missing oidc_token")
        try:
            claims = self.broker.verify_oidc(oidc)
            self.broker.authorize_release(claims)
        except OidcError as exc:
            return HttpResponse.json(403, {"ok": False, "error": str(exc)})

        dry_run = bool(body.get("dry_run", False))
        target_version = int(body.get("caller_version") or 1)
        rollout = RolloutService(github=self.github)
        try:
            result = await rollout.run(
                caller_version=target_version, dry_run=dry_run
            )
        except StaleDeploymentError as exc:
            return HttpResponse.json(409, {"ok": False, "error": str(exc)})
        return HttpResponse.json(200, {"ok": True, **result})


_CLOSING_RE = re.compile(
    r"(?i)\b(?:closes|fixes|resolves)\s+#(\d+)\b"
)


def _closing_issue_number(body: str) -> int | None:
    match = _CLOSING_RE.search(body)
    if not match:
        return None
    return int(match.group(1))
