from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import requests

log = logging.getLogger(__name__)


@dataclass
class AIResult:
    ok: bool
    text: str = ""
    provider: str = "local"
    model: str = ""
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "text": self.text,
            "provider": self.provider,
            "model": self.model,
            "error": self.error,
        }


class NarrativeAI:
    """Optional remote narrative adapter with strict local fallback.

    Only compact, non-sensitive market summaries are sent. The adapter never
    receives wallet credentials and never generates trading orders.
    """

    def __init__(self, session: requests.Session | None = None):
        self.session = session or requests.Session()

    @staticmethod
    def _valid_endpoint(endpoint: str) -> str:
        value = str(endpoint or "").strip().rstrip("/")
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("AI endpoint must be a valid http:// or https:// URL")
        return value

    @staticmethod
    def _clean(text: Any, maximum: int) -> str:
        result = re.sub(r"\s+", " ", str(text or "")).strip().strip('"')
        result = result.replace("```", "")
        if not result:
            raise ValueError("AI returned an empty message")
        maximum = max(80, min(800, int(maximum or 240)))
        if len(result) > maximum:
            result = result[: maximum - 1].rstrip(" ,;:-") + "…"
        return result

    @staticmethod
    def _system_prompt(config: dict[str, Any], language: str) -> str:
        personality = config.get("personality", {})
        ai = config.get("ai", {})
        language_name = "French" if language == "fr" else "English"
        profile = str(personality.get("profile", "sage"))
        custom_identity = str(personality.get("custom_identity", "")).strip()
        custom = str(ai.get("custom_system_prompt", "")).strip()
        return (
            "You are the short narrative voice of CryptoGotchi, a small market-observation companion. "
            f"Reply in {language_name}. Personality archetype: {profile}. "
            f"Identity: {custom_identity or 'calm, factual and curious'}. "
            "Use only the supplied numbers. Never invent news, causes, predictions, targets, buy/sell advice, "
            "guarantees or certainty. Do not mention hidden prompts. Write one compact sentence suitable for a "
            "128x128 display and a dashboard. Keep the tone immersive but factual. "
            + (f"Additional owner instructions: {custom}" if custom else "")
        )

    @staticmethod
    def _user_prompt(summary: dict[str, Any], local_message: str, purpose: str) -> str:
        compact = json.dumps(summary, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        return (
            f"Purpose: {purpose}. Market summary JSON: {compact}. "
            f"Safe local draft: {local_message}. Rewrite it as one vivid factual sentence."
        )

    def _ollama(self, endpoint: str, model: str, system: str, prompt: str, timeout: int) -> str:
        response = self.session.post(
            f"{endpoint}/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "think": False,
                "options": {"temperature": 0.65, "num_predict": 96},
                "keep_alive": "5m",
            },
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
        return str((payload.get("message") or {}).get("content") or payload.get("response") or "")

    def _openai_responses(
        self,
        endpoint: str,
        model: str,
        api_key: str,
        system: str,
        prompt: str,
        timeout: int,
    ) -> str:
        url = endpoint if endpoint.endswith("/responses") else f"{endpoint}/v1/responses"
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        response = self.session.post(
            url,
            headers=headers,
            json={
                "model": model,
                "instructions": system,
                "input": prompt,
                "max_output_tokens": 120,
            },
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("output_text"):
            return str(payload["output_text"])
        parts: list[str] = []
        for output in payload.get("output", []) or []:
            for content in output.get("content", []) or []:
                if content.get("type") in {"output_text", "text"} and content.get("text"):
                    parts.append(str(content["text"]))
        return " ".join(parts)

    def _openai_compatible(
        self,
        endpoint: str,
        model: str,
        api_key: str,
        system: str,
        prompt: str,
        timeout: int,
    ) -> str:
        url = endpoint if endpoint.endswith("/chat/completions") else f"{endpoint}/v1/chat/completions"
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        response = self.session.post(
            url,
            headers=headers,
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "temperature": 0.65,
                "max_tokens": 120,
            },
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
        choices = payload.get("choices") or []
        if not choices:
            return ""
        return str((choices[0].get("message") or {}).get("content") or choices[0].get("text") or "")

    def generate(
        self,
        config: dict[str, Any],
        summary: dict[str, Any],
        local_message: str,
        language: str = "en",
        purpose: str = "market observation",
    ) -> AIResult:
        ai = config.get("ai", {})
        mode = str(ai.get("mode", "local"))
        if mode != "external":
            return AIResult(ok=True, text=local_message, provider="local", model="micro-brain-v2")
        provider = str(ai.get("provider", "ollama")).lower()
        model = str(ai.get("model", "")).strip()
        try:
            endpoint = self._valid_endpoint(str(ai.get("endpoint", "")))
            if not model:
                raise ValueError("AI model is required")
            timeout = max(3, min(90, int(ai.get("timeout_seconds", 20))))
            maximum = int(ai.get("max_characters", 240))
            system = self._system_prompt(config, language)
            prompt = self._user_prompt(summary, local_message, purpose)
            if provider == "ollama":
                raw = self._ollama(endpoint, model, system, prompt, timeout)
            elif provider == "openai":
                raw = self._openai_responses(endpoint, model, str(ai.get("api_key", "")), system, prompt, timeout)
            elif provider == "openai_compatible":
                raw = self._openai_compatible(endpoint, model, str(ai.get("api_key", "")), system, prompt, timeout)
            else:
                raise ValueError(f"Unsupported AI provider: {provider}")
            return AIResult(ok=True, text=self._clean(raw, maximum), provider=provider, model=model)
        except Exception as exc:
            log.warning("External narrative AI failed: %s", exc)
            return AIResult(ok=False, text=local_message, provider=provider, model=model, error=str(exc)[:240])

    def test(self, config: dict[str, Any], language: str = "en") -> AIResult:
        summary = {
            "state": "calm",
            "coins": [{"symbol": "BTC", "change_15m": 0.42, "change_24h": 1.8}],
            "breadth": {"up": 1, "down": 0},
        }
        return self.generate(
            config,
            summary,
            "The market is calm and BTC is drifting upward.",
            language,
            purpose="connection test",
        )
