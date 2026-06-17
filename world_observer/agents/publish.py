from __future__ import annotations

from pathlib import Path


class PublishAgent:
    """Human-in-the-loop publishing boundary."""

    def prepare_wechat(self, article_path: Path) -> Path:
        return article_path

