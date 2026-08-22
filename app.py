"""Extension declaration, secrets, lifecycle hooks.

WHY BYOK (bring-your-own-key), same reasoning as MuleSoft / PagerDuty /
Mirth Connect / every other connector in this portfolio.

Ironclad is the user's OWN Contract Lifecycle Management company -- Imperal
cannot and should not broker access to someone else's contract repository
and legal workflows centrally. The user registers their own OAuth Client
(Client ID/Secret) inside their own Ironclad company, pastes it once,
Vault-encrypted via `ctx.secrets`, and every call runs against their own
company's data.

WHY OAUTH 2.0 CLIENT CREDENTIALS, NOT AUTHORIZATION CODE OR THE LEGACY
ACCESS TOKEN -- full reasoning in ironclad_client.py module docstring.

WHY `write_mode="both"`, SAME REASONING AS EVERY OTHER BYOK CONNECTOR.

Declaring `write_mode="user"` would mean only the platform's generic
Secrets screen could write these -- leaving a first-time user with no
in-app screen explaining what an Ironclad OAuth Client even is or how to
create one. `"both"` keeps the generic Secrets screen as a fallback while
letting `connect_ironclad` be the friendly guided path.

WHY SCOPE IS PER-ACCOUNT, NOT APP-LEVEL, SAME AS EVERY OTHER BYOK
CONNECTOR.

Each user connects their OWN Ironclad company -- these are not
developer-owned app credentials, so the connections secret is declared
per-account (default scope), not `scope="app"`.

WHY CONNECTIONS ARE STORED AS A JSON ARRAY UNDER ONE SECRET NAME, NOT ONE
SECRET PER CONNECTION.

Same "one secret holding a JSON array" precedent as every other multi-
connection BYOK connector in this portfolio (MuleSoft/PagerDuty/Mirth
Connect) -- a company may reasonably want more than one Ironclad company
connected (e.g. a parent company and a subsidiary with separate Ironclad
instances), and Imperal's secrets API is simplest when treated as one
opaque blob per logical secret name rather than dynamically-named secrets
per connection.
"""
from __future__ import annotations

from imperal_sdk import ChatExtension, Extension

ext = Extension(
    app_id="ironclad-connector",
    display_name="Ironclad",
    description=(
        "Connect your own Ironclad CLM company -- launch and manage contract "
        "workflows, browse the signed-agreement Records repository, manage "
        "counterparty Entities and post-signature Obligations, and wire up "
        "webhooks for real-time contract lifecycle events."
    ),
    icon="icon.svg",
    capabilities=[
        "ironclad:read",
        "ironclad:write",
    ],
    actions_explicit=True,
    system=False,
)

ext.secret(
    "ironclad_connections",
    (
        "Saved Ironclad OAuth Client connections -- stored as a JSON "
        "array, one entry per connected company, each with its own "
        "client_id, client_secret, as_user_email, region, and label. "
        "Managed through connect_ironclad / disconnect_ironclad -- you "
        "should not need to edit this directly."
    ),
    required=True,
    write_mode="both",
    max_bytes=65536,
    rotation_hint_days=180,
)(lambda: None)

chat = ChatExtension(
    ext,
    tool_name="ironclad",
    description=(
        "Ironclad Connector -- connect your own Ironclad CLM company, then "
        "launch/manage contract Workflows (approvals, signatures, comments, "
        "attachments), browse the signed-agreement Records repository, "
        "manage counterparty Entities and post-signature Obligations, wire "
        "up Webhooks for real-time contract lifecycle events, run data "
        "exports, and audit company-wide contract health."
    ),
)


@ext.health_check
async def health_check(ctx) -> dict:
    return {"ok": True}
