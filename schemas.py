"""Pydantic params models + SDL entity contracts for Ironclad Connector.

All params models are module-scope (V17 federal invariant, same rule as
every other connector's schemas.py). Organized by domain to match
handlers_*.py split (connection, workflows, records, entities, obligations,
webhooks, export, automation/value-add).
"""
from __future__ import annotations

from pydantic import BaseModel, Field
from imperal_sdk import sdl


class NoParams(BaseModel):
    """Explicit empty params model -- V17 disallows untyped handlers."""
    pass


class _ConnScopedParams(BaseModel):
    connection_id: str = Field("", description="Which connected Ironclad company to use, from list_connections. Leave blank to use the only/first connected company.")


# ──────────────────────────────────────────────────────────────────────────
# Connection
# ──────────────────────────────────────────────────────────────────────────


class ConnectIroncladParams(BaseModel):
    client_id: str = Field(..., description="OAuth Client ID from Ironclad Company Settings > API > OAuth Clients.")
    client_secret: str = Field(..., description="OAuth Client Secret shown once when the client was created.")
    as_user_email: str = Field(..., description="Email of the Ironclad user whose permissions this connection acts as (e.g. legal-ops@yourcompany.com).")
    region: str = Field("na1", description="Ironclad data region: na1 (default US), eu1 (EU data residency), or demo (sandbox).")
    label: str = Field("", description="Optional friendly name for this connection, e.g. 'Legal Ops production'.")


class DisconnectIroncladParams(BaseModel):
    connection_id: str = Field(..., description="Connection id to remove, from list_connections.")


class ProviderConnection(sdl.Entity):
    id: str = ""
    title: str = ""
    detail: str = ""


class ProviderConnectionList(sdl.Entity):
    id: str = ""
    title: str = ""
    items: list[ProviderConnection]


class DeleteResult(sdl.Entity):
    id: str = ""
    title: str = ""
    ok: bool = True


class RawResult(sdl.Entity):
    """Generic pass-through entity for Ironclad resources whose shape is
    largely company-configured (custom attributes/properties) -- workflow
    schemas, signature status, attachments, comments, approvals, report
    status. Raw JSON is preserved verbatim rather than forcing a rigid
    schema onto per-company custom fields."""
    id: str = ""
    title: str = ""
    raw_json: str = ""


# ──────────────────────────────────────────────────────────────────────────
# Workflows
# ──────────────────────────────────────────────────────────────────────────


class ListWorkflowsParams(_ConnScopedParams):
    page: int = Field(0, description="Page number, 0-indexed.")
    page_size: int = Field(50, description="Results per page (max 50).")
    status: str = Field("", description="Filter by workflow status, e.g. Active, Completed, Cancelled. Leave blank for all.")
    template_id: str = Field("", description="Filter by workflow design/template id. Leave blank for all templates.")
    last_updated: str = Field("", description="Only workflows updated since this UTC timestamp (ISO 8601). Leave blank for no filter.")


class GetWorkflowParams(_ConnScopedParams):
    workflow_id: str = Field(..., description="Workflow id, e.g. from list_workflows.")


class LaunchWorkflowParams(_ConnScopedParams):
    template_id: str = Field(..., description="Workflow design/template id to launch, from list_workflow_schemas.")
    name: str = Field(..., description="Name for this new workflow instance, e.g. 'MSA - Acme Corp'.")
    attributes_json: str = Field("{}", description="JSON object mapping attribute IDs to launch-form field values, e.g. {\"counterpartyName\": \"Acme Corp\"}.")


class LaunchWorkflowAsyncParams(LaunchWorkflowParams):
    pass


class BulkLaunchWorkflowParams(_ConnScopedParams):
    template_id: str = Field(..., description="Workflow design/template id to launch for every row.")
    launches_json: str = Field(..., description="JSON array of objects, each with 'name' and 'attributes' for one workflow to launch, e.g. [{\"name\": \"MSA - A\", \"attributes\": {...}}].")


class CancelWorkflowParams(_ConnScopedParams):
    workflow_id: str = Field(..., description="Workflow id to cancel.")


class RevertWorkflowToReviewParams(_ConnScopedParams):
    workflow_id: str = Field(..., description="Workflow id to revert.")
    reason: str = Field("", description="Optional reason for reverting to the review step.")


class ListWorkflowSchemasParams(_ConnScopedParams):
    page: int = Field(0, description="Page number, 0-indexed.")
    page_size: int = Field(50, description="Results per page.")


class GetWorkflowSchemaParams(_ConnScopedParams):
    template_id: str = Field(..., description="Workflow design/template id, from list_workflow_schemas.")


class UpdateWorkflowAttributesParams(_ConnScopedParams):
    workflow_id: str = Field(..., description="Workflow id whose attributes to update.")
    attributes_json: str = Field(..., description="JSON object mapping attribute IDs to new values.")


class GetWorkflowAttachmentParams(_ConnScopedParams):
    workflow_id: str = Field(..., description="Workflow id the attachment belongs to.")
    attachment_id: str = Field(..., description="Attachment id, from the workflow's attachment list.")


class AddWorkflowAttachmentParams(_ConnScopedParams):
    workflow_id: str = Field(..., description="Workflow id to attach the file to.")
    file_name: str = Field(..., description="File name to store, e.g. 'redline-v2.docx'.")
    file_url: str = Field(..., description="Publicly reachable URL Ironclad can fetch the file content from.")


class CreateWorkflowCommentParams(_ConnScopedParams):
    workflow_id: str = Field(..., description="Workflow id to comment on.")
    text: str = Field(..., description="Comment text, e.g. 'Legal approved with redlines attached.'")


class SendSignatureRequestParams(_ConnScopedParams):
    workflow_id: str = Field(..., description="Workflow id ready for signature.")
    signers_json: str = Field(..., description="JSON array of signer objects, e.g. [{\"email\": \"ceo@acme.com\", \"name\": \"Jane Doe\"}].")


class GetSignatureStatusParams(_ConnScopedParams):
    workflow_id: str = Field(..., description="Workflow id to check signature status for.")


class UpdateApprovalParams(_ConnScopedParams):
    workflow_id: str = Field(..., description="Workflow id containing the approval step.")
    step_id: str = Field(..., description="Approval step id, from get_workflow.")
    decision: str = Field(..., description="Approval decision: 'approve' or 'reject'.")
    comment: str = Field("", description="Optional comment explaining the decision.")


class Workflow(sdl.Entity):
    title: str = ""
    id: str = ""
    name: str = ""
    status: str = ""
    template_id: str = ""
    created_at: str = ""
    raw_json: str = ""


class WorkflowList(sdl.Entity):
    id: str = ""
    title: str = ""
    items: list[Workflow]
    total: int = 0


# ──────────────────────────────────────────────────────────────────────────
# Records
# ──────────────────────────────────────────────────────────────────────────


class ListRecordsParams(_ConnScopedParams):
    page: int = Field(0, description="Page number, 0-indexed.")
    page_size: int = Field(50, description="Results per page.")
    types: str = Field("", description="Comma-separated record types to filter by, e.g. 'NDA,MSA'. Leave blank for all types.")
    last_updated: str = Field("", description="Only records updated since this UTC timestamp (ISO 8601). Leave blank for no filter.")
    filter_property: str = Field("", description="Record property id to filter on, e.g. 'counterpartyName'. Leave blank for no property filter.")
    filter_value: str = Field("", description="Value the filter_property must contain. Required only if filter_property is set.")
    sort_field: str = Field("agreementDate", description="Field to sort by: agreementDate, name, or lastUpdated.")
    sort_direction: str = Field("DESC", description="Sort direction: ASC or DESC.")


class GetRecordParams(_ConnScopedParams):
    record_id: str = Field(..., description="Record id, e.g. from list_records.")
    hydrate_entities: bool = Field(False, description="If true, expand linked entity ids into full entity objects in the response.")


class CreateRecordParams(_ConnScopedParams):
    name: str = Field(..., description="Contract record name, e.g. 'NDA - Acme Corp 2026'.")
    record_type: str = Field(..., description="Record type id, from get_records_schema.")
    properties_json: str = Field("{}", description="JSON object of record property values keyed by property id.")
    parent_record_id: str = Field("", description="Optional parent record id to link this record under (e.g. an amendment under its master agreement).")


class UpdateRecordParams(_ConnScopedParams):
    record_id: str = Field(..., description="Record id to update.")
    properties_json: str = Field(..., description="JSON object of record property values to update, keyed by property id.")


class DeleteRecordParams(_ConnScopedParams):
    record_id: str = Field(..., description="Record id to delete.")


class GetRecordAttachmentParams(_ConnScopedParams):
    record_id: str = Field(..., description="Record id the attachment belongs to.")
    attachment_id: str = Field(..., description="Attachment id, from the record's attachment list.")


class AddRecordAttachmentParams(_ConnScopedParams):
    record_id: str = Field(..., description="Record id to attach the file to.")
    file_name: str = Field(..., description="File name to store, e.g. 'signed-agreement.pdf'.")
    file_url: str = Field(..., description="Publicly reachable URL Ironclad can fetch the file content from.")


class DeleteRecordAttachmentParams(_ConnScopedParams):
    record_id: str = Field(..., description="Record id the attachment belongs to.")
    attachment_id: str = Field(..., description="Attachment id to delete.")


class ApplyContractActionParams(_ConnScopedParams):
    record_id: str = Field(..., description="Record id to apply the action to.")
    action_type: str = Field(..., description="Contract action type, e.g. 'renew', 'terminate', 'amend' (exact set depends on the record type's configured actions).")
    properties_json: str = Field("{}", description="JSON object of any additional property values the action requires.")


class SmartImportRecordParams(_ConnScopedParams):
    name: str = Field(..., description="Contract record name for the imported document.")
    record_type: str = Field(..., description="Record type id to classify the imported document as.")
    file_url: str = Field(..., description="Publicly reachable URL of the signed document Ironclad should extract metadata from.")


class Record(sdl.Entity):
    title: str = ""
    id: str = ""
    name: str = ""
    record_type: str = ""
    agreement_date: str = ""
    last_updated: str = ""
    raw_json: str = ""


class RecordList(sdl.Entity):
    id: str = ""
    title: str = ""
    items: list[Record]
    total: int = 0


# ──────────────────────────────────────────────────────────────────────────
# Entities (counterparties)
# ──────────────────────────────────────────────────────────────────────────


class ListEntitiesParams(_ConnScopedParams):
    page: int = Field(0, description="Page number, 0-indexed.")
    page_size: int = Field(50, description="Results per page.")
    entity_type: str = Field("", description="Filter by entity type, e.g. 'Company', 'Individual'. Leave blank for all types.")


class GetEntityParams(_ConnScopedParams):
    entity_id: str = Field(..., description="Entity id, e.g. from list_entities.")


class CreateEntityParams(_ConnScopedParams):
    name: str = Field(..., description="Counterparty entity name, e.g. 'Acme Corp'.")
    entity_type: str = Field(..., description="Entity type id, from Ironclad's entity type configuration.")
    properties_json: str = Field("{}", description="JSON object of entity property values keyed by property id.")


class UpdateEntityParams(_ConnScopedParams):
    entity_id: str = Field(..., description="Entity id to update.")
    properties_json: str = Field(..., description="JSON object of entity property values to update, keyed by property id.")


class DeleteEntityParams(_ConnScopedParams):
    entity_id: str = Field(..., description="Entity id to delete.")


class Entity_(sdl.Entity):
    title: str = ""
    id: str = ""
    name: str = ""
    entity_type: str = ""
    raw_json: str = ""


class EntityList(sdl.Entity):
    id: str = ""
    title: str = ""
    items: list[Entity_]
    total: int = 0


# ──────────────────────────────────────────────────────────────────────────
# Obligations
# ──────────────────────────────────────────────────────────────────────────


class ListObligationsParams(_ConnScopedParams):
    page: int = Field(0, description="Page number, 0-indexed.")
    page_size: int = Field(50, description="Results per page.")
    record_id: str = Field("", description="Filter obligations to only those linked to this record id. Leave blank for all.")


class GetObligationParams(_ConnScopedParams):
    obligation_id: str = Field(..., description="Obligation id, e.g. from list_obligations.")


class CreateObligationParams(_ConnScopedParams):
    name: str = Field(..., description="Obligation name, e.g. 'Quarterly SLA report due'.")
    record_id: str = Field(..., description="Record id this obligation is linked to.")
    due_date: str = Field("", description="Due date in ISO 8601 (YYYY-MM-DD), if applicable.")
    properties_json: str = Field("{}", description="JSON object of any additional obligation property values.")


class UpdateObligationParams(_ConnScopedParams):
    obligation_id: str = Field(..., description="Obligation id to update.")
    properties_json: str = Field(..., description="JSON object of obligation property values to update.")


class DeleteObligationParams(_ConnScopedParams):
    obligation_id: str = Field(..., description="Obligation id to delete.")


class Obligation(sdl.Entity):
    title: str = ""
    id: str = ""
    name: str = ""
    record_id: str = ""
    due_date: str = ""
    raw_json: str = ""


class ObligationList(sdl.Entity):
    id: str = ""
    title: str = ""
    items: list[Obligation]
    total: int = 0


# ──────────────────────────────────────────────────────────────────────────
# Webhooks
# ──────────────────────────────────────────────────────────────────────────


class CreateWebhookParams(_ConnScopedParams):
    target_url: str = Field(..., description="HTTPS URL Ironclad should POST event payloads to.")
    events_csv: str = Field(..., description="Comma-separated event types to subscribe to, e.g. 'workflow.launched,workflow.completed,record.created'.")
    secret: str = Field("", description="Optional shared secret Ironclad will use to sign webhook payloads for verification.")


class UpdateWebhookParams(_ConnScopedParams):
    webhook_id: str = Field(..., description="Webhook id to update, from list_webhooks.")
    target_url: str = Field("", description="New target URL, or leave blank to keep current.")
    events_csv: str = Field("", description="New comma-separated event types, or leave blank to keep current.")


class DeleteWebhookParams(_ConnScopedParams):
    webhook_id: str = Field(..., description="Webhook id to delete.")


class Webhook(sdl.Entity):
    title: str = ""
    id: str = ""
    target_url: str = ""
    events: list[str] = Field(default_factory=list)


class WebhookList(sdl.Entity):
    id: str = ""
    title: str = ""
    items: list[Webhook]


# ──────────────────────────────────────────────────────────────────────────
# Export (reports)
# ──────────────────────────────────────────────────────────────────────────


class CreateReportParams(_ConnScopedParams):
    report_type: str = Field(..., description="Report type to generate, e.g. 'records' or 'workflows'.")
    filters_json: str = Field("{}", description="JSON object of report filter criteria, matching the same filters as list_records/list_workflows.")


class GetReportParams(_ConnScopedParams):
    report_id: str = Field(..., description="Report id returned by create_report.")


class Report(sdl.Entity):
    title: str = ""
    id: str = ""
    status: str = ""
    download_url: str = ""
    raw_json: str = ""


# ──────────────────────────────────────────────────────────────────────────
# Automation / value-add (Tier 3)
# ──────────────────────────────────────────────────────────────────────────


class AuditContractHealthParams(_ConnScopedParams):
    lookback_days: int = Field(30, description="How many days back to scan workflows/records for the health snapshot.")


class ContractHealthReport(sdl.Entity):
    id: str = ""
    title: str = ""
    active_workflow_count: int = 0
    stalled_workflow_count: int = 0
    completed_last_period: int = 0
    upcoming_obligations_30d: int = 0
    summary: str = ""


class FindExpiringContractsParams(_ConnScopedParams):
    within_days: int = Field(60, description="Find records whose agreement/expiration date falls within this many days from now.")
    record_type: str = Field("", description="Optional record type filter, e.g. 'MSA'. Leave blank for all types.")


class BulkTagRecordsParams(_ConnScopedParams):
    record_ids_csv: str = Field(..., description="Comma-separated record ids to update in one pass.")
    properties_json: str = Field(..., description="JSON object of property values to apply to every listed record.")


class BulkUpdateResult(sdl.Entity):
    id: str = ""
    title: str = ""
    updated: int = 0
    failed: int = 0
    errors: list[str] = Field(default_factory=list)
