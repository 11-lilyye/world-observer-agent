from __future__ import annotations

from world_observer.integrations.obsidian import ObsidianSearch
from world_observer.models import BrainHit


class MyBrainAgent:
    def __init__(self, obsidian: ObsidianSearch) -> None:
        self.obsidian = obsidian

    def search(self, topic: str, limit: int) -> list[BrainHit]:
        return self.obsidian.search(topic, limit=limit)

