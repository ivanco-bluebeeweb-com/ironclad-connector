"""Chat functions for the Obligations domain: post-signature commitments
tied to a record -- e.g. renewal reminders, SLA deliverables, recurring
compliance deadlines -- that outlive the workflow/signature process
itself.

WHY OBLIGATIONS IS ITS OWN DOMAIN, NOT A RECORD PROPERTY.

Ironclad models obligations as first-class objects LINKED TO a record
rather than a field ON a record (public.obligations.* scope group,
confirmed 2026-08-22 via the full OAuth scopes list, CONNECTOR_DISCOVERY.md
SS5) -- a single record (e.g. an MSA) can carry many independent
obligations with their own due dates and lifecycles (a quarterly report,
an annual price review, a renewal notice window), which a single record
property could not represent cleanly.
"""
from __future__ import annotations

import json

from imperal_sdk import ActionResult

import ironclad_client as ic
from app import ext, chat
from handlers_connection import resolve_connection
from schemas import (
    ListObligationsParams, GetObligationParams, CreateObligationParams,
    UpdateObligationParams, DeleteObligationParams,
    Obligation, ObligationList, DeleteResult,
)


def _to_obligation(o: dict) -> Obligation:
    return Obligation(
        id=o.get("id", ""),
        name=o.get("name", ""),
        record_id=o.get("recordId", ""),
        due_date=o.get("dueDate", ""),
        raw_json=json.dumps(o),
    )


@chat.function(
    "list_obligations",
    "List post-signature obligations (renewal reminders, SLA "
    "deliverables, compliance deadlines), optionally filtered to one "
    "record.",
    action_type="read",
    chain_callable=True,
    data_model=ObligationList,
    event="ironclad-connector.list_obligations",
)
async def list_obligations(ctx, params: ListObligationsParams) -> ActionResult:
    """List post-signature obligations, optionally filtered to one record."""
    conn = await resolve_connection(ctx, params.connection_id)
    if isinstance(conn, ActionResult):
        return conn
    q: dict = {"page": params.page, "pageSize": params.page_size}
    if params.record_id:
        q["recordId"] = params.record_id
    res = await ic.list_obligations(ctx, conn, q)
    items = res.get("list", res.get("data", res if isinstance(res, list) else []))
    if isinstance(items, dict):
        items = items.get("list", [])
    total = res.get("total", len(items)) if isinstance(res, dict) else len(items)
    data = ObligationList(items=[_to_obligation(o) for o in items], total=total)
    return ActionResult.success(data=data, summary=f"{len(data.items)} obligation(s).")


@chat.function(
    "get_obligation",
    "Read one obligation in full.",
    action_type="read",
    chain_callable=True,
    data_model=Obligation,
    event="ironclad-connector.get_obligation",
)
async def get_obligation(ctx, params: GetObligationParams) -> ActionResult:
    """Read one obligation's full details."""
    conn = await resolve_connection(ctx, params.connection_id)
    if isinstance(conn, ActionResult):
        return conn
    res = await ic.get_obligation(ctx, conn, params.obligation_id)
    return ActionResult.success(data=_to_obligation(res), summary="Obligation retrieved.")


@chat.function(
    "create_obligation",
    "Create a new obligation linked to an existing record -- a "
    "deadline or deliverable that outlives the signature process.",
    action_type="write",
    chain_callable=True,
    data_model=Obligation,
    event="ironclad-connector.create_obligation",
    effects=["ironclad.obligation.created"],
)
async def create_obligation(ctx, params: CreateObligationParams) -> ActionResult:
    """Create a new obligation on an existing record."""
    conn = await resolve_connection(ctx, params.connection_id)
    if isinstance(conn, ActionResult):
        return conn
    try:
        props = json.loads(params.properties_json) if params.properties_json else {}
    except Exception:
        return ActionResult.error("properties_json must be valid JSON.")
    body = {"name": params.name, "recordId": params.record_id, "properties": props}
    if params.due_date:
        body["dueDate"] = params.due_date
    res = await ic.create_obligation(ctx, conn, body)
    obl = _to_obligation(res)
    return ActionResult.success(data=obl, summary=f"Obligation '{obl.name}' created.")


@chat.function(
    "update_obligation",
    "Update selected property values of an existing obligation. Only "
    "the given properties change.",
    action_type="write",
    chain_callable=True,
    data_model=Obligation,
    event="ironclad-connector.update_obligation",
    effects=["ironclad.obligation.updated"],
)
async def update_obligation(ctx, params: UpdateObligationParams) -> ActionResult:
    """Update selected property values of an existing obligation."""
    conn = await resolve_connection(ctx, params.connection_id)
    if isinstance(conn, ActionResult):
        return conn
    try:
        props = json.loads(params.properties_json)
    except Exception:
        return ActionResult.error("properties_json must be valid JSON.")
    res = await ic.update_obligation(ctx, conn, params.obligation_id, {"properties": props})
    return ActionResult.success(data=_to_obligation(res), summary="Obligation updated.")


@chat.function(
    "delete_obligation",
    "Permanently delete an obligation. Cannot be undone.",
    action_type="destructive",
    chain_callable=True,
    data_model=DeleteResult,
    event="ironclad-connector.delete_obligation",
    effects=["ironclad.obligation.deleted"],
)
async def delete_obligation(ctx, params: DeleteObligationParams) -> ActionResult:
    """Permanently delete an obligation."""
    conn = await resolve_connection(ctx, params.connection_id)
    if isinstance(conn, ActionResult):
        return conn
    await ic.delete_obligation(ctx, conn, params.obligation_id)
    return ActionResult.success(data=DeleteResult(ok=True), summary="Obligation deleted.")
