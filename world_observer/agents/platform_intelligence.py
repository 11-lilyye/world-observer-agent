from __future__ import annotations

from world_observer.integrations.browser import BrowserWorldSource
from world_observer.models import PlatformReferencePlan


class PlatformIntelligenceAgent:
    def __init__(self, world: BrowserWorldSource) -> None:
        self.world = world

    def build_reference_plan(self, topic: str, platform: str | None, limit: int, prefer_web_hotspots: bool = False) -> PlatformReferencePlan:
        output_platform = platform or "公众号"
        if self._is_wechat(output_platform):
            variants = self.world.wechat_topic_variants(topic)
            if self._is_open_topic(topic):
                web_sources = self._usable_reference_sources(self.world.daily_world_scan(max(limit, 12)))
            else:
                web_sources = self._usable_reference_sources(
                    self.world.search_topic_for_platform(topic, platform=None, limit=limit)
                )
            wechat_style_sources = self.world.search_topic_for_platform(topic, platform="公众号", limit=max(2, limit // 2))
            if web_sources:
                sources = self._dedupe([*web_sources, *wechat_style_sources])[:limit]
                return PlatformReferencePlan(
                    output_platform=output_platform,
                    reference_platform="中外网站/相关资料+公众号表达",
                    topic_variants=variants,
                    sources=sources,
                    fallback_path=[
                        "DuckDuckGo/Web 搜索",
                        "TrendRadar/newsnow",
                        "RSS/Atom",
                        "相关文献/资料页",
                        "本地公众号收藏信息源",
                        "公众号爆款库",
                    ],
                    notes=[
                        "公众号输出默认先抓中外网站、热点源或相关资料理解事实、背景和争议。",
                        "公众号资料只用于学习表达、结构和排版，不替代事实来源；Obsidian 用于叠加用户观点。",
                    ],
                )

            sources, reference_platform = self.world.fallback_sources_for_platform(
                topic,
                platforms=["知乎", "博客", "公众号"],
                limit=limit,
            )

            return PlatformReferencePlan(
                output_platform=output_platform,
                reference_platform=reference_platform,
                topic_variants=variants,
                sources=sources,
                fallback_path=["DuckDuckGo/Web 搜索", "TrendRadar/newsnow", "RSS/Atom", "知乎", "博客", "公众号表达结构"],
                notes=[
                    "没有抓到可用同主题 Web 资料时才退到知乎/博客/公众号。",
                    "公众号资料在这里仍主要作为表达结构参考，不作为唯一事实来源。",
                ],
            )

        sources = self.world.search_topic_for_platform(topic, platform=output_platform, limit=limit)
        reference_platform = sources[0].platform if sources else output_platform
        return PlatformReferencePlan(
            output_platform=output_platform,
            reference_platform=reference_platform,
            topic_variants=[topic],
            sources=sources,
            fallback_path=[output_platform],
            notes=[f"{output_platform} 模式按该平台读者习惯选择参考。"],
        )

    def _is_wechat(self, platform: str) -> bool:
        return platform in {"公众号", "wechat", "wechat/blog", "微信"}

    def _is_open_topic(self, topic: str | None) -> bool:
        normalized = (topic or "").strip()
        return normalized in {"", "不限制", "不限制主题", "不限", "不限主题", "任意主题", "自动选题"}

    def _dedupe(self, sources):
        seen: set[str] = set()
        result = []
        for source in sources:
            key = source.url or source.title
            if key in seen:
                continue
            seen.add(key)
            result.append(source)
        return result

    def _usable_reference_sources(self, sources):
        return [source for source in sources if self._is_usable_reference_source(source)]

    def _is_usable_reference_source(self, source) -> bool:
        source_type = source.metrics.get("source")
        if source_type in {"offline_seed", "platform_seed", "wechat_seed"}:
            return False
        url = str(source.url or "")
        if not url:
            return False
        return not (
            url.startswith("local://")
            or url.startswith("wechat-local-seed://")
            or url.startswith("知乎-seed://")
            or url.startswith("博客-seed://")
        )
