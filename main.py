"""Entrypoint for the web-kernel and CLI tools (imperal validate/build).

Sets up sys.path, purges stale module cache, then imports ext/chat and all
handler modules so their decorators register on the same Extension
instance -- same pattern as Mirth Connect/PagerDuty Connector's main.py.
"""

import os
import sys

_EXT_DIR = os.path.dirname(os.path.abspath(__file__))
if _EXT_DIR not in sys.path:
    sys.path.insert(0, _EXT_DIR)

_LOCAL = (
    "app", "schemas", "ironclad_client",
    "handlers_connection", "handlers_workflows", "handlers_records",
    "handlers_entities", "handlers_obligations", "handlers_webhooks",
    "handlers_export", "handlers_automation",
    "panels", "panels_settings",
)
for _mod in _LOCAL:
    sys.modules.pop(_mod, None)

from app import ext, chat  # noqa: E402,F401
import handlers_connection  # noqa: E402,F401
import handlers_workflows  # noqa: E402,F401
import handlers_records  # noqa: E402,F401
import handlers_entities  # noqa: E402,F401
import handlers_obligations  # noqa: E402,F401
import handlers_webhooks  # noqa: E402,F401
import handlers_export  # noqa: E402,F401
import handlers_automation  # noqa: E402,F401
import panels  # noqa: E402,F401
import panels_settings  # noqa: E402,F401
