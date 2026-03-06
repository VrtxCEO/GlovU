"""
mitmproxy addon — intercepts AI traffic, applies policy, routes events to UI.

The proxy runs on localhost:7777.
The system proxy is configured to point here by the installer.
All HTTPS traffic flows through; only known AI endpoints are inspected.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Optional

from mitmproxy import http
from mitmproxy.options import Options
from mitmproxy.tools.dump import DumpMaster

from .events import event_queue
from .policy import ConsumerPolicy
from .providers import ProviderRegistry

PROXY_HOST = "127.0.0.1"
PROXY_PORT = 7777

# Shared instances — set up in main before starting the proxy thread
_registry: Optional[ProviderRegistry] = None
_policy: Optional[ConsumerPolicy] = None


def init(registry: ProviderRegistry, policy: ConsumerPolicy) -> None:
    global _registry, _policy
    _registry = registry
    _policy = policy


class GlovuAddon:
    """
    mitmproxy addon that applies Glove's consumer policy to every request.

    Fast path: non-AI hosts pass through immediately with zero processing.
    AI path: policy check, optional body redaction, event emission.
    """

    def request(self, flow: http.HTTPFlow) -> None:
        if _registry is None or _policy is None:
            return

        host = flow.request.host
        path = flow.request.path
        dst_port = flow.request.port or 443

        # Fast path: definitely not AI traffic
        if not _registry.is_known(host) and not _is_potential_ai(host, path):
            return

        # Skip our own proxy port (avoid loops)
        if host in ("127.0.0.1", "localhost") and dst_port == PROXY_PORT:
            return

        src_port = flow.client_conn.peername[1] if flow.client_conn.peername else 0
        body = ""
        if flow.request.content:
            try:
                body = flow.request.get_text(strict=False) or ""
            except Exception:
                body = ""

        headers = dict(flow.request.headers)
        verdict = _policy.check(host, src_port, path, body, headers, dst_port)

        if not verdict.allowed:
            # Block the request — return a clean JSON error to the calling app
            flow.response = http.Response.make(
                403,
                _block_response(verdict.event.why if verdict.event else "Blocked by Glove"),
                {"Content-Type": "application/json"},
            )
            if verdict.event:
                event_queue.put(verdict.event)
            return

        # Allowed — apply body redaction if needed
        if verdict.modified_body is not None:
            try:
                flow.request.set_text(verdict.modified_body)
            except Exception:
                pass

        if verdict.event:
            event_queue.put(verdict.event)

    def response(self, flow: http.HTTPFlow) -> None:
        # Reserved for future response inspection (output scanning, token counting)
        pass


def _is_potential_ai(host: str, path: str) -> bool:
    """Quick pre-filter to avoid loading body for obviously non-AI traffic."""
    if _registry is None:
        return False
    return _registry.is_ai_like_unknown(host, path, "")


def _block_response(reason: str) -> bytes:
    import json
    return json.dumps({
        "error": {
            "type": "blocked_by_glove",
            "message": reason,
            "code": "glove_protection_active",
        }
    }).encode("utf-8")


# ---------------------------------------------------------------------------
# Background thread runner
# ---------------------------------------------------------------------------

_proxy_thread: Optional[threading.Thread] = None
_master: Optional[DumpMaster] = None


def start(registry: ProviderRegistry, policy: ConsumerPolicy) -> None:
    """Start the proxy in a background daemon thread."""
    init(registry, policy)
    global _proxy_thread
    _proxy_thread = threading.Thread(target=_run_proxy, daemon=True, name="glovu-proxy")
    _proxy_thread.start()


def _run_proxy() -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_async_run_proxy())
    except Exception as exc:
        # Proxy crashed — emit a synthetic event so the tray shows an issue state
        from .events import new_event
        evt = new_event(
            "suspicious_activity", "GlovU", "proxy", "GlovU",
            what="Glove's protection layer stopped unexpectedly.",
            why=str(exc),
            action="Restarting automatically. Your traffic is temporarily unprotected.",
        )
        event_queue.put(evt)
    finally:
        loop.close()


async def _async_run_proxy() -> None:
    global _master
    opts = Options(
        listen_host=PROXY_HOST,
        listen_port=PROXY_PORT,
        ssl_insecure=False,
        confdir=str(_mitm_config_dir()),
    )
    _master = DumpMaster(opts, with_termlog=False, with_dumper=False)
    _master.addons.add(GlovuAddon())
    await _master.run()


def stop() -> None:
    global _master
    if _master:
        _master.shutdown()


def _mitm_config_dir() -> object:
    """Return the mitmproxy config directory (where the CA cert lives)."""
    from pathlib import Path
    from .events import DATA_DIR
    d = DATA_DIR / "mitmproxy"
    d.mkdir(parents=True, exist_ok=True)
    return d
