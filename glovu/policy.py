"""
Consumer policy engine — implements the 7 baseline protection rules.

This policy is fixed and opinionated. The user never edits it directly.
It is the equivalent of a VPN's encryption settings: invisible and safe.
"""

from __future__ import annotations

import json
import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Optional

import psutil

from .events import DATA_DIR, EventKind, GlovuEvent, new_event
from .providers import LOCAL_AI_PORTS, ProviderRegistry

# ---------------------------------------------------------------------------
# PII / sensitive data patterns (Rule 3)
# ---------------------------------------------------------------------------

_PII_PATTERNS: dict[str, re.Pattern] = {
    # Identity
    "email address":              re.compile(r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b'),
    "US phone number":            re.compile(r'\b(?:\+1[\s.\-]?)?\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}\b'),
    "unformatted phone number":   re.compile(r'\b[2-9]\d{2}[2-9]\d{6}\b'),
    "Social Security Number":     re.compile(r'\b\d{3}-\d{2}-\d{4}\b'),
    "unformatted SSN":            re.compile(r'\b(?!000|666|9\d{2})\d{3}(?!00)\d{2}(?!0000)\d{4}\b'),
    "Employer ID Number (EIN)":   re.compile(r'\b\d{2}-\d{7}\b'),
    "US passport number":         re.compile(r'\b[A-Z]\d{8}\b'),
    "driver license (generic)":   re.compile(r'\b(?:DL|DLN|driver.?lic(?:ense)?)[^\w]?\s*[A-Z0-9]{6,12}\b', re.IGNORECASE),
    "date of birth":              re.compile(r'\b(?:dob|date.of.birth|born)[^\w]?\s*\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}\b', re.IGNORECASE),
    # Financial
    "credit card number":         re.compile(r'\b(?:\d{4}[\s\-]?){3}\d{4}\b'),
    "bank routing number":        re.compile(r'\b(?:routing|aba|rtn)[^\w]?\s*[0-9]{9}\b', re.IGNORECASE),
    "bank account number":        re.compile(r'\b(?:account|acct)[^\w]?\s*(?:number|no|#)?[^\w]?\s*\d{8,17}\b', re.IGNORECASE),
    "IBAN":                       re.compile(r'\b[A-Z]{2}\d{2}[A-Z0-9]{4}\d{7}(?:[A-Z0-9]{0,16})?\b'),
    # Credentials & keys
    "API key or token":           re.compile(r'\b(?:sk-|pk-|Bearer |api[_\-]?key[=:\s]+)[A-Za-z0-9_\-]{20,}', re.IGNORECASE),
    "GitHub token":               re.compile(r'\bgh[pousr]_[A-Za-z0-9]{36,}\b'),
    "Slack token":                re.compile(r'\bxox[baprs]-[A-Za-z0-9\-]{10,}\b'),
    "Stripe key":                 re.compile(r'\b(?:sk|pk)_(?:live|test)_[A-Za-z0-9]{24,}\b'),
    "Google API key":             re.compile(r'\bAIza[A-Za-z0-9_\-]{35}\b'),
    "private key":                re.compile(r'-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----'),
    "AWS access key":             re.compile(r'\bAKIA[0-9A-Z]{16}\b'),
    "AWS secret key":             re.compile(r'\b(?:aws.?secret|secret.?access.?key)[^\w]?\s*[=:]\s*[A-Za-z0-9/+]{40}\b', re.IGNORECASE),
    "JWT token":                  re.compile(r'\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\b'),
    # Sensitive fields
    "password field":             re.compile(r'"(?:password|passwd|secret|token|api_key|apikey|auth)"\s*:\s*"[^"]{4,}"', re.IGNORECASE),
    "IP address":                 re.compile(r'\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b'),
    "MAC address":                re.compile(r'\b(?:[0-9A-Fa-f]{2}[:\-]){5}[0-9A-Fa-f]{2}\b'),
}

_REDACT_PLACEHOLDER = "[REDACTED BY GLOVE]"


def _redact_string(text: str) -> tuple[str, list[str]]:
    """Scan a string for PII and replace matches. Returns (cleaned, found_types)."""
    found: list[str] = []
    for label, pattern in _PII_PATTERNS.items():
        if pattern.search(text):
            text = pattern.sub(_REDACT_PLACEHOLDER, text)
            found.append(label)
    return text, found


def _walk_and_redact(obj: object) -> tuple[object, list[str]]:
    """Recursively walk JSON-like structure, redacting string values."""
    found: list[str] = []
    if isinstance(obj, str):
        cleaned, hits = _redact_string(obj)
        return cleaned, hits
    if isinstance(obj, list):
        out = []
        for item in obj:
            cleaned_item, hits = _walk_and_redact(item)
            out.append(cleaned_item)
            found.extend(hits)
        return out, found
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            cleaned_v, hits = _walk_and_redact(v)
            out[k] = cleaned_v
            found.extend(hits)
        return out, found
    return obj, []


def redact_body(body: str) -> tuple[str, list[str]]:
    """
    Parse the request body as JSON, redact PII, return (new_body, found_types).
    If the body is not valid JSON, redact in raw string mode.
    """
    try:
        parsed = json.loads(body)
        cleaned, found = _walk_and_redact(parsed)
        return json.dumps(cleaned), found
    except (json.JSONDecodeError, ValueError):
        return _redact_string(body)


# ---------------------------------------------------------------------------
# Known browsers — auto-approved (monitored but never blocked by Rule 2)
# ---------------------------------------------------------------------------

_BROWSER_APPS: frozenset[str] = frozenset({
    # Windows
    "chrome.exe", "msedge.exe", "firefox.exe", "brave.exe",
    "opera.exe", "vivaldi.exe", "chromium.exe", "iexplore.exe",
    "arc.exe", "waterfox.exe", "librewolf.exe",
    # macOS / Linux names (no .exe)
    "Google Chrome", "Microsoft Edge", "Firefox", "Brave Browser",
    "Opera", "Vivaldi", "Chromium", "Arc", "Safari",
})


# ---------------------------------------------------------------------------
# App identification (Rule 2)
# ---------------------------------------------------------------------------

_app_cache: dict[int, tuple[str, float]] = {}   # port -> (name, timestamp)
_APP_CACHE_TTL = 2.0                             # seconds


def get_app_by_port(src_port: int) -> str:
    """Identify the process making a request by its source TCP port."""
    now = time.monotonic()
    cached = _app_cache.get(src_port)
    if cached and (now - cached[1]) < _APP_CACHE_TTL:
        return cached[0]
    try:
        for conn in psutil.net_connections(kind="tcp"):
            if conn.laddr and conn.laddr.port == src_port and conn.pid:
                try:
                    name = psutil.Process(conn.pid).name()
                    _app_cache[src_port] = (name, now)
                    return name
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
    except (psutil.AccessDenied, Exception):
        pass
    return "Unknown App"


# ---------------------------------------------------------------------------
# Burst / volume tracking (Rule 7)
# ---------------------------------------------------------------------------

_BURST_WINDOW = 60        # seconds
_BURST_THRESHOLD = 20     # requests per window
_LARGE_PAYLOAD_BYTES = 50_000   # 50 KB


class _BurstTracker:
    def __init__(self) -> None:
        self._windows: dict[str, deque[float]] = defaultdict(deque)

    def record_and_check(self, app_name: str) -> bool:
        """Record a request. Returns True if burst threshold exceeded."""
        now = time.monotonic()
        q = self._windows[app_name]
        while q and (now - q[0]) > _BURST_WINDOW:
            q.popleft()
        q.append(now)
        return len(q) >= _BURST_THRESHOLD


# ---------------------------------------------------------------------------
# App and endpoint approval state (Rules 1, 2, 5)
# ---------------------------------------------------------------------------

_STATE_FILE = DATA_DIR / "state.json"


@dataclass
class _State:
    approved_apps: set[str]
    blocked_apps: set[str]
    # unknown models: provider_host -> set of approved model names
    approved_models: dict[str, set[str]]

    @classmethod
    def load(cls) -> "_State":
        if _STATE_FILE.exists():
            try:
                raw = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
                return cls(
                    approved_apps=set(raw.get("approved_apps", [])),
                    blocked_apps=set(raw.get("blocked_apps", [])),
                    approved_models={k: set(v) for k, v in raw.get("approved_models", {}).items()},
                )
            except Exception:
                pass
        return cls(approved_apps=set(), blocked_apps=set(), approved_models={})

    def save(self) -> None:
        data = {
            "approved_apps": sorted(self.approved_apps),
            "blocked_apps": sorted(self.blocked_apps),
            "approved_models": {k: sorted(v) for k, v in self.approved_models.items()},
        }
        _STATE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Policy verdict
# ---------------------------------------------------------------------------

@dataclass
class PolicyVerdict:
    allowed: bool
    event: Optional[GlovuEvent]
    modified_body: Optional[str] = None   # set if body was redacted


# ---------------------------------------------------------------------------
# Consumer policy engine
# ---------------------------------------------------------------------------

class ConsumerPolicy:
    """
    The single pre-baked policy for personal device protection.
    Implements all 7 baseline rules. Stateful — persists decisions to disk.
    """

    def __init__(self, registry: ProviderRegistry) -> None:
        self._registry = registry
        self._state = _State.load()
        self._burst = _BurstTracker()
        self._seen_endpoints: set[str] = set()   # for "new endpoint" dedup

    # ------------------------------------------------------------------
    # Public: approve / deny decisions from the UI
    # ------------------------------------------------------------------

    def approve_app(self, app_name: str) -> None:
        self._state.approved_apps.add(app_name)
        self._state.blocked_apps.discard(app_name)
        self._state.save()

    def deny_app(self, app_name: str) -> None:
        self._state.blocked_apps.add(app_name)
        self._state.approved_apps.discard(app_name)
        self._state.save()

    def approve_endpoint(self, host: str, display_name: str) -> None:
        self._registry.add_and_approve(host, display_name)

    def deny_endpoint(self, host: str, display_name: str) -> None:
        self._registry.deny(host, )

    def approve_model(self, provider_host: str, model: str) -> None:
        self._state.approved_models.setdefault(provider_host, set()).add(model)
        self._state.save()

    # ------------------------------------------------------------------
    # Main check — called by proxy for every AI-bound request
    # ------------------------------------------------------------------

    def check(
        self,
        host: str,
        src_port: int,
        path: str,
        body: str,
        headers: dict[str, str],
        dst_port: int = 443,
    ) -> PolicyVerdict:
        app_name = get_app_by_port(src_port)
        provider = self._registry.lookup(host)

        # --- Rule 4: local model runtime control ---
        if provider and provider.local:
            return self._handle_local_model(host, app_name, provider.name)

        # Check for local port that indicates a local model server
        if host in ("localhost", "127.0.0.1", "::1") and dst_port in LOCAL_AI_PORTS:
            local_name = LOCAL_AI_PORTS[dst_port]
            return self._handle_local_model(host, app_name, local_name)

        # --- Rule 1 & 6: unknown AI endpoint ---
        if provider is None:
            if self._registry.is_ai_like_unknown(host, path, body):
                return self._handle_unknown_endpoint(host, app_name, body)
            # Not AI — pass through
            return PolicyVerdict(allowed=True, event=None)

        # --- Rule 1: known but explicitly denied endpoint ---
        if not provider.approved:
            return self._handle_denied_endpoint(host, app_name, provider.name)

        # --- Rule 2: app-level approval ---
        # Browsers are always allowed — they're user-driven, not background automations.
        # Other apps (scripts, CLIs, background services) require explicit approval.
        is_browser = app_name in _BROWSER_APPS

        if not is_browser:
            if app_name in self._state.blocked_apps:
                return _block(new_event(
                    "blocked_unknown_app", app_name, host, provider.name,
                    what=f"{app_name} tried to use AI but has been blocked.",
                    why=f"You previously denied {app_name} access to AI services.",
                    action="The request was blocked. No data left your device.",
                ))

            if app_name not in self._state.approved_apps:
                return _block(new_event(
                    "blocked_unknown_app", app_name, host, provider.name,
                    what=f"{app_name} is trying to use AI for the first time.",
                    why="Apps must be approved before they can send data to AI services.",
                    action="The request was blocked. Tap to approve or deny this app.",
                    requires_decision=True,
                ))

        # --- Rule 3: sensitive data protection ---
        modified_body, redacted_fields = None, []
        if body:
            new_body, redacted_fields = redact_body(body)
            if redacted_fields:
                modified_body = new_body
                evt = new_event(
                    "redacted_sensitive_data", app_name, host, provider.name,
                    what=f"Sensitive data was found in a request from {app_name} to {provider.name}.",
                    why="Glove detected private information that you may not have intended to share.",
                    action=f"The following were automatically redacted: {', '.join(redacted_fields)}.",
                    redacted_fields=redacted_fields,
                )

        # --- Rule 5: model allowance ---
        model_verdict = self._check_model(body, host, app_name, provider.name)
        if model_verdict is not None:
            return model_verdict

        # --- Rule 7: burst / volume detection ---
        # Skip for browsers — they make dozens of page-load requests normally.
        # Burst detection is for background apps making automated API calls.
        if is_browser:
            if redacted_fields:
                return PolicyVerdict(allowed=True, event=evt, modified_body=modified_body)
            return PolicyVerdict(allowed=True, event=None)

        if len(body.encode()) > _LARGE_PAYLOAD_BYTES:
            suspicious_evt = new_event(
                "suspicious_activity", app_name, host, provider.name,
                what=f"{app_name} sent an unusually large request to {provider.name}.",
                why=f"The request contained more than {_LARGE_PAYLOAD_BYTES // 1000} KB of data.",
                action="The request was allowed. Glove is monitoring this activity.",
            )
            return PolicyVerdict(allowed=True, event=suspicious_evt, modified_body=modified_body)

        if self._burst.record_and_check(app_name):
            suspicious_evt = new_event(
                "suspicious_activity", app_name, host, provider.name,
                what=f"Unusual burst of AI activity detected from {app_name}.",
                why=f"{app_name} sent more than {_BURST_THRESHOLD} AI requests in {_BURST_WINDOW} seconds.",
                action="Requests are being allowed. Glove is monitoring this activity.",
            )
            return PolicyVerdict(allowed=True, event=suspicious_evt, modified_body=modified_body)

        # All checks passed
        if redacted_fields:
            return PolicyVerdict(allowed=True, event=evt, modified_body=modified_body)

        return PolicyVerdict(allowed=True, event=None)

    # ------------------------------------------------------------------
    # Internal handlers
    # ------------------------------------------------------------------

    def _handle_unknown_endpoint(self, host: str, app_name: str, body: str) -> PolicyVerdict:
        self._registry.add_pending(host, host)
        evt = new_event(
            "blocked_unknown_endpoint", app_name, host, host,
            what=f"A request to an unrecognized AI service was blocked ({host}).",
            why="This AI service is not on your approved provider list.",
            action="The request was denied. Tap to approve this service or keep it blocked.",
            requires_decision=True,
        )
        return _block(evt)

    def _handle_local_model(self, host: str, app_name: str, model_server_name: str) -> PolicyVerdict:
        evt = new_event(
            "new_local_model", app_name, host, model_server_name,
            what=f"A local AI model server was detected ({model_server_name}).",
            why="Local model servers are untrusted by default and require your approval.",
            action="The request was blocked. Tap to approve or deny this local AI server.",
            requires_decision=True,
        )
        return _block(evt)

    def _handle_denied_endpoint(self, host: str, app_name: str, provider_name: str) -> PolicyVerdict:
        evt = new_event(
            "blocked_unknown_endpoint", app_name, host, provider_name,
            what=f"A request to {provider_name} was blocked.",
            why="You previously denied access to this AI service.",
            action="The request was safely denied. No data left your device.",
        )
        return _block(evt)

    def _check_model(
        self, body: str, host: str, app_name: str, provider_name: str
    ) -> Optional[PolicyVerdict]:
        if not body:
            return None
        try:
            parsed = json.loads(body)
        except Exception:
            return None
        model = parsed.get("model", "")
        if not model or not isinstance(model, str):
            return None

        # Known models from known providers — allow silently
        # We don't maintain a strict model allowlist; only flag unknown patterns
        # (e.g., a model string that looks like a custom fine-tune or jailbreak variant)
        approved = self._state.approved_models.get(host, set())
        if model in approved:
            return None

        # Heuristic: flag model names that look non-standard
        # (contains paths, URLs, very long strings, or suspicious suffixes)
        if len(model) > 80 or "/" in model or model.startswith("http"):
            evt = new_event(
                "blocked_unknown_model", app_name, host, provider_name,
                what=f"A request using an unusual model was blocked ({model[:60]}).",
                why="This model identifier looks non-standard and may indicate unexpected behavior.",
                action="The request was blocked. Tap to approve this model or keep it blocked.",
                model=model,
                requires_decision=True,
            )
            return _block(evt)

        return None


def _block(event: GlovuEvent) -> PolicyVerdict:
    return PolicyVerdict(allowed=False, event=event)
