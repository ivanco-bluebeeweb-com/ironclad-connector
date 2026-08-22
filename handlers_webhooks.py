"""Chat functions for the Webhooks domain: event subscriptions that push
workflow/record/obligation lifecycle events to an external HTTPS endpoint
in real time, instead of a caller having to poll list_workflows/
list_records on a schedule.

WHY THIS EXISTS ALONGSIDE POLLING-STYLE list_workflows/list_records.

Ironclad's Public API documents webhook event types spanning workflow
launch/completion/cancellation, record creation/update, and obligation
due-date events (public.webhooks.* scope group, confirmed 2026-08-22 via
the full OAuth scopes list, CONNECTOR_DISCOVERY.md SS5) -- the same
"poll vs push" duality every other event-capable connector in this
portfolio exposes (e.g. HubSpot/Shopify/Stripe Connector's webhook
subscriptions alongside their list_* reads).
"""
from __future__ import annotations

import json

from imperal_sdk import ActionResult

import ironclad_client as ic
from app import ext, chat
from handlers_connection import resolve_connection
from schemas import (
    CreateWebhookParams, UpdateWebhookParams, DeleteWebhookParams,
    Webhook, WebhookList, DeleteResult, NoParams,
)


def _to_webhook(w: dict) -> Webhook:
    return Webhook(
        id=w.get("id", ""),
        target_url=w.get("targetUrl", w.get("url", "")),
        events=w.get("events", []),
    )


@chat.function(
    "list_webhooks",
    "List webhook subscriptions configured on the connected Ironclad company.",
    action_type="read",
    chain_callable=True,
    data_model=WebhookList,
    event="ironclad-connector.list_webhooks",
)
async def list_webhooks(ctx, params: NoParams) -> ActionResult:
    """List webhook subscriptions configured on the connected Ironclad company."""
    conn = await resolve_connection(ctx)
    if isinstance(conn, ActionResult):
        return conn
    res = await ic.list_webhooks(ctx, conn)
    items = res.get("list", res if isinstance(res, list) else [])
    data = WebhookList(items=[_to_webhook(w) for w in items])
    return ActionResult.success(data=data, summary=f"{len(data.items)} webhook(s).")


@chat.function(
    "create_webhook",
    "Subscribe to Ironclad workflow/record/obligation lifecycle events "
    "-- Ironclad will POST event payloads to your target URL as they "
    "happen.",
    action_type="write",
    chain_callable=True,
    data_model=Webhook,
    event="ironclad-connector.create_webhook",
    effects=["ironclad.webhook.created"],
)
async def create_webhook(ctx, params: CreateWebhookParams) -> ActionResult:
    """Subscribe to Ironclad lifecycle events via a target URL."""
    conn = await resolve_connection(ctx, params.connection_id)
    if isinstance(conn, ActionResult):
        return conn
    events = [e.strip() for e in params.events_csv.split(",") if e.strip()]
    body = {"targetUrl": params.target_url, "events": events}
    if params.secret:
        body["secret"] = params.secret
    res = await ic.create_webhook(ctx, conn, body)
    wh = _to_webhook(res)
    return ActionResult.success(data=wh, summary=f"Webhook created for {wh.target_url}.")


@chat.function(
    "update_webhook",
    "Update an existing webhook's target URL and/or subscribed events. "
    "Only the given fields change.",
    action_type="write",
    chain_callable=True,
    data_model=Webhook,
    event="ironclad-connector.update_webhook",
    effects=["ironclad.webhook.updated"],
)
async def update_webhook(ctx, params: UpdateWebhookParams) -> ActionResult:
    """Update an existing webhook's target URL and/or subscribed events."""
    conn = await resolve_connection(ctx, params.connection_id)
    if isinstance(conn, ActionResult):
        return conn
    body: dict = {}
    if params.target_url:
        body["targetUrl"] = params.target_url
    if params.events_csv:
        body["events"] = [e.strip() for e in params.events_csv.split(",") if e.strip()]
    res = await ic.update_webhook(ctx, conn, params.webhook_id, body)
    return ActionResult.success(data=_to_webhook(res), summary="Webhook updated.")


@chat.function(
    "delete_webhook",
    "Permanently remove a webhook subscription. Cannot be undone.",
    action_type="destructive",
    chain_callable=True,
    data_model=DeleteResult,
    event="ironclad-connector.delete_webhook",
    effects=["ironclad.webhook.deleted"],
)
async def delete_webhook(ctx, params: DeleteWebhookParams) -> ActionResult:
    """Permanently remove a webhook subscription."""
    conn = await resolve_connection(ctx, params.connection_id)
    if isinstance(conn, ActionResult):
        return conn
    await ic.delete_webhook(ctx, conn, params.webhook_id)
    return ActionResult.success(data=DeleteResult(ok=True), summary="Webhook deleted.")
