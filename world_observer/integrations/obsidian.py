from __future__ import annotations

import re
from pathlib import Path

from world_observer.models import BrainHit


class ObsidianSearch:
    def __init__(self, vault: Path | None) -> None:
        self.vault = vault

    def search(self, query: str, limit: int = 8) -> list[BrainHit]:
        if not self.vault or not self.vault.exists():
            return []

        terms = [term.lower() for term in re.findall(r"[\w\u4e00-\u9fff]+", query)]
        hits: list[BrainHit] = []
        for path in self.vault.rglob("*.md"):
            if self._skip_path(path):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            lowered = text.lower()
            score = sum(lowered.count(term) for term in terms)
            if score <= 0:
                continue
            title = self._title(path, text)
            excerpt = self._excerpt(text, terms)
            hits.append(BrainHit(path=str(path), title=title, excerpt=excerpt, score=score))

        return sorted(hits, key=lambda hit: hit.score, reverse=True)[:limit]

    def _title(self, path: Path, text: str) -> str:
        for line in text.splitlines():
            if line.startswith("# "):
                return line[2:].strip()
        return path.stem

    def _excerpt(self, text: str, terms: list[str]) -> str:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        for line in lines:
            lowered = line.lower()
            if any(term in lowered for term in terms):
                return line[:240]
        return (lines[0] if lines else "")[:240]

    def _skip_path(self, path: Path) -> bool:
        text = str(path)
        skipped_parts = [
            "04_实验设计记录/微信开发平台/公众号/输出",
            "04_实验设计记录/agent资料库",
            ".obsidian",
        ]
        return any(part in text for part in skipped_parts)
