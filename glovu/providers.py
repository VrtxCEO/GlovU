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
    # ── OpenAI ──────────────────────────────────────────────────────────
    "api.openai.com": Provider(
        "OpenAI", "api.openai.com",
        ["/v1/chat/completions", "/v1/completions", "/v1/embeddings", "/v1/images", "/v1/audio"],
    ),
    "chat.openai.com": Provider("ChatGPT (Web)", "chat.openai.com", ["/"]),
    "chatgpt.com": Provider("ChatGPT (Web)", "chatgpt.com", ["/"]),
    # ── Anthropic ───────────────────────────────────────────────────────
    "api.anthropic.com": Provider(
        "Anthropic", "api.anthropic.com",
        ["/v1/messages", "/v1/complete"],
    ),
    "claude.ai": Provider("Claude (Web)", "claude.ai", ["/api/"]),
    # ── Google ──────────────────────────────────────────────────────────
    "generativelanguage.googleapis.com": Provider(
        "Google Gemini", "generativelanguage.googleapis.com",
        ["/v1/", "/v1beta/"],
    ),
    "aiplatform.googleapis.com": Provider(
        "Google Vertex AI", "aiplatform.googleapis.com", ["/v1/"],
    ),
    "us-central1-aiplatform.googleapis.com": Provider(
        "Google Vertex AI (US)", "us-central1-aiplatform.googleapis.com", ["/v1/"],
    ),
    "europe-west4-aiplatform.googleapis.com": Provider(
        "Google Vertex AI (EU)", "europe-west4-aiplatform.googleapis.com", ["/v1/"],
    ),
    "gemini.google.com": Provider("Google Gemini (Web)", "gemini.google.com", ["/"]),
    "bard.google.com": Provider("Google Bard (Web)", "bard.google.com", ["/"]),
    "ml.googleapis.com": Provider("Google Cloud ML", "ml.googleapis.com", ["/"]),
    # ── Microsoft Copilot ────────────────────────────────────────────────
    "copilot.microsoft.com": Provider(
        "Microsoft Copilot", "copilot.microsoft.com", ["/"],
    ),
    "sydney.bing.com": Provider(
        "Microsoft Copilot (Bing)", "sydney.bing.com", ["/"],
    ),
    "edgeservices.bing.com": Provider(
        "Microsoft Copilot (Edge)", "edgeservices.bing.com", ["/"],
    ),
    "www.bing.com": Provider(
        "Bing AI", "www.bing.com", ["/turing/", "/chat"],
    ),
    # ── GitHub Copilot ───────────────────────────────────────────────────
    "api.githubcopilot.com": Provider(
        "GitHub Copilot", "api.githubcopilot.com", ["/"],
    ),
    "copilot-proxy.githubusercontent.com": Provider(
        "GitHub Copilot Proxy", "copilot-proxy.githubusercontent.com", ["/"],
    ),
    "githubcopilot.com": Provider(
        "GitHub Copilot", "githubcopilot.com", ["/"],
    ),
    # ── Azure OpenAI (suffix match — handles <tenant>.openai.azure.com) ─
    ".openai.azure.com": Provider(
        "Azure OpenAI", ".openai.azure.com", ["/openai/"],
    ),
    "inference.ai.azure.com": Provider(
        "Azure AI Inference", "inference.ai.azure.com", ["/models/"],
    ),
    "api.cognitive.microsoft.com": Provider(
        "Azure Cognitive Services", "api.cognitive.microsoft.com", ["/openai/"],
    ),
    # ── AWS ─────────────────────────────────────────────────────────────
    "bedrock-runtime.amazonaws.com": Provider(
        "AWS Bedrock", "bedrock-runtime.amazonaws.com", ["/model/"],
    ),
    # ── Groq ────────────────────────────────────────────────────────────
    "api.groq.com": Provider("Groq", "api.groq.com", ["/openai/v1/"]),
    # ── Mistral ─────────────────────────────────────────────────────────
    "api.mistral.ai": Provider("Mistral", "api.mistral.ai", ["/v1/"]),
    # ── HuggingFace ─────────────────────────────────────────────────────
    "api-inference.huggingface.co": Provider(
        "HuggingFace Inference", "api-inference.huggingface.co", ["/"],
    ),
    "router.huggingface.co": Provider(
        "HuggingFace Serverless", "router.huggingface.co", ["/"],
    ),
    # ── Perplexity ───────────────────────────────────────────────────────
    "api.perplexity.ai": Provider("Perplexity", "api.perplexity.ai", ["/chat/completions"]),
    "perplexity.ai": Provider("Perplexity (Web)", "perplexity.ai", ["/"]),
    # ── xAI Grok ────────────────────────────────────────────────────────
    "api.x.ai": Provider("xAI Grok", "api.x.ai", ["/v1/"]),
    # ── Cohere ──────────────────────────────────────────────────────────
    "api.cohere.com": Provider("Cohere", "api.cohere.com", ["/v1/", "/v2/"]),
    "api.cohere.ai": Provider("Cohere", "api.cohere.ai", ["/v1/", "/v2/"]),
    # ── Together AI ──────────────────────────────────────────────────────
    "api.together.xyz": Provider("Together AI", "api.together.xyz", ["/v1/"]),
    "api.together.ai": Provider("Together AI", "api.together.ai", ["/v1/"]),
    # ── Fireworks AI ─────────────────────────────────────────────────────
    "api.fireworks.ai": Provider("Fireworks AI", "api.fireworks.ai", ["/inference/v1/"]),
    # ── DeepInfra ───────────────────────────────────────────────────────
    "api.deepinfra.com": Provider("DeepInfra", "api.deepinfra.com", ["/v1/"]),
    # ── Replicate ───────────────────────────────────────────────────────
    "api.replicate.com": Provider("Replicate", "api.replicate.com", ["/v1/predictions"]),
    # ── AI21 Labs ───────────────────────────────────────────────────────
    "api.ai21.com": Provider("AI21 Labs", "api.ai21.com", ["/studio/v1/"]),
    # ── DeepSeek ────────────────────────────────────────────────────────
    "api.deepseek.com": Provider("DeepSeek", "api.deepseek.com", ["/v1/"]),
    "chat.deepseek.com": Provider("DeepSeek (Web)", "chat.deepseek.com", ["/"]),
    # ── OpenRouter ───────────────────────────────────────────────────────
    "openrouter.ai": Provider("OpenRouter", "openrouter.ai", ["/api/v1/"]),
    # ── Cerebras ────────────────────────────────────────────────────────
    "api.cerebras.ai": Provider("Cerebras", "api.cerebras.ai", ["/v1/"]),
    # ── SambaNova ────────────────────────────────────────────────────────
    "api.sambanova.ai": Provider("SambaNova", "api.sambanova.ai", ["/v1/"]),
    # ── NVIDIA ──────────────────────────────────────────────────────────
    "integrate.api.nvidia.com": Provider("NVIDIA NIM", "integrate.api.nvidia.com", ["/v1/"]),
    "api.nvcf.nvidia.com": Provider("NVIDIA Cloud Functions", "api.nvcf.nvidia.com", ["/"]),
    # ── Stability AI ────────────────────────────────────────────────────
    "api.stability.ai": Provider("Stability AI", "api.stability.ai", ["/v1/", "/v2beta/"]),
    # ── ElevenLabs ───────────────────────────────────────────────────────
    "api.elevenlabs.io": Provider("ElevenLabs", "api.elevenlabs.io", ["/v1/"]),
    # ── AssemblyAI ───────────────────────────────────────────────────────
    "api.assemblyai.com": Provider("AssemblyAI", "api.assemblyai.com", ["/v2/", "/lemur/"]),
    # ── Cloudflare AI ────────────────────────────────────────────────────
    "api.cloudflare.com": Provider("Cloudflare AI", "api.cloudflare.com", ["/client/v4/accounts/"]),
    # ── RunPod ──────────────────────────────────────────────────────────
    "api.runpod.io": Provider("RunPod", "api.runpod.io", ["/v2/"]),
    # ── Novita AI ────────────────────────────────────────────────────────
    "api.novita.ai": Provider("Novita AI", "api.novita.ai", ["/v3/"]),
    # ── Hyperbolic ───────────────────────────────────────────────────────
    "api.hyperbolic.xyz": Provider("Hyperbolic", "api.hyperbolic.xyz", ["/v1/"]),
    # ── Lepton AI ────────────────────────────────────────────────────────
    "api.lepton.ai": Provider("Lepton AI", "api.lepton.ai", ["/api/v1/"]),
    # ── Baseten ─────────────────────────────────────────────────────────
    "inference.baseten.co": Provider("Baseten", "inference.baseten.co", ["/"]),
    # ── Poe ─────────────────────────────────────────────────────────────
    "poe.com": Provider("Poe", "poe.com", ["/api/"]),
    # ── Mistral Chat ─────────────────────────────────────────────────────
    "chat.mistral.ai": Provider("Mistral Chat (Web)", "chat.mistral.ai", ["/"]),
    # ── Character AI ─────────────────────────────────────────────────────
    "character.ai": Provider("Character.AI", "character.ai", ["/"]),
    "neo.character.ai": Provider("Character.AI (API)", "neo.character.ai", ["/"]),
    # ── Grok (xAI web) ───────────────────────────────────────────────────
    "grok.com": Provider("Grok (Web)", "grok.com", ["/"]),
    "x.com": Provider("Grok on X (Web)", "x.com", ["/i/grok"]),
    # ── Moonshot AI (Kimi) ───────────────────────────────────────────────
    "api.moonshot.cn": Provider("Moonshot AI (Kimi)", "api.moonshot.cn", ["/v1/"]),
    # ── MiniMax ──────────────────────────────────────────────────────────
    "api.minimax.chat": Provider("MiniMax", "api.minimax.chat", ["/v1/"]),
    # ── 01.AI ────────────────────────────────────────────────────────────
    "api.lingyiwanwu.com": Provider("01.AI (Yi)", "api.lingyiwanwu.com", ["/v1/"]),
    # ── Alibaba (Qwen) ───────────────────────────────────────────────────
    "dashscope.aliyuncs.com": Provider("Alibaba DashScope (Qwen)", "dashscope.aliyuncs.com", ["/api/v1/"]),
    # ── Baidu (ERNIE) ────────────────────────────────────────────────────
    "aip.baidubce.com": Provider("Baidu ERNIE", "aip.baidubce.com", ["/rpc/2.0/ai_custom/"]),
    # ── SiliconFlow ──────────────────────────────────────────────────────
    "api.siliconflow.cn": Provider("SiliconFlow", "api.siliconflow.cn", ["/v1/"]),
    # ── Local model servers — untrusted by default ───────────────────────
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
        # Exact match first
        result = BUILTIN_PROVIDERS.get(clean) or self._custom.get(clean)
        if result:
            return result
        # Strip common UI subdomains and retry against the base domain.
        # Catches www.perplexity.ai → perplexity.ai, etc.
        for prefix in ("www.", "chat.", "app.", "web."):
            if clean.startswith(prefix):
                bare = clean[len(prefix):]
                result = BUILTIN_PROVIDERS.get(bare) or self._custom.get(bare)
                if result:
                    return result
                break
        # Suffix match for wildcard entries (e.g. ".openai.azure.com")
        for key, provider in {**BUILTIN_PROVIDERS, **self._custom}.items():
            if key.startswith(".") and clean.endswith(key):
                return provider
        return None

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
