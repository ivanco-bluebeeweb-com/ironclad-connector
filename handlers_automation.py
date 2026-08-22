"""Imperal-side value-add (Tier 3): functionality beyond raw Ironclad
Public API parity that a real legal-ops/contracts team actually needs
day to day.

WHY audit_contract_health BUILDS ONE AGGREGATED REPORT INSTEAD OF
REQUIRING N CALLS.

Same shape as PagerDuty Connector's audit_account / Mirth Connect
Connector's audit_mirth_estate -- a single call an operator can run
before a board/leadership check-in to get one company-wide contract
health snapshot: how many workflows are actively moving, how many look
stalled (no update in the lookback window despite not being complete),
how many completed recently, and how many obligations are coming due --
without manually cross-referencing list_workflows/list_obligations by
hand.

WHY find_expiring_contracts EXISTS SEPARATELY FROM list_records.

Ironclad's own list_records supports filtering by a single property, but
finding "everything expiring soon" requires knowing which property holds
the expiration date (varies by record type/company configuration) and
doing date-window math client-side -- exactly the kind of repetitive,
error-prone task a value-add wrapper should absorb, same pattern as
ShipStation Connector's get_low_stock_report or Cin7 Core Connector's
get_dead_stock_report.

WHY bulk_tag_records EXISTS SEPARATELY FROM update_record.

Applying the same property values to many records in one call (e.g.
tagging every contract from a since-acquired subsidiary with a new
business-unit code) is a common bulk-migration/reorg task; Ironclad's own
API has no native bulk-update endpoint for records, so this loops
update_record and reports how many succeeded -- same "no native bulk
endpoint, so the connector builds one" precedent as MuleSoft Connector's
bulk_restart_cloudhub_applications.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from imperal_sdk import ActionResult

import ironclad_client as ic
from app import ext, chat
from handlers_connection import resolve_connection
from schemas import (
    AuditContractHealthParams, ContractHealthReport,
    FindExpiringContractsParams,
    BulkTagRecordsParams, BulkUpdateResult,
)
from schemas import RecordList, Record
import handlers_records as _hr


def _parse_ts(s: str):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


@chat.function(
    "audit_contract_health",
    "Build one aggregated health report across the connected Ironclad "
    "company: active vs stalled workflows, recently completed "
    "workflows, and obligations due in the next 30 days -- one call "
    "instead of manually cross-referencing several reads.",
    action_type="read",
    chain_callable=True,
    data_model=ContractHealthReport,
    event="ironclad-connector.audit_contract_health",
)
async def audit_contract_health(ctx, params: AuditContractHealthParams) -> ActionResult:
    """Build one aggregated contract-health report for the connected company."""
    conn = await resolve_connection(ctx, params.connection_id)
    if isinstance(conn, ActionResult):
        return conn
    cutoff = datetime.now(timezone.utc) - timedelta(days=params.lookback_days)

    wf_res = await ic.list_workflows(ctx, conn, {"page": 0, "pageSize": 50})
    wf_items = wf_res.get("list", wf_res if isinstance(wf_res, list) else [])
    if isinstance(wf_items, dict):
        wf_items = wf_items.get("list", [])

    active = 0
    stalled = 0
    completed_recent = 0
    for w in wf_items:
        status = str(w.get("status", w.get("currentStepName", ""))).lower()
        updated = _parse_ts(w.get("lastUpdated", w.get("updatedTs", "")))
        if status in ("completed", "complete", "signed"):
            if updated and updated >= cutoff:
                completed_recent += 1
            continue
        if status in ("cancelled", "canceled"):
            continue
        active += 1
        if updated and updated < cutoff:
            stalled += 1

    ob_res = await ic.list_obligations(ctx, conn, {"page": 0, "pageSize": 50})
    ob_items = ob_res.get("list", ob_res if isinstance(ob_res, list) else [])
    if isinstance(ob_items, dict):
        ob_items = ob_items.get("list", [])
    soon = datetime.now(timezone.utc) + timedelta(days=30)
    upcoming = 0
    for o in ob_items:
        due = _parse_ts(o.get("dueDate", ""))
        if due and datetime.now(timezone.utc) <= due <= soon:
            upcoming += 1

    summary = (
        f"{active} active workflow(s), {stalled} of which look stalled "
        f"(no update in {params.lookback_days}d). {completed_recent} "
        f"completed in the last {params.lookback_days}d. {upcoming} "
        f"obligation(s) due in the next 30 days."
    )
    report = ContractHealthReport(
        active_workflow_count=active,
        stalled_workflow_count=stalled,
        completed_last_period=completed_recent,
        upcoming_obligations_30d=upcoming,
        summary=summary,
    )
    return ActionResult.success(data=report, summary=summary)


@chat.function(
    "find_expiring_contracts",
    "Value-add report: scan records and flag every one whose "
    "agreement/expiration date falls within a given window from now "
    "-- absorbs the client-side date-window math Ironclad's own "
    "list_records filter doesn't do.",
    action_type="read",
    chain_callable=True,
    data_model=RecordList,
    event="ironclad-connector.find_expiring_contracts",
)
async def find_expiring_contracts(ctx, params: FindExpiringContractsParams) -> ActionResult:
    """Scan records and flag those expiring within a given window from now."""
    conn = await resolve_connection(ctx, params.connection_id)
    if isinstance(conn, ActionResult):
        return conn
    q: dict = {"page": 0, "pageSize": 50, "sortBy": "agreementDate", "sortDirection": "ASC"}
    if params.record_type:
        q["types"] = params.record_type
    res = await ic.list_records(ctx, conn, q)
    items = res.get("list", res if isinstance(res, list) else [])
    if isinstance(items, dict):
        items = items.get("list", [])

    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=params.within_days)
    expiring: list[Record] = []
    for r in items:
        exp = _parse_ts(r.get("agreementDate", "")) or _parse_ts(r.get("expirationDate", ""))
        if exp and now <= exp <= horizon:
            expiring.append(_hr._to_record(r))
    data = RecordList(items=expiring, total=len(expiring))
    return ActionResult.success(data=data, summary=f"{len(expiring)} contract(s) expiring within {params.within_days} day(s).")


@chat.function(
    "bulk_tag_records",
    "Apply the same property values to several existing records in "
    "one call -- e.g. tagging every contract from an acquired "
    "subsidiary with a new business-unit code. Ironclad's own API has "
    "no native bulk-update endpoint for records, so this loops "
    "update_record and reports how many succeeded.",
    action_type="write",
    chain_callable=True,
    data_model=BulkUpdateResult,
    event="ironclad-connector.bulk_tag_records",
    effects=["ironclad.records.bulk_updated"],
)
async def bulk_tag_records(ctx, params: BulkTagRecordsParams) -> ActionResult:
    """Apply the same property values to several existing records in one call."""
    conn = await resolve_connection(ctx, params.connection_id)
    if isinstance(conn, ActionResult):
        return conn
    try:
        props = json.loads(params.properties_json)
    except Exception:
        return ActionResult.error("properties_json must be valid JSON.")
    ids = [i.strip() for i in params.record_ids_csv.split(",") if i.strip()]
    updated = 0
    for rid in ids:
        try:
            await ic.update_record(ctx, conn, rid, {"properties": props})
            updated += 1
        except Exception:
            continue
    result = BulkUpdateResult(updated=updated)
    return ActionResult.success(data=result, summary=f"{updated} of {len(ids)} record(s) updated.")
