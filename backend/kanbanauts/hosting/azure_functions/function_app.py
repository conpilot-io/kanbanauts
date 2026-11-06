"""Azure Functions (v2 programming model) adapter."""

from __future__ import annotations

import logging
import os

import azure.functions as func

from kanbanauts.core.ports import HttpRequest
from kanbanauts.core.service import KanbanautsService, Settings
from kanbanauts.hosting.secrets import AzureKeyVaultSecretProvider, EnvSecretProvider

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)
logger = logging.getLogger("kanbanauts")

_service: KanbanautsService | None = None


def _get_service() -> KanbanautsService:
    global _service
    if _service is not None:
        return _service
    vault_url = os.environ.get("KEY_VAULT_URL")
    if vault_url:
        secrets: EnvSecretProvider | AzureKeyVaultSecretProvider = AzureKeyVaultSecretProvider(
            vault_url=vault_url
        )
    else:
        secrets = EnvSecretProvider()
    settings = Settings(
        app_id=os.environ["GITHUB_APP_ID"],
        private_key_pem=secrets.get("github-app-private-key").replace("\\n", "\n"),
        webhook_secret=secrets.get("github-webhook-secret"),
        oidc_audience=os.environ.get(
            "KANBANAUTS_OIDC_AUDIENCE",
            os.environ.get("KANBANAUTS_URL", "https://kanbanauts.local"),
        ),
    )
    _service = KanbanautsService.create(settings)
    return _service


def _to_http_request(req: func.HttpRequest) -> HttpRequest:
    headers = {k: v for k, v in req.headers.items()}
    query = {k: v for k, v in req.params.items()}
    body = req.get_body() or b""
    return HttpRequest(
        method=req.method or "GET",
        path=req.url.path if hasattr(req.url, "path") else req.route_params.get("path", "/"),
        headers=headers,
        body=body,
        query=query,
    )


@app.route(route="{*path}", methods=["GET", "POST", "PUT", "DELETE"])  # type: ignore[untyped-decorator]
async def http_trigger(req: func.HttpRequest) -> func.HttpResponse:
    service = _get_service()
    # Azure Functions path is relative to /api/
    path = "/" + (req.route_params.get("path") or "")
    http_req = _to_http_request(req)
    # Normalize path so service sees /webhook, /token, etc.
    http_req = HttpRequest(
        method=http_req.method,
        path=path if path != "/" else http_req.path,
        headers=http_req.headers,
        body=http_req.body,
        query=http_req.query,
    )
    response = await service.handle_http(http_req)
    return func.HttpResponse(
        body=response.body,
        status_code=response.status,
        headers=dict(response.headers),
        mimetype=response.headers.get("content-type", "text/plain"),
    )
