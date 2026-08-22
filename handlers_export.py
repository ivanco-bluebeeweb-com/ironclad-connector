"""Chat functions for the Export (Reports) domain: on-demand data exports
of records/workflows for offline analysis or archival.

WHY THIS IS ITS OWN SMALL MODULE, NOT FOLDED INTO handlers_records.py.

Ironclad's own Getting Started guide flags Reports/Exports as a
SEPARATELY GATED capability -- available only to companies with the
relevant plan/feature enabled, unlike Workflows/Records/Entities which
are universally available on any Public API-enabled company (confirmed
2026-08-22, developer.ironcladapp.com/reference/getting-started-api,
CONNECTOR_DISCOVERY.md SS2). Exposing it as its own module keeps that
gating visible: a 403 here plausibly means "not on your plan", not "your
OAuth Client is broken" -- callers hitting FORBIDDEN specifically for
these two functions should check their Ironclad plan first.
"""
from __future__ import annotations

import json

from imperal_sdk import ActionResult

import ironclad_client as ic
from app import ext, chat
from handlers_connection import resolve_connection
from schemas import CreateReportParams, GetReportParams, Report


def _to_report(r: dict) -> Report:
    return Report(
        id=r.get("id", ""),
        status=r.get("status", ""),
        download_url=r.get("downloadUrl", r.get("url", "")),
        raw_json=json.dumps(r),
    )


@chat.function(
    "create_report",
    "Start a data export (report) of records or workflows for offline "
    "analysis. Requires the Reports/Exports feature to be enabled on "
    "your Ironclad plan -- a permission error here likely means it isn't.",
    action_type="write",
    chain_callable=True,
    data_model=Report,
    event="ironclad-connector.create_report",
    effects=["ironclad.report.created"],
)
async def create_report(ctx, params: CreateReportParams) -> ActionResult:
    """Start a data export (report) of records or workflows."""
    conn = await resolve_connection(ctx, params.connection_id)
    if isinstance(conn, ActionResult):
        return conn
    try:
        filters = json.loads(params.filters_json) if params.filters_json else {}
    except Exception:
        return ActionResult.error("filters_json must be valid JSON.")
    body = {"type": params.report_type, "filters": filters}
    res = await ic.create_report(ctx, conn, body)
    rep = _to_report(res)
    return ActionResult.success(data=rep, summary=f"Report export started (id {rep.id}).")


@chat.function(
    "get_report",
    "Check the status of a data export and get its download URL once ready.",
    action_type="read",
    chain_callable=True,
    data_model=Report,
    event="ironclad-connector.get_report",
)
async def get_report(ctx, params: GetReportParams) -> ActionResult:
    """Check the status of a data export and get its download URL once ready."""
    conn = await resolve_connection(ctx, params.connection_id)
    if isinstance(conn, ActionResult):
        return conn
    res = await ic.get_report(ctx, conn, params.report_id)
    return ActionResult.success(data=_to_report(res), summary="Report status retrieved.")
