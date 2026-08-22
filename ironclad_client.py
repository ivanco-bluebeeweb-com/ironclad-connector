"""Ironclad Public API HTTP client -- OAuth 2.0 Client Credentials auth
against a user's OWN Ironclad company, thin wrappers over the Workflows,
Records, Entities, Obligations, Webhooks and Export domains.

WHY CLIENT CREDENTIALS GRANT, NOT AUTHORIZATION CODE -- same reasoning as
MuleSoft/PagerDuty/Mirth Connector's BYOK clients. Ironclad's own OAuth 2.0
implementation supports both grants (developer.ironcladapp.com/reference/
client-credentials-grant, confirmed during Discovery 2026-08-22). Authorization
Code ties the token to ONE consenting human user (browser redirect dance,
short-lived without a refresh-token dance Imperal would have to babysit).
Client Credentials is a pure server-to-server machine grant scoped to the
company via a registered OAuth client (Client ID/Secret created by a company
admin on the API settings page) -- exactly the shape every other BYOK
connector in this portfolio uses. The one wrinkle: every Client Credentials
request MUST also carry an `x-as-user-email` or `x-as-user-id` header naming
which user's permissions the request runs under (Ironclad has no "service
account" concept -- every request is entity-scoped to a real user, see
CONNECTOR_DISCOVERY.md SS3). connect_ironclad() therefore also collects that
acting-user email once, stored alongside the client id/secret.

WHY LEGACY ACCESS TOKEN IS NOT SUPPORTED AT ALL.
Ironclad's own docs mark it deprecated and slated for shutdown
(developer.ironcladapp.com/reference/legacy-access-token) -- building BYOK
support for a token type the vendor is actively killing would be dead code
on arrival.

WHY A REGION/SUBDOMAIN FIELD, NOT A HARDCODED na1.ironcladapp.com.
Ironclad runs separate production stacks per region -- na1 (default US),
eu1 (EU data residency) and demo (sandbox) all documented as live server
variants (raw OpenAPI `servers` list, confirmed 2026-08-22). A single
hardcoded host would silently break for every EU-hosted company. The user
picks their region once at connect time (defaulting to na1, the common
case), and it is stored with the connection -- same shape as MuleSoft's
environment_id or Salesforce's instance_url.

WHY 401 vs 403 ARE HANDLED DIFFERENTLY, SAME PRINCIPLE AS EVERY OTHER
CONNECTOR IN THIS PORTFOLIO.
A 401 means the token request itself failed (bad client id/secret, or an
expired/rejected bearer token on a resource call). A 403 means the token is
valid but the underlying scope/permission is missing for that acting user
(OAuth scope not granted on the registered client, OR the acting user lacks
that permission inside Ironclad itself -- entity-scoped, see module
docstring above). Surfacing these as different, actionable errors saves a
user from re-pasting credentials that were never the problem.

WHY 429 CARRIES RETRY-AFTER GUIDANCE.
Ironclad enforces per-bucket rate limits (400-4500 RPM depending on
resource, see CONNECTOR_DISCOVERY.md SS5) plus a hard 4500 RPM company-wide
cap, and documents `Retry-After`-style headers on 429 responses
(developer.ironcladapp.com/reference/clm-api-rate-limits). RATE_LIMITED
carries whatever wait hint the response provides instead of a generic
"try again" message.
"""
from __future__ import annotations

import base64
from typing import Any

REGION_HOSTS = {
    "na1": "https://na1.ironcladapp.com",
    "eu1": "https://eu1.ironcladapp.com",
    "demo": "https://demo.ironcladapp.com",
}

TOKEN_REJECTED = "TOKEN_REJECTED"
PERMISSION_DENIED = "PERMISSION_DENIED"
NOT_FOUND = "NOT_FOUND"
RATE_LIMITED = "RATE_LIMITED"
BACKEND_5XX = "BACKEND_5XX"
VALIDATION_FAILED = "VALIDATION_FAILED"
RESPONSE_UNEXPECTED = "RESPONSE_UNEXPECTED"
REGION_INVALID = "REGION_INVALID"


class ClientFail(Exception):
    def __init__(self, payload: dict):
        self.payload = payload
        super().__init__(payload.get("error", "ironclad client error"))


def fail(code: str, action: str, detail: str = "") -> dict:
    msg = {
        TOKEN_REJECTED: f"Ironclad rejected the client credentials while trying to {action}. Re-check the Client ID/Secret and the region.",
        PERMISSION_DENIED: f"The Ironclad OAuth client (or the acting user's Ironclad permissions) does not allow: {action}.",
        NOT_FOUND: f"Ironclad could not find the resource for: {action}.",
        RATE_LIMITED: f"Ironclad rate limit hit while trying to {action}.{(' ' + detail) if detail else ''}",
        BACKEND_5XX: f"Ironclad's API returned a server error while trying to {action}.",
        VALIDATION_FAILED: f"Ironclad rejected the request while trying to {action}.{(' ' + detail) if detail else ''}",
        RESPONSE_UNEXPECTED: f"Unexpected response from Ironclad while trying to {action}.{(' ' + detail) if detail else ''}",
        REGION_INVALID: f"Unknown Ironclad region '{detail}'. Use one of: na1, eu1, demo.",
    }.get(code, f"Error while trying to {action}.")
    return {"ok": False, "error": msg, "error_code": code}


def base_url(region: str) -> str:
    host = REGION_HOSTS.get((region or "na1").strip().lower())
    if not host:
        raise ClientFail(fail(REGION_INVALID, "resolve region", region))
    return f"{host}/public/api/v1"


def _oauth_base(region: str) -> str:
    host = REGION_HOSTS.get((region or "na1").strip().lower())
    if not host:
        raise ClientFail(fail(REGION_INVALID, "resolve region", region))
    return f"{host}/oauth"


async def get_access_token(ctx, client_id: str, client_secret: str, region: str, scope: str = "") -> dict:
    """POST /oauth/token, grant_type=client_credentials. Scope is optional --
    when omitted, Ironclad issues a token for the OAuth client's full
    registered scope set."""
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    body = {"grant_type": "client_credentials"}
    if scope:
        body["scope"] = scope
    resp = await ctx.http.post(
        f"{_oauth_base(region)}/token",
        headers={
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data=body,
    )
    if resp.status_code == 200 and isinstance(resp.body, dict) and resp.body.get("access_token"):
        return {"ok": True, "access_token": resp.body["access_token"]}
    if resp.status_code in (400, 401, 403):
        raise ClientFail(fail(TOKEN_REJECTED, "obtain an access token"))
    raise ClientFail(fail(RESPONSE_UNEXPECTED, "obtain an access token", f"HTTP {resp.status_code}"))


def _headers(token: str, as_user_email: str) -> dict:
    h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    if as_user_email:
        h["x-as-user-email"] = as_user_email
    return h


def _check_status(resp, action: str) -> Any:
    if 200 <= resp.status_code < 300:
        if resp.status_code == 204:
            return {}
        return resp.body if isinstance(resp.body, (dict, list)) else {}
    if resp.status_code == 401:
        raise ClientFail(fail(TOKEN_REJECTED, action))
    if resp.status_code == 403:
        raise ClientFail(fail(PERMISSION_DENIED, action))
    if resp.status_code == 404:
        raise ClientFail(fail(NOT_FOUND, action))
    if resp.status_code == 429:
        retry_after = resp.headers.get("Retry-After", "") if hasattr(resp, "headers") else ""
        raise ClientFail(fail(RATE_LIMITED, action, f"Retry after {retry_after}s." if retry_after else ""))
    if resp.status_code >= 500:
        raise ClientFail(fail(BACKEND_5XX, action))
    if resp.status_code == 400:
        detail = ""
        if isinstance(resp.body, dict):
            detail = resp.body.get("message") or resp.body.get("error") or ""
        raise ClientFail(fail(VALIDATION_FAILED, action, detail))
    raise ClientFail(fail(RESPONSE_UNEXPECTED, f"{action}: HTTP {resp.status_code}"))


async def check_connection(ctx, client_id: str, client_secret: str, region: str, as_user_email: str) -> dict:
    """Get a token, then a cheap GET /workflows?pageSize=1 to prove the
    OAuth client actually has a working scope -- a valid token alone does
    not guarantee any real permission (see PERMISSION_DENIED docstring)."""
    tok = await get_access_token(ctx, client_id, client_secret, region)
    if not tok.get("ok"):
        return tok
    resp = await ctx.http.get(
        f"{base_url(region)}/workflows",
        headers=_headers(tok["access_token"], as_user_email),
        params={"pageSize": 1},
    )
    try:
        _check_status(resp, "verify connection")
    except ClientFail as e:
        return e.payload
    return {"ok": True}


async def _token(ctx, client_id: str, client_secret: str, region: str) -> str:
    tok = await get_access_token(ctx, client_id, client_secret, region)
    if not tok.get("ok"):
        raise ClientFail(tok)
    return tok["access_token"]


async def _get(ctx, conn: dict, path: str, action: str, params: dict | None = None):
    token = await _token(ctx, conn["client_id"], conn["client_secret"], conn["region"])
    resp = await ctx.http.get(
        f"{base_url(conn['region'])}{path}",
        headers=_headers(token, conn.get("as_user_email", "")),
        params=params or {},
    )
    return _check_status(resp, action)


async def _post(ctx, conn: dict, path: str, action: str, json: dict | None = None, params: dict | None = None):
    token = await _token(ctx, conn["client_id"], conn["client_secret"], conn["region"])
    resp = await ctx.http.post(
        f"{base_url(conn['region'])}{path}",
        headers=_headers(token, conn.get("as_user_email", "")),
        json=json or {},
        params=params or {},
    )
    return _check_status(resp, action)


async def _patch(ctx, conn: dict, path: str, action: str, json: dict | None = None):
    token = await _token(ctx, conn["client_id"], conn["client_secret"], conn["region"])
    resp = await ctx.http.patch(
        f"{base_url(conn['region'])}{path}",
        headers=_headers(token, conn.get("as_user_email", "")),
        json=json or {},
    )
    return _check_status(resp, action)


async def _put(ctx, conn: dict, path: str, action: str, json: dict | None = None):
    token = await _token(ctx, conn["client_id"], conn["client_secret"], conn["region"])
    resp = await ctx.http.put(
        f"{base_url(conn['region'])}{path}",
        headers=_headers(token, conn.get("as_user_email", "")),
        json=json or {},
    )
    return _check_status(resp, action)


async def _delete(ctx, conn: dict, path: str, action: str):
    token = await _token(ctx, conn["client_id"], conn["client_secret"], conn["region"])
    resp = await ctx.http.delete(
        f"{base_url(conn['region'])}{path}",
        headers=_headers(token, conn.get("as_user_email", "")),
    )
    return _check_status(resp, action)


# ──────────────────────────────────────────────────────────────────────────
# Workflows
# ──────────────────────────────────────────────────────────────────────────

async def list_workflows(ctx, conn, params: dict):
    return await _get(ctx, conn, "/workflows", "list workflows", params)


async def get_workflow(ctx, conn, workflow_id: str):
    return await _get(ctx, conn, f"/workflows/{workflow_id}", "retrieve a workflow")


async def launch_workflow(ctx, conn, body: dict):
    return await _post(ctx, conn, "/workflows", "launch a workflow", body)


async def launch_workflow_async(ctx, conn, body: dict):
    return await _post(ctx, conn, "/workflows/async", "launch a workflow asynchronously", body)


async def bulk_launch_workflow(ctx, conn, body: dict):
    return await _post(ctx, conn, "/workflows/bulk", "bulk launch workflows", body)


async def cancel_workflow(ctx, conn, workflow_id: str):
    return await _post(ctx, conn, f"/workflows/{workflow_id}/cancel", "cancel a workflow")


async def revert_workflow_to_review(ctx, conn, workflow_id: str, body: dict):
    return await _post(ctx, conn, f"/workflows/{workflow_id}/revertToReview", "revert a workflow to the review step", body)


async def list_workflow_schemas(ctx, conn, params: dict):
    return await _get(ctx, conn, "/workflows/schemas", "list all workflow schemas", params)


async def get_workflow_schema(ctx, conn, template_id: str):
    return await _get(ctx, conn, f"/workflows/schemas/{template_id}", "retrieve a workflow schema")


async def update_workflow_attributes(ctx, conn, workflow_id: str, body: dict):
    return await _patch(ctx, conn, f"/workflows/{workflow_id}/attributes", "update workflow attributes", body)


async def get_workflow_attachment(ctx, conn, workflow_id: str, attachment_id: str):
    return await _get(ctx, conn, f"/workflows/{workflow_id}/attachments/{attachment_id}", "retrieve a workflow attachment")


async def add_workflow_attachment(ctx, conn, workflow_id: str, body: dict):
    return await _post(ctx, conn, f"/workflows/{workflow_id}/attachments", "add a workflow attachment", body)


async def create_workflow_comment(ctx, conn, workflow_id: str, body: dict):
    return await _post(ctx, conn, f"/workflows/{workflow_id}/comments", "create a workflow comment", body)


async def send_signature_request(ctx, conn, workflow_id: str, body: dict):
    return await _post(ctx, conn, f"/workflows/{workflow_id}/sendForSignature", "send a signature request", body)


async def get_signature_status(ctx, conn, workflow_id: str):
    return await _get(ctx, conn, f"/workflows/{workflow_id}/signatureStatus", "read signature status")


async def update_approval(ctx, conn, workflow_id: str, step_id: str, body: dict):
    return await _post(ctx, conn, f"/workflows/{workflow_id}/steps/{step_id}/approval", "update an approval", body)


# ──────────────────────────────────────────────────────────────────────────
# Records
# ──────────────────────────────────────────────────────────────────────────

async def list_records(ctx, conn, params: dict):
    return await _get(ctx, conn, "/records", "list all records", params)


async def get_record(ctx, conn, record_id: str, params: dict):
    return await _get(ctx, conn, f"/records/{record_id}", "retrieve a record", params)


async def create_record(ctx, conn, body: dict):
    return await _post(ctx, conn, "/records", "create a record", body)


async def update_record(ctx, conn, record_id: str, body: dict):
    return await _patch(ctx, conn, f"/records/{record_id}", "update a record", body)


async def delete_record(ctx, conn, record_id: str):
    return await _delete(ctx, conn, f"/records/{record_id}", "delete a record")


async def get_records_schema(ctx, conn):
    return await _get(ctx, conn, "/records/schema", "retrieve the records schema")


async def get_record_attachment(ctx, conn, record_id: str, attachment_id: str):
    return await _get(ctx, conn, f"/records/{record_id}/attachments/{attachment_id}", "retrieve a record attachment")


async def add_record_attachment(ctx, conn, record_id: str, body: dict):
    return await _post(ctx, conn, f"/records/{record_id}/attachments", "add a record attachment", body)


async def delete_record_attachment(ctx, conn, record_id: str, attachment_id: str):
    return await _delete(ctx, conn, f"/records/{record_id}/attachments/{attachment_id}", "delete a record attachment")


async def apply_contract_action(ctx, conn, record_id: str, body: dict):
    return await _post(ctx, conn, f"/records/{record_id}/actions", "apply a contract action", body)


async def smart_import_record(ctx, conn, body: dict):
    return await _post(ctx, conn, "/records/smartImport", "create a record via smart import", body)


# ──────────────────────────────────────────────────────────────────────────
# Entities (counterparties)
# ──────────────────────────────────────────────────────────────────────────

async def list_entities(ctx, conn, params: dict):
    return await _get(ctx, conn, "/entities", "list entities", params)


async def get_entity(ctx, conn, entity_id: str):
    return await _get(ctx, conn, f"/entities/{entity_id}", "retrieve an entity")


async def create_entity(ctx, conn, body: dict):
    return await _post(ctx, conn, "/entities", "create an entity", body)


async def update_entity(ctx, conn, entity_id: str, body: dict):
    return await _patch(ctx, conn, f"/entities/{entity_id}", "update an entity", body)


async def delete_entity(ctx, conn, entity_id: str):
    return await _delete(ctx, conn, f"/entities/{entity_id}", "delete an entity")


async def list_relationship_types(ctx, conn):
    return await _get(ctx, conn, "/entities/relationshipTypes", "read relationship types")


# ──────────────────────────────────────────────────────────────────────────
# Obligations
# ──────────────────────────────────────────────────────────────────────────

async def list_obligations(ctx, conn, params: dict):
    return await _get(ctx, conn, "/obligations", "list obligations", params)


async def get_obligation(ctx, conn, obligation_id: str):
    return await _get(ctx, conn, f"/obligations/{obligation_id}", "retrieve an obligation")


async def create_obligation(ctx, conn, body: dict):
    return await _post(ctx, conn, "/obligations", "create an obligation", body)


async def update_obligation(ctx, conn, obligation_id: str, body: dict):
    return await _patch(ctx, conn, f"/obligations/{obligation_id}", "update an obligation", body)


async def delete_obligation(ctx, conn, obligation_id: str):
    return await _delete(ctx, conn, f"/obligations/{obligation_id}", "delete an obligation")


# ──────────────────────────────────────────────────────────────────────────
# Webhooks
# ──────────────────────────────────────────────────────────────────────────

async def list_webhooks(ctx, conn):
    return await _get(ctx, conn, "/webhooks", "list webhooks")


async def create_webhook(ctx, conn, body: dict):
    return await _post(ctx, conn, "/webhooks", "create a webhook", body)


async def update_webhook(ctx, conn, webhook_id: str, body: dict):
    return await _put(ctx, conn, f"/webhooks/{webhook_id}", "update a webhook", body)


async def delete_webhook(ctx, conn, webhook_id: str):
    return await _delete(ctx, conn, f"/webhooks/{webhook_id}", "delete a webhook")


# ──────────────────────────────────────────────────────────────────────────
# Export (reports) -- purchase-gated on Ironclad's side, see docstring in
# handlers_export.py
# ──────────────────────────────────────────────────────────────────────────

async def create_report(ctx, conn, body: dict):
    return await _post(ctx, conn, "/reports", "create a report export", body)


async def get_report(ctx, conn, report_id: str):
    return await _get(ctx, conn, f"/reports/{report_id}", "retrieve a report export")
