"""Chat functions for the Workflows domain: active/in-progress contract
approval processes -- launch, list, inspect, cancel, revert, act on
approvals, attach files, comment, request signatures, and read/list
workflow design schemas (template metadata + attribute ids needed to
launch correctly).

WHY LAUNCH IS SPLIT INTO SYNC vs ASYNC vs BULK, MATCHING IRONCLAD'S OWN
THREE ENDPOINTS.

Ironclad's Public API exposes `POST /workflows` (synchronous, blocks
until the workflow is created), `POST /workflows/async` (non-blocking,
returns immediately) and a documented bulk-launch pattern
(developer.ironcladapp.com/docs/bulk-launch-a-workflow) -- confirmed
during Discovery 2026-08-22 (CONNECTOR_DISCOVERY.md SS4). The async form
is Ironclad's own documented recommendation whenever files are attached
to the launch (large uploads can otherwise time out the sync call), and
bulk_launch_workflow lets a caller launch many similar workflows (e.g.
one NDA per new hire) in a single call instead of N round trips.

WHY WORKFLOW ATTRIBUTE VALUES ARE PASSED AS A RAW JSON STRING, NOT
INDIVIDUAL TYPED FIELDS.

Every Ironclad company designs its own custom workflow templates with
arbitrary attribute ids/types (see CONNECTOR_DISCOVERY.md SS5, "Field
Types Supported for Workflows") -- there is no fixed schema a generic
connector could hardcode. get_workflow_schema lets the caller discover a
template's actual attribute ids/types before calling launch_workflow,
same "discover-then-act" shape as HubSpot Connector's
create_property/create_object pairing for custom CRM properties.
"""
from __future__ import annotations

import json

from imperal_sdk import ActionResult

import ironclad_client as ic
from app import ext, chat
from handlers_connection import resolve_connection
from schemas import (
    ListWorkflowsParams, GetWorkflowParams, LaunchWorkflowParams,
    LaunchWorkflowAsyncParams, BulkLaunchWorkflowParams,
    CancelWorkflowParams, RevertWorkflowToReviewParams,
    ListWorkflowSchemasParams, GetWorkflowSchemaParams,
    UpdateWorkflowAttributesParams, GetWorkflowAttachmentParams,
    AddWorkflowAttachmentParams, CreateWorkflowCommentParams,
    SendSignatureRequestParams, GetSignatureStatusParams,
    UpdateApprovalParams,
    Workflow, WorkflowList, RawResult, DeleteResult,
)


def _to_workflow(w: dict) -> Workflow:
    return Workflow(
        id=w.get("id", ""),
        name=w.get("name", w.get("title", "")),
        status=w.get("status", w.get("currentStepName", "")),
        template_id=w.get("templateId", ""),
        created_at=w.get("createdTs", w.get("created", "")),
        raw_json=json.dumps(w),
    )


def _parse_json_field(raw: str, field: str) -> dict | ActionResult:
    try:
        val = json.loads(raw) if raw else {}
        if not isinstance(val, dict):
            raise ValueError
        return val
    except Exception:
        return ActionResult.error(f"'{field}' must be a valid JSON object, e.g. {{\"key\": \"value\"}}.")


@chat.function(
    "list_all_workflows",
    "List active/in-progress Ironclad workflows (contracts currently "
    "moving through approval, not yet completed records). Paginated.",
    action_type="read",
    chain_callable=True,
    data_model=WorkflowList,
    event="ironclad-connector.list_all_workflows",
)
async def list_all_workflows(ctx, params: ListWorkflowsParams) -> ActionResult:
    """List active/in-progress workflows, optionally filtered by status/template/last-updated."""
    conn = await resolve_connection(ctx, params.connection_id)
    if isinstance(conn, ActionResult):
        return conn
    q: dict = {"page": params.page, "pageSize": params.page_size}
    if params.status:
        q["status"] = params.status
    if params.template_id:
        q["templateId"] = params.template_id
    if params.last_updated:
        q["lastUpdated"] = params.last_updated
    res = await ic.list_workflows(ctx, conn, q)
    items = res.get("list", res.get("data", res if isinstance(res, list) else []))
    if isinstance(items, dict):
        items = items.get("list", [])
    total = res.get("total", len(items)) if isinstance(res, dict) else len(items)
    data = WorkflowList(items=[_to_workflow(w) for w in (items or [])], total=total)
    return ActionResult.success(data=data, summary=f"{len(data.items)} workflow(s).")


@chat.function(
    "get_workflow",
    "Read one Ironclad workflow in full: current step, attribute values, "
    "participants, and approval state.",
    action_type="read",
    chain_callable=True,
    data_model=Workflow,
    event="ironclad-connector.get_workflow",
)
async def get_workflow(ctx, params: GetWorkflowParams) -> ActionResult:
    """Read one workflow by id."""
    conn = await resolve_connection(ctx, params.connection_id)
    if isinstance(conn, ActionResult):
        return conn
    res = await ic.get_workflow(ctx, conn, params.workflow_id)
    wf = _to_workflow(res if isinstance(res, dict) else {})
    return ActionResult.success(data=wf, summary=f"Workflow '{wf.name or wf.id}'.")


@chat.function(
    "launch_workflow",
    "Launch a new Ironclad workflow (contract request) synchronously "
    "from a template. Blocks until created -- use launch_workflow_async "
    "if attaching large files.",
    action_type="write",
    chain_callable=True,
    data_model=Workflow,
    event="ironclad-connector.launch_workflow",
    effects=["ironclad.workflow.launched"],
)
async def launch_workflow(ctx, params: LaunchWorkflowParams) -> ActionResult:
    """Launch a new workflow synchronously from a template id."""
    conn = await resolve_connection(ctx, params.connection_id)
    if isinstance(conn, ActionResult):
        return conn
    attrs = _parse_json_field(params.attributes_json, "attributes_json")
    if isinstance(attrs, ActionResult):
        return attrs
    body = {"templateId": params.template_id, "name": params.name, "attributes": attrs}
    res = await ic.launch_workflow(ctx, conn, body)
    wf = _to_workflow(res if isinstance(res, dict) else {})
    return ActionResult.success(data=wf, summary=f"Launched workflow '{params.name}'.")


@chat.function(
    "launch_workflow_async",
    "Launch a new Ironclad workflow asynchronously (non-blocking) -- "
    "recommended when the launch also includes file attachments. Returns "
    "immediately with a launch acknowledgement; poll get_workflow with "
    "the returned id to see it settle.",
    action_type="write",
    chain_callable=True,
    data_model=RawResult,
    event="ironclad-connector.launch_workflow_async",
    effects=["ironclad.workflow.launched"],
)
async def launch_workflow_async(ctx, params: LaunchWorkflowAsyncParams) -> ActionResult:
    """Launch a new workflow asynchronously from a template id."""
    conn = await resolve_connection(ctx, params.connection_id)
    if isinstance(conn, ActionResult):
        return conn
    attrs = _parse_json_field(params.attributes_json, "attributes_json")
    if isinstance(attrs, ActionResult):
        return attrs
    body = {"templateId": params.template_id, "name": params.name, "attributes": attrs}
    res = await ic.launch_workflow_async(ctx, conn, body)
    data = RawResult(raw_json=json.dumps(res if isinstance(res, dict) else {}))
    return ActionResult.success(data=data, summary=f"Launch of '{params.name}' accepted asynchronously.")


@chat.function(
    "bulk_launch_workflow",
    "Launch several workflows from the same template in one call, e.g. "
    "one NDA per new counterparty. Pass launches_json as a JSON array of "
    "{name, attributes} objects.",
    action_type="write",
    chain_callable=True,
    data_model=RawResult,
    event="ironclad-connector.bulk_launch_workflow",
    effects=["ironclad.workflow.launched"],
)
async def bulk_launch_workflow(ctx, params: BulkLaunchWorkflowParams) -> ActionResult:
    """Launch several workflows from the same template in one call."""
    conn = await resolve_connection(ctx, params.connection_id)
    if isinstance(conn, ActionResult):
        return conn
    try:
        launches = json.loads(params.launches_json)
        if not isinstance(launches, list):
            raise ValueError
    except Exception:
        return ActionResult.error("'launches_json' must be a valid JSON array of {name, attributes} objects.")
    body = {"templateId": params.template_id, "launches": launches}
    res = await ic.bulk_launch_workflow(ctx, conn, body)
    data = RawResult(raw_json=json.dumps(res if isinstance(res, dict) else {}))
    return ActionResult.success(data=data, summary=f"Bulk-launched {len(launches)} workflow(s).")


@chat.function(
    "cancel_workflow",
    "Cancel an active Ironclad workflow before it completes.",
    action_type="write",
    chain_callable=True,
    data_model=DeleteResult,
    event="ironclad-connector.cancel_workflow",
    effects=["ironclad.workflow.cancelled"],
)
async def cancel_workflow(ctx, params: CancelWorkflowParams) -> ActionResult:
    """Cancel an active workflow by id."""
    conn = await resolve_connection(ctx, params.connection_id)
    if isinstance(conn, ActionResult):
        return conn
    await ic.cancel_workflow(ctx, conn, params.workflow_id)
    return ActionResult.success(data=DeleteResult(ok=True), summary=f"Workflow '{params.workflow_id}' cancelled.")


@chat.function(
    "revert_workflow_to_review",
    "Send an active workflow back to its Review step -- e.g. after a "
    "signer rejects, or new redlines require another look.",
    action_type="write",
    chain_callable=True,
    data_model=RawResult,
    event="ironclad-connector.revert_workflow_to_review",
    effects=["ironclad.workflow.reverted"],
)
async def revert_workflow_to_review(ctx, params: RevertWorkflowToReviewParams) -> ActionResult:
    """Revert an active workflow back to its Review step."""
    conn = await resolve_connection(ctx, params.connection_id)
    if isinstance(conn, ActionResult):
        return conn
    body = {"reason": params.reason} if params.reason else {}
    res = await ic.revert_workflow_to_review(ctx, conn, params.workflow_id, body)
    data = RawResult(raw_json=json.dumps(res if isinstance(res, dict) else {}))
    return ActionResult.success(data=data, summary=f"Workflow '{params.workflow_id}' reverted to review.")


@chat.function(
    "list_workflow_schemas",
    "List all workflow designs (templates) configured in this Ironclad "
    "company -- their template ids, needed to launch a workflow.",
    action_type="read",
    chain_callable=True,
    data_model=RawResult,
    event="ironclad-connector.list_workflow_schemas",
)
async def list_workflow_schemas(ctx, params: ListWorkflowSchemasParams) -> ActionResult:
    """List workflow design (template) summaries."""
    conn = await resolve_connection(ctx, params.connection_id)
    if isinstance(conn, ActionResult):
        return conn
    res = await ic.list_workflow_schemas(ctx, conn, {"page": params.page, "pageSize": params.page_size})
    data = RawResult(raw_json=json.dumps(res if isinstance(res, (dict, list)) else {}))
    return ActionResult.success(data=data, summary="Workflow schemas retrieved.")


@chat.function(
    "get_workflow_schema",
    "Read one workflow design (template) in full -- its launch-form "
    "attribute ids and types, needed before calling launch_workflow.",
    action_type="read",
    chain_callable=True,
    data_model=RawResult,
    event="ironclad-connector.get_workflow_schema",
)
async def get_workflow_schema(ctx, params: GetWorkflowSchemaParams) -> ActionResult:
    """Read one workflow design (template) schema by id."""
    conn = await resolve_connection(ctx, params.connection_id)
    if isinstance(conn, ActionResult):
        return conn
    res = await ic.get_workflow_schema(ctx, conn, params.template_id)
    data = RawResult(raw_json=json.dumps(res if isinstance(res, dict) else {}))
    return ActionResult.success(data=data, summary=f"Schema for template '{params.template_id}' retrieved.")


@chat.function(
    "update_workflow_attributes",
    "Update one or more attribute values on an active workflow, e.g. "
    "correcting a counterparty name mid-review.",
    action_type="write",
    chain_callable=True,
    data_model=Workflow,
    event="ironclad-connector.update_workflow_attributes",
    effects=["ironclad.workflow.updated"],
)
async def update_workflow_attributes(ctx, params: UpdateWorkflowAttributesParams) -> ActionResult:
    """Update one or more attribute values on an active workflow."""
    conn = await resolve_connection(ctx, params.connection_id)
    if isinstance(conn, ActionResult):
        return conn
    attrs = _parse_json_field(params.attributes_json, "attributes_json")
    if isinstance(attrs, ActionResult):
        return attrs
    res = await ic.update_workflow_attributes(ctx, conn, params.workflow_id, {"attributes": attrs})
    wf = _to_workflow(res if isinstance(res, dict) else {})
    return ActionResult.success(data=wf, summary=f"Workflow '{params.workflow_id}' attributes updated.")


@chat.function(
    "get_workflow_attachment",
    "Read one file attachment's metadata/download info on an active "
    "workflow.",
    action_type="read",
    chain_callable=True,
    data_model=RawResult,
    event="ironclad-connector.get_workflow_attachment",
)
async def get_workflow_attachment(ctx, params: GetWorkflowAttachmentParams) -> ActionResult:
    """Read one workflow attachment's metadata by id."""
    conn = await resolve_connection(ctx, params.connection_id)
    if isinstance(conn, ActionResult):
        return conn
    res = await ic.get_workflow_attachment(ctx, conn, params.workflow_id, params.attachment_id)
    data = RawResult(raw_json=json.dumps(res if isinstance(res, dict) else {}))
    return ActionResult.success(data=data, summary="Workflow attachment retrieved.")


@chat.function(
    "add_workflow_attachment",
    "Attach a file (fetched from a publicly reachable URL) to an active "
    "workflow.",
    action_type="write",
    chain_callable=True,
    data_model=RawResult,
    event="ironclad-connector.add_workflow_attachment",
    effects=["ironclad.workflow.attachment_added"],
)
async def add_workflow_attachment(ctx, params: AddWorkflowAttachmentParams) -> ActionResult:
    """Attach a file to an active workflow from a publicly reachable URL."""
    conn = await resolve_connection(ctx, params.connection_id)
    if isinstance(conn, ActionResult):
        return conn
    body = {"fileName": params.file_name, "fileUrl": params.file_url}
    res = await ic.add_workflow_attachment(ctx, conn, params.workflow_id, body)
    data = RawResult(raw_json=json.dumps(res if isinstance(res, dict) else {}))
    return ActionResult.success(data=data, summary=f"Attachment '{params.file_name}' added to workflow '{params.workflow_id}'.")


@chat.function(
    "create_workflow_comment",
    "Add a comment to an active workflow, visible to its participants "
    "inside Ironclad.",
    action_type="write",
    chain_callable=True,
    data_model=RawResult,
    event="ironclad-connector.create_workflow_comment",
    effects=["ironclad.workflow.commented"],
)
async def create_workflow_comment(ctx, params: CreateWorkflowCommentParams) -> ActionResult:
    """Add a comment to an active workflow."""
    conn = await resolve_connection(ctx, params.connection_id)
    if isinstance(conn, ActionResult):
        return conn
    res = await ic.create_workflow_comment(ctx, conn, params.workflow_id, {"text": params.text})
    data = RawResult(raw_json=json.dumps(res if isinstance(res, dict) else {}))
    return ActionResult.success(data=data, summary=f"Comment added to workflow '{params.workflow_id}'.")


@chat.function(
    "send_signature_request",
    "Trigger Ironclad's e-signature flow for a workflow currently ready "
    "for signature, naming who should sign.",
    action_type="write",
    chain_callable=True,
    data_model=RawResult,
    event="ironclad-connector.send_signature_request",
    effects=["ironclad.workflow.signature_requested"],
)
async def send_signature_request(ctx, params: SendSignatureRequestParams) -> ActionResult:
    """Trigger the e-signature flow for a workflow, naming the signers."""
    conn = await resolve_connection(ctx, params.connection_id)
    if isinstance(conn, ActionResult):
        return conn
    try:
        signers = json.loads(params.signers_json)
        if not isinstance(signers, list):
            raise ValueError
    except Exception:
        return ActionResult.error("'signers_json' must be a valid JSON array of {email, name} objects.")
    res = await ic.send_signature_request(ctx, conn, params.workflow_id, {"signers": signers})
    data = RawResult(raw_json=json.dumps(res if isinstance(res, dict) else {}))
    return ActionResult.success(data=data, summary=f"Signature request sent for workflow '{params.workflow_id}'.")


@chat.function(
    "get_signature_status",
    "Read the current e-signature status of a workflow -- who has "
    "signed, who is pending.",
    action_type="read",
    chain_callable=True,
    data_model=RawResult,
    event="ironclad-connector.get_signature_status",
)
async def get_signature_status(ctx, params: GetSignatureStatusParams) -> ActionResult:
    """Read the e-signature status of a workflow."""
    conn = await resolve_connection(ctx, params.connection_id)
    if isinstance(conn, ActionResult):
        return conn
    res = await ic.get_signature_status(ctx, conn, params.workflow_id)
    data = RawResult(raw_json=json.dumps(res if isinstance(res, dict) else {}))
    return ActionResult.success(data=data, summary=f"Signature status for workflow '{params.workflow_id}' retrieved.")


@chat.function(
    "update_approval",
    "Approve or reject a pending approval step on a workflow, acting as "
    "the connection's configured user.",
    action_type="write",
    chain_callable=True,
    data_model=RawResult,
    event="ironclad-connector.update_approval",
    effects=["ironclad.workflow.approval_updated"],
)
async def update_approval(ctx, params: UpdateApprovalParams) -> ActionResult:
    """Approve or reject a pending approval step on a workflow."""
    conn = await resolve_connection(ctx, params.connection_id)
    if isinstance(conn, ActionResult):
        return conn
    decision = params.decision.strip().lower()
    if decision not in ("approve", "reject"):
        return ActionResult.error("'decision' must be either 'approve' or 'reject'.")
    body = {"decision": decision, "comment": params.comment}
    res = await ic.update_approval(ctx, conn, params.workflow_id, params.step_id, body)
    data = RawResult(raw_json=json.dumps(res if isinstance(res, dict) else {}))
    return ActionResult.success(data=data, summary=f"Approval step '{params.step_id}' {decision}d.")
