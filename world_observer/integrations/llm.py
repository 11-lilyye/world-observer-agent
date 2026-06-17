from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from world_observer.integrations.config import Settings


class LlmClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def complete_json(self, prompt: str, fallback: dict[str, Any], stage: str = "general") -> dict[str, Any]:
        if self.settings.llm_mode == "local" and self._should_use_llm(stage):
            result = self._ollama(prompt)
            if result:
                try:
                    return json.loads(result)
                except json.JSONDecodeError:
                    return fallback
        return fallback

    def complete_text(self, prompt: str, fallback: str, stage: str = "general") -> str:
        text, _used_model = self.complete_text_result(prompt, fallback, stage)
        return text

    def complete_text_result(self, prompt: str, fallback: str, stage: str = "general") -> tuple[str, bool]:
        if self.settings.llm_mode == "local" and self._should_use_llm(stage):
            result = self._ollama(prompt)
            if result:
                return result.strip(), True
        return fallback, False

    def health(self) -> dict[str, Any]:
        if self.settings.llm_mode != "local":
            return {"mode": self.settings.llm_mode, "ok": True, "detail": "local Ollama disabled"}
        request = urllib.request.Request("http://localhost:11434/api/tags", method="GET")
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as error:
            return {"mode": "local", "ok": False, "detail": str(error)}

        models = [item.get("name", "") for item in body.get("models", [])]
        return {
            "mode": "local",
            "ok": self.settings.ollama_model in models,
            "model": self.settings.ollama_model,
            "available_models": models,
        }

    def _should_use_llm(self, stage: str) -> bool:
        depth = self.settings.analysis_depth
        if depth == "off":
            return False
        if depth == "deep":
            return True
        if depth == "balanced":
            return stage in {"article", "feedback"}
        if depth == "fast":
            return False
        return stage in {"article", "feedback"}

    def _ollama(self, prompt: str) -> str | None:
        deadline = time.monotonic() + max(10, self.settings.ollama_timeout_seconds)
        payload = {
            "model": self.settings.ollama_model,
            "prompt": prompt,
            "stream": True,
            "format": "json" if "Return JSON" in prompt else None,
            "options": {"num_predict": self.settings.ollama_num_predict},
        }
        payload = {key: value for key, value in payload.items() if value is not None}
        request = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        chunks: list[str] = []
        try:
            print(
                f"[Ollama] model={self.settings.ollama_model} timeout={self.settings.ollama_timeout_seconds}s "
                f"num_predict={self.settings.ollama_num_predict}",
                flush=True,
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                for raw_line in response:
                    if time.monotonic() > deadline:
                        print("[Ollama] timeout: generation exceeded total deadline", flush=True)
                        return None
                    if not raw_line.strip():
                        continue
                    body = json.loads(raw_line.decode("utf-8"))
                    if body.get("error"):
                        print(f"[Ollama] error: {body.get('error')}", flush=True)
                        return None
                    chunks.append(body.get("response") or "")
                    if body.get("done"):
                        text = "".join(chunks).strip()
                        print(f"[Ollama] done: {len(text)} chars", flush=True)
                        return text
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as error:
            print(f"[Ollama] failed: {error}", flush=True)
            return None
        return "".join(chunks).strip() or None
