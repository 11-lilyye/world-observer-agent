from __future__ import annotations

from world_observer.integrations.browser import BrowserWorldSource
from world_observer.integrations.llm import LlmClient
from world_observer.models import Observation, WorldSource


class ObserveAgent:
    def __init__(self, world: BrowserWorldSource, llm: LlmClient) -> None:
        self.world = world
        self.llm = llm

    def run(self, limit: int) -> list[Observation]:
        return self.from_sources(self.world.daily_world_scan(limit))

    def from_sources(self, sources: list[WorldSource]) -> list[Observation]:
        return [self._observe(source) for source in sources]

    def _observe(self, source: WorldSource) -> Observation:
        fallback = {
            "phenomenon": source.title,
            "who_likes_it": "正在寻找解释、效率或情绪共鸣的人",
            "why_they_like_it": source.excerpt,
            "explicit_need": "获取信息、方法或判断依据",
            "hidden_need": "降低不确定感，确认自己不是孤立的",
            "emotion": "安全感、掌控感、被理解感",
            "era_context": "信息过载和工具快速变化让人更依赖可解释的路径",
            "human_pattern": "人在不确定环境中，会偏好能提供解释系统和行动路径的内容",
        }
        data = self.llm.complete_json(
            prompt=(
                "Return JSON with keys: phenomenon, who_likes_it, why_they_like_it, "
                "explicit_need, hidden_need, emotion, era_context, human_pattern.\n"
                f"Source title: {source.title}\nSource excerpt: {source.excerpt}"
            ),
            fallback=fallback,
            stage="observe",
        )
        return Observation(
            phenomenon=data["phenomenon"],
            who_likes_it=data["who_likes_it"],
            why_they_like_it=data["why_they_like_it"],
            explicit_need=data["explicit_need"],
            hidden_need=data["hidden_need"],
            emotion=data["emotion"],
            era_context=data["era_context"],
            human_pattern=data["human_pattern"],
            source=source,
        )
