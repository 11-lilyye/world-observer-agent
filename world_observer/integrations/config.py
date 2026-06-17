from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    obsidian_vault: Path | None
    output_dir: Path
    llm_mode: str
    ollama_model: str
    openai_api_key: str | None
    world_source_mode: str
    world_source_feeds: tuple[str, ...]
    analysis_depth: str
    creation_engine: str
    allow_fallback_article: bool
    codex_timeout_seconds: int = 240
    auto_local_fallback: bool = False
    ollama_timeout_seconds: int = 180
    ollama_num_predict: int = 1800
    trendradar_enabled: bool = True
    trendradar_api_url: str = "https://newsnow.busiyi.world/api/s"
    trendradar_platforms: tuple[str, ...] = ()
    image_backend: str = "canva_figma"
    image_fallback_backend: str = "prompt_only"
    batch_size: int = 2
    batch_article_min_chars: int = 1000
    batch_article_max_chars: int = 1800

    @classmethod
    def from_env(cls) -> "Settings":
        cls._load_dotenv()
        vault = os.getenv("OBSIDIAN_VAULT")
        output = os.getenv("WORLD_OBSERVER_OUTPUT_DIR")
        feeds = os.getenv("WORLD_OBSERVER_FEEDS", "")
        trendradar_platforms = os.getenv("TREND_RADAR_PLATFORMS", "")
        default_vault = (
            Path.home()
            / "LifeOS"
            / "10_人生OS"
            / "叶总的人生游戏试验站"
            / "叶总的人生地图"
        )
        default_output = default_vault / "03_Research_研究复盘" / "观察实验室" / "04_实验设计记录"
        return cls(
            obsidian_vault=Path(vault).expanduser() if vault else default_vault,
            output_dir=Path(output).expanduser() if output else default_output,
            llm_mode=os.getenv("WORLD_OBSERVER_LLM", "local"),
            ollama_model=os.getenv("OLLAMA_MODEL", "qwen2.5:7b"),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            world_source_mode=os.getenv("WORLD_OBSERVER_SOURCE_MODE", "auto"),
            world_source_feeds=tuple(item.strip() for item in feeds.split(",") if item.strip()),
            analysis_depth=os.getenv("WORLD_OBSERVER_ANALYSIS_DEPTH", "balanced"),
            creation_engine=os.getenv("WORLD_OBSERVER_CREATION_ENGINE", "auto"),
            allow_fallback_article=os.getenv("WORLD_OBSERVER_ALLOW_FALLBACK_ARTICLE", "false").lower() == "true",
            codex_timeout_seconds=int(os.getenv("WORLD_OBSERVER_CODEX_TIMEOUT_SECONDS", "240")),
            auto_local_fallback=os.getenv("WORLD_OBSERVER_AUTO_LOCAL_FALLBACK", "false").lower() in {"1", "true", "yes", "on"},
            ollama_timeout_seconds=int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "180")),
            ollama_num_predict=int(os.getenv("OLLAMA_NUM_PREDICT", "1800")),
            trendradar_enabled=os.getenv("TREND_RADAR_ENABLED", "true").lower() in {"1", "true", "yes", "on"},
            trendradar_api_url=os.getenv("TREND_RADAR_API_URL", "https://newsnow.busiyi.world/api/s"),
            trendradar_platforms=tuple(item.strip() for item in trendradar_platforms.split(",") if item.strip()),
            image_backend=os.getenv("WORLD_OBSERVER_IMAGE_BACKEND", "canva_figma"),
            image_fallback_backend=os.getenv("WORLD_OBSERVER_IMAGE_FALLBACK_BACKEND", "prompt_only"),
            batch_size=int(os.getenv("WORLD_OBSERVER_BATCH_SIZE", "2")),
            batch_article_min_chars=int(os.getenv("WORLD_OBSERVER_BATCH_ARTICLE_MIN_CHARS", "1000")),
            batch_article_max_chars=int(os.getenv("WORLD_OBSERVER_BATCH_ARTICLE_MAX_CHARS", "1800")),
        )

    @staticmethod
    def _load_dotenv() -> None:
        project_root = Path(__file__).resolve().parents[2]
        candidates = [Path.cwd() / ".env", project_root / ".env"]
        for path in candidates:
            if not path.exists():
                continue
            for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
