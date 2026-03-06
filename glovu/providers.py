"""
Known AI provider registry.

Glove watches outbound traffic to these hosts and routes it through the local gateway.
The list auto-updates from a community-maintained source.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional


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


PROVIDERS_FILE = _data_dir() / "providers.json"

# Community-maintained AI provider list — lives in the GlovU repo, updated as new providers emerge
PROVIDER_LIST_URL = "https://raw.githubusercontent.com/VrtxCEO/GlovU/main/providers/ai_providers.json"


@dataclass
class Provider:
    name: str
    host: str
    paths: list[str] = field(default_factory=list)   # path prefixes that indicate AI calls
    local: bool = False                                # local model server (Ollama, LM Studio, etc.)
    approved: bool = True                              # built-ins are pre-approved


# Built-in providers — always present, no user approval required
BUILTIN_PROVIDERS: dict[str, Provider] = {
    "api.openai.com": Provider(
        "OpenAI", "api.openai.com",
        ["/v1/chat/completions", "/v1/completions", "/v1/embeddings", "/v1/images"],
    ),
    "api.anthropic.com": Provider(
        "Anthropic", "api.anthropic.com",
        ["/v1/messages", "/v1/complete"],
    ),
    "generativelanguage.googleapis.com": Provider(
        "Google Gemini", "generativelanguage.googleapis.com",
        ["/v1/", "/v1beta/"],
    ),
    "api.groq.com": Provider(
        "Groq", "api.groq.com",
        ["/openai/v1/"],
    ),
    "api.mistral.ai": Provider(
        "Mistral", "api.mistral.ai",
        ["/v1/"],
    ),
    "api-inference.huggingface.co": Provider(
        "HuggingFace Inference", "api-inference.huggingface.co",
        ["/"],
    ),
    "api.perplexity.ai": Provider(
        "Perplexity", "api.perplexity.ai",
        ["/chat/completions"],
    ),
    "api.x.ai": Provider(
        "xAI Grok", "api.x.ai",
        ["/v1/"],
    ),
    "api.cohere.com": Provider(
        "Cohere", "api.cohere.com",
        ["/v1/", "/v2/"],
    ),
    "api.together.xyz": Provider(
        "Together AI", "api.together.xyz",
        ["/v1/"],
    ),
    "api.fireworks.ai": Provider(
        "Fireworks AI", "api.fireworks.ai",
        ["/inference/v1/"],
    ),
    "api.deepinfra.com": Provider(
        "DeepInfra", "api.deepinfra.com",
        ["/v1/"],
    ),
    "api.replicate.com": Provider(
        "Replicate", "api.replicate.com",
        ["/v1/predictions"],
    ),
    "api.ai21.com": Provider(
        "AI21 Labs", "api.ai21.com",
        ["/studio/v1/"],
    ),
    # Local model servers — untrusted by default
    "localhost": Provider("Local Model Server", "localhost", [], local=True, approved=False),
    "127.0.0.1": Provider("Local Model Server", "127.0.0.1", [], local=True, approved=False),
    "::1": Provider("Local Model Server", "::1", [], local=True, approved=False),
}

# Well-known local model server ports
LOCAL_AI_PORTS: dict[int, str] = {
    11434: "Ollama",
    1234:  "LM Studio",
    8080:  "llama.cpp server",
    5000:  "LocalAI",
    8000:  "vLLM",
    7860:  "Gradio",
    3000:  "Open WebUI",
}

# Heuristics for detecting unknown AI endpoints
_AI_PATH_SIGNALS = [
    "/v1/chat", "/v1/completions", "/v1/messages", "/v1/generate",
    "/api/generate", "/api/chat", "/v1/embeddings", "/inference",
]
_AI_BODY_SIGNALS = [
    '"model"', '"messages"', '"prompt"', '"max_tokens"',
    '"temperature"', '"stream"', '"system"',
]


class ProviderRegistry:
    """
    Manages known AI providers. Built-ins are always present.
    User-approved unknown endpoints are persisted to disk.
    """

    def __init__(self) -> None:
        self._custom: dict[str, Provider] = {}
        self._load()

    def _load(self) -> None:
        if PROVIDERS_FILE.exists():
            try:
                raw = json.loads(PROVIDERS_FILE.read_text(encoding="utf-8"))
                for host, data in raw.items():
                    self._custom[host] = Provider(**data)
            except Exception:
                pass

    def _save(self) -> None:
        data = {host: asdict(p) for host, p in self._custom.items()}
        PROVIDERS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def lookup(self, host: str) -> Optional[Provider]:
        """Return provider for this hostname, or None if not known."""
        clean = host.lower().split(":")[0]
        return BUILTIN_PROVIDERS.get(clean) or self._custom.get(clean)

    def is_known(self, host: str) -> bool:
        return self.lookup(host) is not None

    def is_approved(self, host: str) -> bool:
        p = self.lookup(host)
        return p is not None and p.approved

    def is_ai_like_unknown(self, host: str, path: str, body: str) -> bool:
        """Heuristic: does this request to an unknown host look like an AI API call?"""
        path_hit = any(path.startswith(sig) or sig in path for sig in _AI_PATH_SIGNALS)
        body_hits = sum(1 for sig in _AI_BODY_SIGNALS if sig in body)
        return path_hit or body_hits >= 2

    def add_and_approve(self, host: str, name: str) -> None:
        self._custom[host.lower()] = Provider(name, host.lower(), approved=True)
        self._save()

    def add_pending(self, host: str, name: str) -> None:
        """Add an unknown endpoint in unapproved state (awaiting user decision)."""
        if host.lower() not in self._custom:
            self._custom[host.lower()] = Provider(name, host.lower(), approved=False)
            self._save()

    def approve(self, host: str) -> None:
        h = host.lower()
        if h in self._custom:
            self._custom[h].approved = True
            self._save()

    def deny(self, host: str) -> None:
        """Mark an endpoint as permanently blocked."""
        h = host.lower()
        self._custom[h] = Provider(
            self._custom[h].name if h in self._custom else host,
            h, approved=False,
        )
        self._save()

    def all_providers(self) -> list[Provider]:
        return list(BUILTIN_PROVIDERS.values()) + list(self._custom.values())

    def try_update_from_remote(self) -> bool:
        """Pull updated provider list from community source. Returns True on success."""
        try:
            with urllib.request.urlopen(PROVIDER_LIST_URL, timeout=5) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
            for host, data in raw.items():
                if host not in BUILTIN_PROVIDERS and host not in self._custom:
                    self._custom[host] = Provider(**data)
            self._save()
            return True
        except Exception:
            return False
