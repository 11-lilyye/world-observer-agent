from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class WorldSource:
    title: str
    url: str
    platform: str
    excerpt: str
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PlatformReferencePlan:
    output_platform: str
    reference_platform: str
    topic_variants: list[str]
    sources: list[WorldSource]
    fallback_path: list[str]
    notes: list[str]


@dataclass(frozen=True)
class Observation:
    phenomenon: str
    who_likes_it: str
    why_they_like_it: str
    explicit_need: str
    hidden_need: str
    emotion: str
    era_context: str
    human_pattern: str
    source: WorldSource
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


@dataclass(frozen=True)
class ViralModel:
    title: str
    click_reason: str
    finish_reason: str
    save_reason: str
    share_reason: str
    comment_reason: str
    title_mechanics: list[str]
    content_structure: list[str]
    expression_notes: list[str]
    reference_platform: str = "unknown"
    title_formula: str = ""
    opening_structure: list[str] = field(default_factory=list)
    body_structure: list[str] = field(default_factory=list)
    layout_notes: list[str] = field(default_factory=list)
    propagation_reason: list[str] = field(default_factory=list)
    migration_notes: list[dict[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class BrainHit:
    path: str
    title: str
    excerpt: str
    score: int


@dataclass(frozen=True)
class Decision:
    label: str
    reason: str
    next_action: str


@dataclass(frozen=True)
class ArticleDraft:
    title: str
    markdown: str
    cover_prompt: str
    image_prompts: list[str]
    structure_strategy: str


@dataclass(frozen=True)
class ArticleStrategy:
    target_reader: str
    platform: str
    purpose: str
    reference_strength: str
    structure: list[str]
    expression_style: list[str]
    default_principle_used: bool = False


@dataclass(frozen=True)
class ImportedWechatArticle:
    title: str
    url: str
    author: str
    publish_time: str
    markdown: str
    html: str = ""
    account_desc: str = ""
    images: list[str] = field(default_factory=list)
    importer: str = "unknown"
