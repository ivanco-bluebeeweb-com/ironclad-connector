"""Chat functions for connection management: connect/disconnect/list saved
Ironclad OAuth Client companies. Built on ironclad_client.py / schemas.py,
same shape as MuleSoft/PagerDuty/Mirth Connect Connector's connection
section.
"""
from __future__ import annotations

import json
import uuid

from imperal_sdk import ActionResult

import ironclad_client as ic
from app import ext, chat
from schemas import (
    NoParams,
    ConnectIroncladParams, ProviderConnection, ProviderConnectionList,
    DisconnectIroncladParams, DeleteResult,
)

_SECRET_NAME = "ironclad_connections"


async def _load_connections(ctx) -> list[dict]:
    raw = await ctx.secrets.get(_SECRET_NAME)
    try:
        return json.loads(raw) if raw else []
    except Exception:
        return []


async def _save_connections(ctx, connections: list[dict]) -> None:
    await ctx.secrets.set(_SECRET_NAME, json.dumps(connections))


def _to_provider_connection(c: dict) -> ProviderConnection:
    region = c.get("region", "na1")
    return ProviderConnection(
        id=c.get("id", ""),
        title=c.get("label") or f"Ironclad ({region})",
        detail=f"{c.get('as_user_email', '')} · {region}",
    )


async def resolve_connection(ctx, connection_id: str = ""):
    """Resolve a connection_id (or the first saved connection) to a conn
    dict. Returns an ActionResult.error(...) instead if none match --
    callers must check `isinstance(result, ActionResult)`."""
    connections = await _load_connections(ctx)
    if not connections:
        return ActionResult.error("No Ironclad company connected yet. Use connect_ironclad first.")
    if connection_id:
        for c in connections:
            if c.get("id") == connection_id:
                return c
        return ActionResult.error(f"No saved Ironclad connection with id '{connection_id}'.")
    return connections[0]


@chat.function(
    "connect_ironclad",
    "Connect your own Ironclad CLM company using an OAuth Client (Client "
    "ID/Secret) registered in Ironclad's Company Settings > API, after "
    "checking it actually works.",
    action_type="write",
    chain_callable=True,
    data_model=ProviderConnection,
    event="ironclad-connector.connect_ironclad",
    effects=["create:connection"],
)
async def connect_ironclad(ctx, params: ConnectIroncladParams) -> ActionResult:
    """Verify and save a new Ironclad OAuth Client connection."""
    region = (params.region or "na1").strip().lower()
    if region not in ic.REGION_HOSTS:
        return ActionResult.error(f"Unknown region '{params.region}'. Use one of: na1, eu1, demo.")

    check = await ic.check_connection(ctx, params.client_id, params.client_secret, region, params.as_user_email)
    if not check.get("ok"):
        return ActionResult.error(check.get("error", "Could not verify the Ironclad OAuth Client."))

    connections = await _load_connections(ctx)
    entry = {
        "id": str(uuid.uuid4()),
        "client_id": params.client_id,
        "client_secret": params.client_secret,
        "as_user_email": params.as_user_email,
        "region": region,
        "label": params.label,
    }
    connections.append(entry)
    await _save_connections(ctx, connections)
    conn = _to_provider_connection(entry)
    return ActionResult.success(data=conn, summary=f"Connected to {conn.title}.")


@chat.function(
    "disconnect_ironclad",
    "Disconnect one Ironclad company. Nothing in Ironclad itself is "
    "changed; only the saved OAuth Client credentials here are deleted.",
    action_type="write",
    chain_callable=True,
    data_model=DeleteResult,
    event="ironclad-connector.disconnect_ironclad",
    effects=["delete:connection"],
)
async def disconnect_ironclad(ctx, params: DisconnectIroncladParams) -> ActionResult:
    """Remove a saved Ironclad connection by id."""
    connections = await _load_connections(ctx)
    remaining = [c for c in connections if c.get("id") != params.connection_id]
    if len(remaining) == len(connections):
        return ActionResult.error(f"No saved Ironclad connection with id '{params.connection_id}'.")
    await _save_connections(ctx, remaining)
    return ActionResult.success(data=DeleteResult(ok=True), summary="Ironclad connection removed.")


@chat.function(
    "list_connections",
    "List the connected Ironclad companies.",
    action_type="read",
    chain_callable=True,
    data_model=ProviderConnectionList,
    event="ironclad-connector.list_connections",
)
async def list_connections(ctx, params: NoParams) -> ActionResult:
    """List every saved Ironclad company connection."""
    connections = await _load_connections(ctx)
    items = [_to_provider_connection(c) for c in connections]
    return ActionResult.success(data=ProviderConnectionList(items=items), summary=f"{len(items)} connected Ironclad company(ies).")
