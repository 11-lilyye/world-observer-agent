from __future__ import annotations

from world_observer.app import WorldObserverApp
from world_observer.integrations.config import Settings


def test_create_smoke(tmp_path):
    settings = Settings(
        obsidian_vault=None,
        output_dir=tmp_path / "04_实验设计记录",
        llm_mode="off",
        ollama_model="none",
        openai_api_key=None,
        world_source_mode="offline",
        world_source_feeds=(),
        analysis_depth="off",
        creation_engine="local",
        allow_fallback_article=True,
    )
    app = WorldObserverApp(settings)
    result = app.create("OpenClaw安装经验", limit=2)
    assert result.path is not None
    assert (result.path / "article.md").exists()
    assert (result.path / "analysis.md").exists()
    assert (result.path / "metadata.json").exists()
