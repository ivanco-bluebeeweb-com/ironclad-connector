"""Panel UI -- connections list/connect form in the left sidebar.

SIDEBAR CONTENT -- NO CARDS ANYWHERE, per ~/UI_INTERFACE_STANDARD.md's
"left sidebar, no decorated cards" rule (same convention as CircleCI/
MuleSoft/Mirth Connect Connector's panels.py).

Every section is a plain ui.Stack, content stacked vertically and
left-aligned, sections separated by ui.Divider() -- no Card
border/background/shadow anywhere in this slot. Disconnect lives only in
the "App settings" screen (panels_settings.py). The one secondary
"App settings" button is always the LAST element at the bottom of the
sidebar.

PER ~/UI_INTERFACE_STANDARD.md (2026-08-21 addendum): every Input/Password
carries its own visible label (never placeholder-only), the placeholder
text is always contextually specific to what's being entered (never a
generic "Enter value"), the form's own container is stretched to the full
width of the left sidebar, and the form's inner content is stretched to
fill that container. The "How do I set this up?" instruction lives ONLY
in the help modal below -- it is not duplicated as static sidebar text.
"""
from __future__ import annotations

from imperal_sdk import ui

from app import ext
from handlers_connection import _load_connections


def _settings_button() -> ui.UINode:
    """The one required secondary entry point into the settings screen --
    always the last element at the bottom of the sidebar."""
    return ui.Button(
        "App settings", variant="secondary", size="sm", full_width=True,
        icon="settings", on_click=ui.Call("__panel__ironclad_settings"),
    )


def _connection_row(c: dict) -> ui.UINode:
    region = c.get("region", "na1")
    label = c.get("label") or f"Ironclad ({region})"
    return ui.Stack(direction="v", gap=1, align="start", children=[
        ui.Text(label, variant="body"),
        ui.Text(f"{c.get('as_user_email', '')} · {region}", variant="caption"),
    ])


def _connections_section(connections: list[dict]) -> ui.UINode:
    if not connections:
        return ui.Text("No Ironclad company connected yet.", variant="caption")
    children: list[ui.UINode] = []
    for i, c in enumerate(connections):
        if i > 0:
            children.append(ui.Divider())
        children.append(_connection_row(c))
    return ui.Stack(direction="v", gap=2, children=children)


def _connect_section() -> ui.UINode:
    """Form container stretched to the FULL WIDTH of the left sidebar, its
    inner content stretched to fill it. No intro heading/description text
    here -- the setup walkthrough lives ONLY in ironclad_connect_help's
    modal (button below opens it); repeating it here would duplicate that
    instruction."""
    return ui.Stack(direction="v", gap=3, align="stretch", children=[
        ui.Button("How do I set this up?", variant="ghost", size="sm",
                  icon="HelpCircle",
                  on_click=ui.Call("__panel__ironclad_connect_help")),
        ui.Form(
            action="connect_ironclad",
            submit_label="Verify and connect",
            children=[
                ui.Stack(direction="v", gap=1, align="stretch", children=[
                    ui.Text("OAuth Client ID", variant="caption"),
                    ui.Input(param_name="client_id",
                              placeholder="Client ID from Ironclad Company Settings > API"),
                ]),
                ui.Stack(direction="v", gap=1, align="stretch", children=[
                    ui.Text("OAuth Client Secret", variant="caption"),
                    ui.Password(param_name="client_secret",
                                placeholder="Client Secret shown once when the client was created"),
                ]),
                ui.Stack(direction="v", gap=1, align="stretch", children=[
                    ui.Text("Acting user email", variant="caption"),
                    ui.Input(param_name="as_user_email",
                              placeholder="e.g. legal-ops@yourcompany.com"),
                ]),
                ui.Stack(direction="v", gap=1, align="stretch", children=[
                    ui.Text("Region", variant="caption"),
                    ui.Select(param_name="region", options=[
                        {"label": "na1 -- US (default)", "value": "na1"},
                        {"label": "eu1 -- EU data residency", "value": "eu1"},
                        {"label": "demo -- Sandbox", "value": "demo"},
                    ], value="na1"),
                ]),
                ui.Stack(direction="v", gap=1, align="stretch", children=[
                    ui.Text("Label (optional)", variant="caption"),
                    ui.Input(param_name="label", placeholder="e.g. Legal Ops production"),
                ]),
            ],
        ),
    ])


@ext.panel("ironclad_connect", slot="left", title="Ironclad", icon="📜",
           default_width=320, min_width=260, max_width=420)
async def ironclad_connect_panel(ctx, **kwargs) -> object:
    connections = await _load_connections(ctx)
    connected = bool(connections)

    header = ui.Header(text="Ironclad", level=2,
                        subtitle="Launch and manage contract workflows and records from Imperal")

    if not connected:
        return ui.Stack(direction="v", gap=4, align="stretch", children=[
            header,
            _connect_section(),
            ui.Divider(),
            _settings_button(),
        ])

    return ui.Stack(direction="v", gap=4, align="stretch", children=[
        header,
        ui.Text("Connected companies", variant="subtitle"),
        _connections_section(connections),
        ui.Divider(),
        _connect_section(),
        ui.Divider(),
        _settings_button(),
    ])


@ext.panel("ironclad_connect_help", slot="center",
           title="How to connect Ironclad", center_overlay=True)
async def ironclad_connect_help(ctx, **kwargs) -> object:
    content = ui.Stack(direction="v", gap=3, children=[
        ui.Text("1. In Ironclad, go to Company Settings > API > OAuth Clients (you must be a company admin)."),
        ui.Text("2. Click \"Create OAuth Client\", give it a name you'll recognize, and create it."),
        ui.Text("3. Copy the Client ID and Client Secret immediately -- Ironclad only shows the secret once."),
        ui.Text("4. Every request also runs AS a specific Ironclad user -- enter that user's email (they need the permissions you want this connection to have)."),
        ui.Text("5. Pick your company's data region (na1/eu1/demo) and paste everything into the form here."),
        ui.Divider(),
        ui.Alert(
            title="OAuth 2.0 Client Credentials grant only",
            message=(
                "This connects via Ironclad's own machine-to-machine OAuth grant -- "
                "the deprecated company-wide Legacy Access Token is not supported. "
                "This covers Workflows, Records, Entities, Obligations, Webhooks and "
                "Export/Reports (plan-gated). Ironclad Clickwrap is a separate product "
                "and out of scope."
            ),
            type="warning",
        ),
        ui.Divider(),
        ui.Link(
            label="Open Ironclad's official Client Credentials grant guide",
            href="https://developer.ironcladapp.com/reference/client-credentials-grant",
        ),
    ])
    return ui.Dialog(
        title="How to connect Ironclad",
        content=content,
        confirm_label="",
        cancel_label="Close",
    )


@ext.panel("ironclad_center", slot="center", title="Ironclad", icon="📜", center_overlay=True)
async def ironclad_center_panel(ctx, **kwargs) -> object:
    """Base center panel -- per UI_INTERFACE_STANDARD.md (2026-08-20).
    This app has no list/detail content of its own to show in the center
    by default (everything lives in the sidebar). MUST carry
    center_overlay=True: per docs.imperal.io/en/concepts/panels, a plain
    slot="center" panel is registered but the Panel app never fetches it
    at session-init without that flag. Text is the shared canonical
    wording -- must stay identical across every app in this situation."""
    return ui.Empty(
        message="Nothing to show here -- this app is managed entirely from the sidebar.",
        icon="👈",
    )
