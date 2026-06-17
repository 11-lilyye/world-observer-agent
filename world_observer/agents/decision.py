from __future__ import annotations

from world_observer.integrations.llm import LlmClient
from world_observer.models import BrainHit, Decision, Observation


class DecisionAgent:
    def __init__(self, llm: LlmClient) -> None:
        self.llm = llm

    def classify_observations(self, observations: list[Observation]) -> list[Decision]:
        decisions: list[Decision] = []
        for observation in observations:
            decisions.append(
                Decision(
                    label="B Research",
                    reason=f"现象值得保留：{observation.human_pattern}",
                    next_action="继续收集案例，等待与个人知识库形成更强连接。",
                )
            )
        return decisions

    def classify_creation(self, topic: str, brain_hits: list[BrainHit], patterns: list[str]) -> Decision:
        if brain_hits and patterns:
            return Decision(
                label="A Create",
                reason="世界现象和个人知识库都有连接，可以输出作品。",
                next_action="生成未发布草稿，等待人工检查后发布。",
            )
        if patterns:
            return Decision(
                label="B Research",
                reason="已有世界模式，但个人知识连接不足。",
                next_action="先生成研究型草稿，并标记需要补充个人经验。",
            )
        return Decision(
            label="C Observe",
            reason=f"{topic} 暂时缺少足够强的连接。",
            next_action="保存观察，不急于发布。",
        )

