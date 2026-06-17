from __future__ import annotations

import json
from typing import Any

from world_observer.integrations.llm import LlmClient
from world_observer.models import Observation, ViralModel


class PatternAgent:
    def __init__(self, llm: LlmClient) -> None:
        self.llm = llm

    def extract(self, observations: list[Observation], viral_models: list[ViralModel]) -> list[str]:
        patterns: list[str] = []
        for observation in observations:
            fallback = {
                "patterns": [
                    observation.human_pattern,
                    f"{observation.hidden_need} 经常比 {observation.explicit_need} 更能解释传播。",
                ]
            }
            data = self.llm.complete_json(
                prompt=(
                    "Return JSON with key patterns as a list of concise Chinese human behavior patterns.\n"
                    f"Observation: {observation}"
                ),
                fallback=fallback,
                stage="pattern",
            )
            patterns.extend(self._as_patterns(data.get("patterns", [])))
        return self._dedupe(patterns)

    def _as_patterns(self, value: Any) -> list[str]:
        if isinstance(value, list):
            return [self._stringify(item) for item in value]
        return [self._stringify(value)]

    def _stringify(self, value: Any) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            for key in ("pattern", "规律", "human_pattern", "summary"):
                item = value.get(key)
                if isinstance(item, str):
                    return item
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    def _dedupe(self, patterns: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for pattern in patterns:
            normalized = pattern.strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                result.append(normalized)
        return result
