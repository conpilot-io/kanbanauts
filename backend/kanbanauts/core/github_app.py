"""GitHub App JWT, installation tokens, REST + GraphQL helpers."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx
import jwt

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"


@dataclass(slots=True)
class GitHubApp:
    app_id: str
    private_key_pem: str
    client: httpx.AsyncClient | None = None

    def _client(self) -> httpx.AsyncClient:
        if self.client is None:
            self.client = httpx.AsyncClient(
                base_url=GITHUB_API,
                headers={
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                    "User-Agent": "kanbanauts",
                },
                timeout=30.0,
            )
        return self.client

    def app_jwt(self, *, now: int | None = None) -> str:
        ts = now if now is not None else int(time.time())
        payload = {
            "iat": ts - 60,
            "exp": ts + 9 * 60,
            "iss": self.app_id,
        }
        return jwt.encode(payload, self.private_key_pem, algorithm="RS256")

    async def installation_token(
        self,
        installation_id: int,
        *,
        repositories: list[str] | None = None,
        permissions: dict[str, str] | None = None,
    ) -> str:
        body: dict[str, Any] = {}
        if repositories is not None:
            body["repositories"] = repositories
        if permissions is not None:
            body["permissions"] = permissions
        headers = {"Authorization": f"Bearer {self.app_jwt()}"}
        response = await self._client().post(
            f"/app/installations/{installation_id}/access_tokens",
            headers=headers,
            json=body or None,
        )
        response.raise_for_status()
        data = response.json()
        return str(data["token"])

    async def get(
        self, path: str, token: str, *, params: dict[str, Any] | None = None
    ) -> Any:
        response = await self._client().get(
            path, headers={"Authorization": f"Bearer {token}"}, params=params
        )
        response.raise_for_status()
        if response.status_code == 204:
            return None
        return response.json()

    async def post(self, path: str, token: str, json_body: Any | None = None) -> Any:
        response = await self._client().post(
            path,
            headers={"Authorization": f"Bearer {token}"},
            json=json_body,
        )
        response.raise_for_status()
        if response.status_code == 204:
            return None
        return response.json()

    async def put(self, path: str, token: str, json_body: Any | None = None) -> Any:
        response = await self._client().put(
            path,
            headers={"Authorization": f"Bearer {token}"},
            json=json_body,
        )
        response.raise_for_status()
        if response.status_code == 204:
            return None
        return response.json()

    async def delete(self, path: str, token: str) -> None:
        response = await self._client().delete(
            path, headers={"Authorization": f"Bearer {token}"}
        )
        response.raise_for_status()

    async def graphql(self, token: str, query: str, variables: dict[str, Any] | None = None) -> Any:
        response = await self._client().post(
            "/graphql",
            headers={"Authorization": f"Bearer {token}"},
            json={"query": query, "variables": variables or {}},
        )
        response.raise_for_status()
        data = response.json()
        if data.get("errors"):
            raise RuntimeError(f"GraphQL errors: {data['errors']}")
        return data["data"]

    async def get_repo_file(
        self, token: str, owner: str, repo: str, path: str, *, ref: str | None = None
    ) -> str | None:
        params = {"ref": ref} if ref else None
        response = await self._client().get(
            f"/repos/{owner}/{repo}/contents/{path}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github.raw",
            },
            params=params,
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.text

    async def list_issue_labels(
        self, token: str, owner: str, repo: str, issue_number: int
    ) -> set[str]:
        data = await self.get(f"/repos/{owner}/{repo}/issues/{issue_number}/labels", token)
        assert isinstance(data, list)
        return {str(item["name"]) for item in data}

    async def set_issue_state_label(
        self,
        token: str,
        owner: str,
        repo: str,
        issue_number: int,
        *,
        remove: list[str],
        add: list[str],
    ) -> None:
        for label in remove:
            response = await self._client().delete(
                f"/repos/{owner}/{repo}/issues/{issue_number}/labels/{label}",
                headers={"Authorization": f"Bearer {token}"},
            )
            if response.status_code not in (200, 404):
                response.raise_for_status()
        if add:
            await self.post(
                f"/repos/{owner}/{repo}/issues/{issue_number}/labels",
                token,
                {"labels": add},
            )

    async def add_issue_comment(
        self, token: str, owner: str, repo: str, issue_number: int, body: str
    ) -> Any:
        return await self.post(
            f"/repos/{owner}/{repo}/issues/{issue_number}/comments",
            token,
            {"body": body},
        )

    async def collaborator_permission(
        self, token: str, owner: str, repo: str, username: str
    ) -> str | None:
        response = await self._client().get(
            f"/repos/{owner}/{repo}/collaborators/{username}/permission",
            headers={"Authorization": f"Bearer {token}"},
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        data = response.json()
        return str(data.get("permission") or "")

    async def dispatch_workflow(
        self,
        token: str,
        owner: str,
        repo: str,
        workflow_id: str,
        *,
        ref: str,
        inputs: dict[str, Any],
    ) -> None:
        await self.post(
            f"/repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches",
            token,
            {"ref": ref, "inputs": inputs},
        )

    async def list_workflow_runs(
        self,
        token: str,
        owner: str,
        repo: str,
        *,
        status: str | None = None,
        per_page: int = 50,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"per_page": per_page}
        if status:
            params["status"] = status
        data = await self.get(f"/repos/{owner}/{repo}/actions/runs", token, params=params)
        assert isinstance(data, dict)
        runs = data.get("workflow_runs") or []
        assert isinstance(runs, list)
        return runs

    async def cancel_workflow_run(
        self, token: str, owner: str, repo: str, run_id: int
    ) -> None:
        response = await self._client().post(
            f"/repos/{owner}/{repo}/actions/runs/{run_id}/cancel",
            headers={"Authorization": f"Bearer {token}"},
        )
        # 409 if already completed — treat as ok
        if response.status_code in (202, 409):
            return
        response.raise_for_status()

    async def get_repository(self, token: str, owner: str, repo: str) -> dict[str, Any]:
        data = await self.get(f"/repos/{owner}/{repo}", token)
        assert isinstance(data, dict)
        return data

    async def ensure_label(
        self,
        token: str,
        owner: str,
        repo: str,
        name: str,
        *,
        color: str,
        description: str = "",
    ) -> None:
        response = await self._client().post(
            f"/repos/{owner}/{repo}/labels",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": name, "color": color, "description": description},
        )
        if response.status_code in (201, 422):
            # 422 = already exists
            return
        response.raise_for_status()

    async def get_file_sha(
        self, token: str, owner: str, repo: str, path: str, *, ref: str
    ) -> str | None:
        response = await self._client().get(
            f"/repos/{owner}/{repo}/contents/{path}",
            headers={"Authorization": f"Bearer {token}"},
            params={"ref": ref},
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict):
            sha = data.get("sha")
            return str(sha) if sha else None
        return None

    async def put_file(
        self,
        token: str,
        owner: str,
        repo: str,
        path: str,
        *,
        content: str,
        message: str,
        branch: str,
        sha: str | None = None,
    ) -> dict[str, Any]:
        import base64

        body: dict[str, Any] = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "branch": branch,
        }
        if sha:
            body["sha"] = sha
        data = await self.put(
            f"/repos/{owner}/{repo}/contents/{path}",
            token,
            body,
        )
        assert isinstance(data, dict)
        return data

    async def create_ref(
        self, token: str, owner: str, repo: str, *, ref: str, sha: str
    ) -> None:
        await self.post(
            f"/repos/{owner}/{repo}/git/refs",
            token,
            {"ref": ref, "sha": sha},
        )

    async def get_ref_sha(
        self, token: str, owner: str, repo: str, ref: str
    ) -> str | None:
        # ref like heads/main
        response = await self._client().get(
            f"/repos/{owner}/{repo}/git/ref/{ref}",
            headers={"Authorization": f"Bearer {token}"},
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        data = response.json()
        return str((data.get("object") or {}).get("sha") or "") or None

    async def create_pull_request(
        self,
        token: str,
        owner: str,
        repo: str,
        *,
        title: str,
        head: str,
        base: str,
        body: str,
    ) -> dict[str, Any]:
        data = await self.post(
            f"/repos/{owner}/{repo}/pulls",
            token,
            {"title": title, "head": head, "base": base, "body": body},
        )
        assert isinstance(data, dict)
        return data

    async def list_pull_requests(
        self,
        token: str,
        owner: str,
        repo: str,
        *,
        head: str | None = None,
        state: str = "open",
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"state": state}
        if head:
            params["head"] = head
        data = await self.get(f"/repos/{owner}/{repo}/pulls", token, params=params)
        assert isinstance(data, list)
        return data

    async def list_installations(self, *, per_page: int = 100) -> list[dict[str, Any]]:
        headers = {"Authorization": f"Bearer {self.app_jwt()}"}
        out: list[dict[str, Any]] = []
        page = 1
        while True:
            response = await self._client().get(
                "/app/installations",
                headers=headers,
                params={"per_page": per_page, "page": page},
            )
            response.raise_for_status()
            batch = response.json()
            if not isinstance(batch, list) or not batch:
                break
            out.extend(batch)
            if len(batch) < per_page:
                break
            page += 1
        return out

    async def list_installation_repos(
        self, token: str, *, per_page: int = 100
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        page = 1
        while True:
            data = await self.get(
                "/installation/repositories",
                token,
                params={"per_page": per_page, "page": page},
            )
            assert isinstance(data, dict)
            repos = data.get("repositories") or []
            assert isinstance(repos, list)
            if not repos:
                break
            out.extend(repos)
            if len(repos) < per_page:
                break
            page += 1
        return out

    async def list_org_projects(
        self, token: str, org: str
    ) -> list[dict[str, Any]]:
        """Return org Projects V2 as {number, title, url}."""
        query = """
        query($org: String!, $cursor: String) {
          organization(login: $org) {
            projectsV2(first: 20, after: $cursor) {
              nodes { number title url }
              pageInfo { hasNextPage endCursor }
            }
          }
        }
        """
        out: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            data = await self.graphql(
                token, query, {"org": org, "cursor": cursor}
            )
            org_data = (data.get("organization") or {})
            projects = org_data.get("projectsV2") or {}
            for node in projects.get("nodes") or []:
                if isinstance(node, dict) and node.get("number") is not None:
                    out.append(
                        {
                            "number": int(node["number"]),
                            "title": str(node.get("title") or ""),
                            "url": str(node.get("url") or ""),
                        }
                    )
            page = projects.get("pageInfo") or {}
            if not page.get("hasNextPage"):
                break
            cursor = page.get("endCursor")
        return out

    async def close(self) -> None:
        if self.client is not None:
            await self.client.aclose()
            self.client = None


# GraphQL snippets used by the lifecycle layer.

PROJECT_FIELD_OPTIONS_QUERY = """
query($owner: String!, $number: Int!) {
  organization(login: $owner) {
    projectV2(number: $number) {
      id
      field(name: $fieldName) {
        ... on ProjectV2SingleSelectField {
          id
          name
          options { id name }
        }
      }
    }
  }
}
"""

# field(name:) requires a variable — define a proper query:
PROJECT_STATUS_FIELD_QUERY = """
query($owner: String!, $number: Int!) {
  organization(login: $owner) {
    projectV2(number: $number) {
      id
      fields(first: 50) {
        nodes {
          __typename
          ... on ProjectV2SingleSelectField {
            id
            name
            options { id name }
          }
        }
      }
    }
  }
}
"""

UPDATE_ITEM_STATUS_MUTATION = """
mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!, $optionId: String!) {
  updateProjectV2ItemFieldValue(
    input: {
      projectId: $projectId
      itemId: $itemId
      fieldId: $fieldId
      value: { singleSelectOptionId: $optionId }
    }
  ) {
    projectV2Item { id }
  }
}
"""

ITEM_WITH_CONTENT_QUERY = """
query($id: ID!) {
  node(id: $id) {
    ... on ProjectV2Item {
      id
      type
      content {
        __typename
        ... on Issue {
          number
          title
          repository { name nameWithOwner owner { login } }
        }
        ... on PullRequest {
          number
          repository { name nameWithOwner owner { login } }
        }
      }
      fieldValues(first: 30) {
        nodes {
          ... on ProjectV2ItemFieldSingleSelectValue {
            name
            field { ... on ProjectV2SingleSelectField { name } }
          }
        }
      }
    }
  }
}
"""

FIND_ITEM_FOR_ISSUE_QUERY = """
query($owner: String!, $number: Int!, $issueId: ID!) {
  organization(login: $owner) {
    projectV2(number: $number) {
      id
      items(first: 1, query: $issueId) {
        nodes { id }
      }
    }
  }
}
"""
