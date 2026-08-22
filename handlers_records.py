"""Chat functions for the Records domain: the repository of completed/
signed agreements, their metadata properties, attachments, and post-
signature contract actions (renew, terminate, amend).

WHY RECORDS IS A SEPARATE DOMAIN FROM WORKFLOWS, NOT ONE UNIFIED
"CONTRACTS" CONCEPT.

Ironclad's own conceptual split (developer.ironcladapp.com/reference/
getting-started-api, confirmed 2026-08-22, CONNECTOR_DISCOVERY.md SS2):
Workflows are the in-progress approval PROCESS; Records are the
completed, signed AGREEMENT once that process finishes (or an agreement
migrated in directly, bypassing a workflow entirely via smart import or
manual creation). A workflow's completion creates a record, but a record
can also exist standalone -- so the two APIs, and this module split,
mirror that real separation rather than papering over it.

WHY apply_contract_action IS ITS OWN FUNCTION, NOT PART OF update_record.

Contract actions (renew/terminate/amend) are Ironclad's own
company-configured action set per record type (see CONNECTOR_DISCOVERY.md
SS5) -- semantically a lifecycle EVENT on the record, not a plain field
edit, and Ironclad models it as its own endpoint
(`POST /records/{id}/actions`) precisely for that reason.

WHY smart_import_record IS EXPOSED SEPARATELY FROM create_record.

Smart Import (`POST /records/smartImport`) asks Ironclad's own AI to read
an already-signed document and extract record properties automatically --
a fundamentally different capability from create_record's explicit
property values, and worth exposing as a distinct, discoverable action
for bulk-migrating a legacy contract archive (see CONNECTOR_DISCOVERY.md
SS6, also referenced in the official Entities/Records migration guide).
"""
from __future__ import annotations

import json

from imperal_sdk import ActionResult

import ironclad_client as ic
from app import ext, chat
from handlers_connection import resolve_connection
from schemas import (
    ListRecordsParams, GetRecordParams, CreateRecordParams,
    UpdateRecordParams, DeleteRecordParams,
    GetRecordAttachmentParams, AddRecordAttachmentParams,
    DeleteRecordAttachmentParams, ApplyContractActionParams,
    SmartImportRecordParams, NoParams,
    Record, RecordList, RawResult, DeleteResult,
)


def _to_record(r: dict) -> Record:
    return Record(
        id=r.get("id", ""),
        name=r.get("name", r.get("title", "")),
        record_type=r.get("type", r.get("recordType", "")),
        agreement_date=r.get("agreementDate", ""),
        last_updated=r.get("lastUpdated", ""),
        raw_json=json.dumps(r),
    )


@chat.function(
    "list_records",
    "List records (completed/signed agreements) in the connected "
    "Ironclad company, with optional filtering by type, last-updated "
    "timestamp, and one property value.",
    action_type="read",
    chain_callable=True,
    data_model=RecordList,
    event="ironclad-connector.list_records",
)
async def list_records(ctx, params: ListRecordsParams) -> ActionResult:
    """List completed/signed records, optionally filtered by type/property/last-updated."""
    conn = await resolve_connection(ctx, params.connection_id)
    if isinstance(conn, ActionResult):
        return conn
    q: dict = {"page": params.page, "pageSize": params.page_size, "sortBy": params.sort_field, "sortDirection": params.sort_direction}
    if params.types:
        q["types"] = params.types
    if params.last_updated:
        q["lastUpdated"] = params.last_updated
    if params.filter_property:
        q["filter[properties][%s]" % params.filter_property] = params.filter_value
    res = await ic.list_records(ctx, conn, q)
    items = res.get("list", res.get("data", res if isinstance(res, list) else []))
    if isinstance(items, dict):
        items = items.get("list", [])
    total = res.get("total", len(items)) if isinstance(res, dict) else len(items)
    data = RecordList(items=[_to_record(r) for r in items], total=total)
    return ActionResult.success(data=data, summary=f"{len(data.items)} record(s).")


@chat.function(
    "get_record",
    "Read one record (completed/signed agreement) in full, including "
    "its properties and attachment list.",
    action_type="read",
    chain_callable=True,
    data_model=Record,
    event="ironclad-connector.get_record",
)
async def get_record(ctx, params: GetRecordParams) -> ActionResult:
    """Read one record by id."""
    conn = await resolve_connection(ctx, params.connection_id)
    if isinstance(conn, ActionResult):
        return conn
    q = {"hydrateEntities": "true"} if params.hydrate_entities else {}
    res = await ic.get_record(ctx, conn, params.record_id, q)
    rec = _to_record(res)
    return ActionResult.success(data=rec, summary=f"Record '{rec.name or rec.id}'.")


@chat.function(
    "get_records_schema",
    "Read the Records schema: every record type and its configured "
    "properties/attributes, needed before create_record or "
    "update_record.",
    action_type="read",
    chain_callable=True,
    data_model=RawResult,
    event="ironclad-connector.get_records_schema",
)
async def get_records_schema(ctx, params: NoParams) -> ActionResult:
    """Read every record type and its configured properties/attributes for the connected Ironclad company."""
    conn = await resolve_connection(ctx, "")
    if isinstance(conn, ActionResult):
        return conn
    res = await ic.get_records_schema(ctx, conn)
    return ActionResult.success(data=RawResult(raw_json=json.dumps(res)), summary="Records schema retrieved.")


@chat.function(
    "create_record",
    "Create a new record directly (e.g. migrating a legacy signed "
    "agreement into Ironclad without running it through a workflow "
    "first).",
    action_type="write",
    chain_callable=True,
    data_model=Record,
    event="ironclad-connector.create_record",
    effects=["ironclad.record.created"],
)
async def create_record(ctx, params: CreateRecordParams) -> ActionResult:
    """Create a new record with explicit property values."""
    conn = await resolve_connection(ctx, params.connection_id)
    if isinstance(conn, ActionResult):
        return conn
    try:
        props = json.loads(params.properties_json) if params.properties_json else {}
    except Exception:
        return ActionResult.error("properties_json must be valid JSON, e.g. {\"counterpartyName\": \"Acme Corp\"}.")
    body = {"name": params.name, "type": params.record_type, "properties": props}
    if params.parent_record_id:
        body["parentRecordId"] = params.parent_record_id
    res = await ic.create_record(ctx, conn, body)
    rec = _to_record(res)
    return ActionResult.success(data=rec, summary=f"Record '{rec.name}' created.")


@chat.function(
    "update_record",
    "Update selected property values on an existing record. Only the "
    "properties you pass change.",
    action_type="write",
    chain_callable=True,
    data_model=Record,
    event="ironclad-connector.update_record",
    effects=["ironclad.record.updated"],
)
async def update_record(ctx, params: UpdateRecordParams) -> ActionResult:
    """Update selected property values on an existing record."""
    conn = await resolve_connection(ctx, params.connection_id)
    if isinstance(conn, ActionResult):
        return conn
    try:
        props = json.loads(params.properties_json)
    except Exception:
        return ActionResult.error("properties_json must be valid JSON.")
    res = await ic.update_record(ctx, conn, params.record_id, {"properties": props})
    rec = _to_record(res)
    return ActionResult.success(data=rec, summary=f"Record '{rec.id}' updated.")


@chat.function(
    "delete_record",
    "Permanently delete a record. Cannot be undone through the API -- "
    "use with care.",
    action_type="destructive",
    chain_callable=True,
    data_model=DeleteResult,
    event="ironclad-connector.delete_record",
    effects=["ironclad.record.deleted"],
)
async def delete_record(ctx, params: DeleteRecordParams) -> ActionResult:
    """Permanently delete a record by id."""
    conn = await resolve_connection(ctx, params.connection_id)
    if isinstance(conn, ActionResult):
        return conn
    await ic.delete_record(ctx, conn, params.record_id)
    return ActionResult.success(data=DeleteResult(ok=True), summary=f"Record '{params.record_id}' deleted.")


@chat.function(
    "get_record_attachment",
    "Read one record attachment's metadata and download link.",
    action_type="read",
    chain_callable=True,
    data_model=RawResult,
    event="ironclad-connector.get_record_attachment",
)
async def get_record_attachment(ctx, params: GetRecordAttachmentParams) -> ActionResult:
    """Read one record attachment's metadata/download link."""
    conn = await resolve_connection(ctx, params.connection_id)
    if isinstance(conn, ActionResult):
        return conn
    res = await ic.get_record_attachment(ctx, conn, params.record_id, params.attachment_id)
    return ActionResult.success(data=RawResult(raw_json=json.dumps(res)), summary="Attachment metadata retrieved.")


@chat.function(
    "add_record_attachment",
    "Attach a file to an existing record by giving Ironclad a publicly "
    "reachable URL to fetch it from.",
    action_type="write",
    chain_callable=True,
    data_model=RawResult,
    event="ironclad-connector.add_record_attachment",
    effects=["ironclad.record.attachment_added"],
)
async def add_record_attachment(ctx, params: AddRecordAttachmentParams) -> ActionResult:
    """Attach a publicly reachable file URL to an existing record."""
    conn = await resolve_connection(ctx, params.connection_id)
    if isinstance(conn, ActionResult):
        return conn
    res = await ic.add_record_attachment(ctx, conn, params.record_id, {"fileName": params.file_name, "url": params.file_url})
    return ActionResult.success(data=RawResult(raw_json=json.dumps(res)), summary=f"Attachment '{params.file_name}' added to record '{params.record_id}'.")


@chat.function(
    "delete_record_attachment",
    "Permanently remove an attachment from a record. Cannot be undone.",
    action_type="destructive",
    chain_callable=True,
    data_model=DeleteResult,
    event="ironclad-connector.delete_record_attachment",
    effects=["ironclad.record.attachment_deleted"],
)
async def delete_record_attachment(ctx, params: DeleteRecordAttachmentParams) -> ActionResult:
    """Permanently remove an attachment from a record."""
    conn = await resolve_connection(ctx, params.connection_id)
    if isinstance(conn, ActionResult):
        return conn
    await ic.delete_record_attachment(ctx, conn, params.record_id, params.attachment_id)
    return ActionResult.success(data=DeleteResult(ok=True), summary=f"Attachment '{params.attachment_id}' removed from record '{params.record_id}'.")


@chat.function(
    "apply_contract_action",
    "Apply a post-signature contract action to a record -- e.g. renew, "
    "terminate, or amend -- using the action types configured for that "
    "record's type.",
    action_type="write",
    chain_callable=True,
    data_model=RawResult,
    event="ironclad-connector.apply_contract_action",
    effects=["ironclad.record.action_applied"],
)
async def apply_contract_action(ctx, params: ApplyContractActionParams) -> ActionResult:
    """Apply a company-configured lifecycle action (renew/terminate/amend) to a record."""
    conn = await resolve_connection(ctx, params.connection_id)
    if isinstance(conn, ActionResult):
        return conn
    try:
        props = json.loads(params.properties_json) if params.properties_json else {}
    except Exception:
        return ActionResult.error("properties_json must be valid JSON.")
    body = {"actionType": params.action_type, "properties": props}
    res = await ic.apply_contract_action(ctx, conn, params.record_id, body)
    return ActionResult.success(data=RawResult(raw_json=json.dumps(res)), summary=f"Action '{params.action_type}' applied to record '{params.record_id}'.")


@chat.function(
    "smart_import_record",
    "Create a record from an already-signed document by URL, using "
    "Ironclad's own AI to extract its metadata automatically -- ideal "
    "for bulk-migrating a legacy contract archive.",
    action_type="write",
    chain_callable=True,
    data_model=Record,
    event="ironclad-connector.smart_import_record",
    effects=["ironclad.record.created"],
)
async def smart_import_record(ctx, params: SmartImportRecordParams) -> ActionResult:
    """Create a record from a signed document URL using Ironclad's Smart Import AI extraction."""
    conn = await resolve_connection(ctx, params.connection_id)
    if isinstance(conn, ActionResult):
        return conn
    body = {"name": params.name, "type": params.record_type, "url": params.file_url}
    res = await ic.smart_import_record(ctx, conn, body)
    rec = _to_record(res)
    return ActionResult.success(data=rec, summary=f"Record '{rec.name}' smart-imported.")
