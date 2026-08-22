"""Chat functions for the Entities domain: Ironclad's own counterparty/
contact repository (companies and individuals your organization contracts
with), plus relationship types linking entities to each other.

WHY ENTITIES EXISTS AS A SEPARATE DOMAIN FROM RECORDS/WORKFLOWS.

Entities is Ironclad's structured counterparty CRM layer -- a company can
maintain ONE canonical "Acme Corp" entity referenced by many records and
workflows, instead of counterparty name being a free-text field repeated
on every contract (developer.ironcladapp.com/docs/entities-integration-guide,
confirmed 2026-08-22, CONNECTOR_DISCOVERY.md SS5). Exposing it as its own
domain lets an integration sync an upstream CRM's account list into
Ironclad entities once, then reference those entity ids from records/
workflows -- exactly the migration pattern Ironclad's own integration
guide describes.
"""
from __future__ import annotations

import json

from imperal_sdk import ActionResult

import ironclad_client as ic
from app import ext, chat
from handlers_connection import resolve_connection
from schemas import (
    ListEntitiesParams, GetEntityParams, CreateEntityParams,
    UpdateEntityParams, DeleteEntityParams,
    Entity_, EntityList, RawResult, DeleteResult, NoParams,
)


def _to_entity(e: dict) -> Entity_:
    return Entity_(
        id=e.get("id", ""),
        name=e.get("name", ""),
        entity_type=e.get("type", e.get("entityType", "")),
        raw_json=json.dumps(e),
    )


@chat.function(
    "list_entities",
    "List counterparty/contact entities (companies and individuals) "
    "registered in the connected Ironclad company.",
    action_type="read",
    chain_callable=True,
    data_model=EntityList,
    event="ironclad-connector.list_entities",
)
async def list_entities(ctx, params: ListEntitiesParams) -> ActionResult:
    """List counterparty/contact entities, optionally filtered by type."""
    conn = await resolve_connection(ctx, params.connection_id)
    if isinstance(conn, ActionResult):
        return conn
    q: dict = {"page": params.page, "pageSize": params.page_size}
    if params.entity_type:
        q["type"] = params.entity_type
    res = await ic.list_entities(ctx, conn, q)
    items = res.get("list", res.get("data", res if isinstance(res, list) else []))
    if isinstance(items, dict):
        items = items.get("list", [])
    total = res.get("total", len(items)) if isinstance(res, dict) else len(items)
    data = EntityList(items=[_to_entity(e) for e in items], total=total)
    return ActionResult.success(data=data, summary=f"{len(data.items)} entity(ies).")


@chat.function(
    "get_entity",
    "Read one counterparty/contact entity in full.",
    action_type="read",
    chain_callable=True,
    data_model=Entity_,
    event="ironclad-connector.get_entity",
)
async def get_entity(ctx, params: GetEntityParams) -> ActionResult:
    """Read one entity by id."""
    conn = await resolve_connection(ctx, params.connection_id)
    if isinstance(conn, ActionResult):
        return conn
    res = await ic.get_entity(ctx, conn, params.entity_id)
    ent = _to_entity(res)
    return ActionResult.success(data=ent, summary=f"Entity '{ent.name or ent.id}'.")


@chat.function(
    "create_entity",
    "Create a new counterparty/contact entity (a company or individual "
    "your organization contracts with).",
    action_type="write",
    chain_callable=True,
    data_model=Entity_,
    event="ironclad-connector.create_entity",
    effects=["ironclad.entity.created"],
)
async def create_entity(ctx, params: CreateEntityParams) -> ActionResult:
    """Create a new counterparty/contact entity."""
    conn = await resolve_connection(ctx, params.connection_id)
    if isinstance(conn, ActionResult):
        return conn
    try:
        props = json.loads(params.properties_json) if params.properties_json else {}
    except Exception:
        return ActionResult.error("properties_json must be valid JSON.")
    body = {"name": params.name, "type": params.entity_type, "properties": props}
    res = await ic.create_entity(ctx, conn, body)
    ent = _to_entity(res)
    return ActionResult.success(data=ent, summary=f"Entity '{ent.name}' created.")


@chat.function(
    "update_entity",
    "Update selected property values of an existing entity. Only the "
    "given properties change.",
    action_type="write",
    chain_callable=True,
    data_model=Entity_,
    event="ironclad-connector.update_entity",
    effects=["ironclad.entity.updated"],
)
async def update_entity(ctx, params: UpdateEntityParams) -> ActionResult:
    """Update selected property values on an existing entity."""
    conn = await resolve_connection(ctx, params.connection_id)
    if isinstance(conn, ActionResult):
        return conn
    try:
        props = json.loads(params.properties_json)
    except Exception:
        return ActionResult.error("properties_json must be valid JSON.")
    res = await ic.update_entity(ctx, conn, params.entity_id, {"properties": props})
    ent = _to_entity(res)
    return ActionResult.success(data=ent, summary=f"Entity '{ent.name or ent.id}' updated.")


@chat.function(
    "delete_entity",
    "Permanently delete a counterparty/contact entity. Cannot be undone "
    "-- records/workflows referencing it will lose that link.",
    action_type="destructive",
    chain_callable=True,
    data_model=DeleteResult,
    event="ironclad-connector.delete_entity",
    effects=["ironclad.entity.deleted"],
)
async def delete_entity(ctx, params: DeleteEntityParams) -> ActionResult:
    """Permanently delete an entity by id."""
    conn = await resolve_connection(ctx, params.connection_id)
    if isinstance(conn, ActionResult):
        return conn
    await ic.delete_entity(ctx, conn, params.entity_id)
    return ActionResult.success(data=DeleteResult(ok=True), summary=f"Entity '{params.entity_id}' deleted.")


@chat.function(
    "list_relationship_types",
    "List the relationship types available for linking entities to each "
    "other (e.g. 'Parent Company', 'Subsidiary').",
    action_type="read",
    chain_callable=True,
    data_model=RawResult,
    event="ironclad-connector.list_relationship_types",
)
async def list_relationship_types(ctx, params: NoParams) -> ActionResult:
    """List entity relationship types configured on the connected Ironclad company."""
    conn = await resolve_connection(ctx)
    if isinstance(conn, ActionResult):
        return conn
    res = await ic.list_relationship_types(ctx, conn)
    return ActionResult.success(data=RawResult(raw_json=json.dumps(res)), summary="Relationship types retrieved.")
