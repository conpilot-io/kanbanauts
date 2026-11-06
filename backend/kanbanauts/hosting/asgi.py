"""Starlette/ASGI adapter — portable hosting entry point."""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from kanbanauts.core.ports import HttpRequest, HttpResponse
from kanbanauts.core.service import KanbanautsService, Settings
from kanbanauts.hosting.secrets import EnvSecretProvider


def _settings_from_env() -> Settings:
    secrets = EnvSecretProvider(
        mapping={
            k: v
            for k, v in {
                "github-app-private-key": os.environ.get("GITHUB_APP_PRIVATE_KEY")
                or os.environ.get("github-app-private-key"),
                "github-webhook-secret": os.environ.get("GITHUB_WEBHOOK_SECRET")
                or os.environ.get("github-webhook-secret"),
            }.items()
            if v
        }
    )
    return Settings(
        app_id=os.environ["GITHUB_APP_ID"],
        private_key_pem=secrets.get("github-app-private-key").replace("\\n", "\n"),
        webhook_secret=secrets.get("github-webhook-secret"),
        oidc_audience=os.environ.get(
            "KANBANAUTS_OIDC_AUDIENCE",
            os.environ.get("KANBANAUTS_URL", "https://kanbanauts.local"),
        ),
    )


def create_service() -> KanbanautsService:
    return KanbanautsService.create(_settings_from_env())


def _to_starlette(response: HttpResponse) -> Response:
    return Response(
        content=response.body,
        status_code=response.status,
        headers=dict(response.headers),
    )


async def _from_starlette(request: Request) -> HttpRequest:
    body = await request.body()
    headers = {k: v for k, v in request.headers.items()}
    query = {k: v for k, v in request.query_params.items()}
    return HttpRequest(
        method=request.method,
        path=request.url.path,
        headers=headers,
        body=body,
        query=query,
    )


def create_app(service: KanbanautsService | None = None) -> Starlette:
    svc = service or create_service()

    async def catch_all(request: Request) -> Response:
        http_req = await _from_starlette(request)
        http_resp = await svc.handle_http(http_req)
        return _to_starlette(http_resp)

    return Starlette(
        routes=[
            Route("/{path:path}", endpoint=catch_all, methods=["GET", "POST", "PUT", "DELETE"]),
            Route("/", endpoint=catch_all, methods=["GET", "POST"]),
        ]
    )


# Default ASGI app for uvicorn: `uvicorn kanbanauts.hosting.asgi:app`
app: Callable[..., Awaitable[None]] | Starlette
try:
    app = create_app()
except KeyError:
    # Allow import without env (tests construct their own app).
    app = Starlette()
