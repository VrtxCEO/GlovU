"""
Event types and thread-safe queue for communication between proxy and UI.

The proxy thread pushes events; the UI thread pulls and displays them.
"""

from __future__ import annotations

import secrets
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from queue import Queue
from typing import Literal


EventKind = Literal[
    "blocked_unknown_endpoint",   # traffic to endpoint not on approved list
    "blocked_unknown_app",        # first-time app detected, blocked pending approval
    "blocked_unknown_model",      # known provider but unknown model
    "redacted_sensitive_data",    # PII found and scrubbed before sending
    "suspicious_activity",        # burst or large payload from an app
    "new_local_model",            # local model server (Ollama, LM Studio) detected
    "approved",                   # user approved something
    "denied",                     # user denied something
]


@dataclass
class GlovuEvent:
    id: str
    timestamp: str
    kind: EventKind
    app_name: str            # process that made the request
    provider_host: str       # destination hostname
    provider_name: str       # human name (e.g. "OpenAI")
    what: str                # "Blocked a request from Cursor to an unknown AI service"
    why: str                 # "This AI service has not been approved on your device"
    action: str              # "The request was safely denied. No data left your device."
    requires_decision: bool = False   # True = show approve/deny buttons
    model: str = ""
    redacted_fields: list[str] = field(default_factory=list)


def new_event(
    kind: EventKind,
    app_name: str,
    provider_host: str,
    provider_name: str,
    what: str,
    why: str,
    action: str,
    requires_decision: bool = False,
    model: str = "",
    redacted_fields: list[str] | None = None,
) -> GlovuEvent:
    return GlovuEvent(
        id=secrets.token_hex(6),
        timestamp=datetime.now(timezone.utc).isoformat(),
        kind=kind,
        app_name=app_name,
        provider_host=provider_host,
        provider_name=provider_name,
        what=what,
        why=why,
        action=action,
        requires_decision=requires_decision,
        model=model,
        redacted_fields=redacted_fields or [],
    )


# Global event queue — proxy pushes, UI pulls
event_queue: Queue[GlovuEvent] = Queue()


def _data_dir() -> Path:
    if sys.platform == "win32":
        import os
        base = Path(os.environ.get("APPDATA", Path.home()))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        import os
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    d = base / "GlovU"
    d.mkdir(parents=True, exist_ok=True)
    return d


DATA_DIR = _data_dir()
