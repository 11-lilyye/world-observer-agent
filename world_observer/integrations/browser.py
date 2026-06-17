from __future__ import annotations

import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from world_observer.integrations.config import Settings
from world_observer.models import WorldSource


class BrowserWorldSource:
    """Boundary for browser-use/computer-use/n8n world collection."""

    DEFAULT_FEEDS = (
        "https://sspai.com/feed",
        "https://www.geekpark.net/rss",
        "https://www.ifanr.com/feed",
        "https://www.ithome.com/rss/",
        "https://www.infoq.cn/feed",
        "https://www.huxiu.com/rss/0.xml",
        "https://www.36kr.com/feed",
        "https://www.technologyreview.com/feed/",
        "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
    )
    DEFAULT_TRENDRADAR_PLATFORMS = (
        ("zhihu", "知乎"),
        ("weibo", "微博"),
        ("douyin", "抖音"),
        ("bilibili-hot-search", "B站热搜"),
        ("toutiao", "今日头条"),
        ("baidu", "百度热搜"),
        ("thepaper", "澎湃新闻"),
        ("wallstreetcn-hot", "华尔街见闻"),
        ("cls-hot", "财联社热门"),
        ("ifeng", "凤凰网"),
        ("tieba", "贴吧"),
    )
    TREND_RADAR_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
    }

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def daily_world_scan(self, limit: int) -> list[WorldSource]:
        if self.settings.world_source_mode != "offline":
            sources = self._trendradar_sources(limit)
            if len(sources) < limit:
                sources.extend(self._rss_sources(limit - len(sources)))
            if sources:
                return self._dedupe(sources)[:limit]
        return self._offline_sources(limit)

    def search_topic(self, topic: str, limit: int) -> list[WorldSource]:
        return self.search_topic_for_platform(topic, platform=None, limit=limit)

    def search_web(self, query: str, limit: int) -> list[WorldSource]:
        if self.settings.world_source_mode == "offline":
            return []
        return self._web_search_sources(query, limit)

    def search_topic_for_platform(self, topic: str, platform: str | None, limit: int) -> list[WorldSource]:
        if self._is_wechat_platform(platform):
            return self._wechat_sources(topic, limit)

        sources = self._topic_sources(topic, platform, max(limit, 24))
        topic_terms = self.topic_terms(topic, platform)
        scored = [(self._score_source(source, topic_terms), source) for source in sources]
        matched = [source for score, source in sorted(scored, key=lambda item: item[0], reverse=True) if score > 0]
        base = matched or sources
        return [
            WorldSource(
                title=source.title,
                url=source.url,
                platform=source.platform,
                excerpt=f"{source.excerpt} 这个角度可用于理解「{topic}」的传播与使用门槛。",
                metrics=source.metrics,
            )
            for source in base[:limit]
        ]

    def wechat_topic_variants(self, topic: str) -> list[str]:
        terms = self._terms(topic)
        variants = [topic]
        variants.extend(f"{term}教程" for term in terms)
        variants.extend(f"{term}经验" for term in terms)
        variants.extend(f"{term}避坑" for term in terms)
        variants.extend(f"{term}复盘" for term in terms)
        variants.extend(f"{term}普通人" for term in terms)
        variants.extend(f"{term}公众号爆款" for term in terms)
        variants.extend(self.topic_terms(topic, platform="公众号"))
        return self._dedupe_strings(variants)

    def topic_terms(self, topic: str, platform: str | None = None) -> list[str]:
        raw_terms = self._terms(topic)
        lowered_topic = topic.lower()
        expansions: list[str] = []

        domain_groups = {
            "ai": [
                "AI",
                "人工智能",
                "AI Agent",
                "智能体",
                "AI工具",
                "自动化",
                "工作流",
                "Claude Code",
                "Codex",
                "OpenClaw",
                "vibe coding",
                "独立开发",
                "效率工具",
            ],
            "creator": ["公众号", "自媒体", "爆款", "选题", "写作", "内容创作", "流量主", "副业"],
            "human": ["普通人", "焦虑", "不确定性", "控制感", "情绪价值", "时代变化", "认知", "成长"],
            "product": ["产品", "商业化", "用户需求", "增长", "工具站", "SaaS", "开源项目"],
            "game": ["游戏", "玩家", "独立游戏", "Steam", "商业化闭环", "玩法", "社区"],
        }
        triggers = {
            "ai": ["ai", "agent", "claude", "codex", "openclaw", "工具", "智能体", "模型"],
            "creator": ["公众号", "文章", "爆款", "内容", "自媒体", "选题"],
            "human": ["人", "心理", "焦虑", "成长", "玄学", "观察"],
            "product": ["产品", "商业", "变现", "工具站", "开源", "项目"],
            "game": ["游戏", "steam", "玩家"],
        }
        for group, words in triggers.items():
            if any(word.lower() in lowered_topic for word in words):
                expansions.extend(domain_groups[group])

        if platform in {"公众号", "wechat", "wechat/blog", "微信"}:
            expansions.extend(["公众号", "收藏", "转发", "小标题", "短段落", "教程", "复盘", "观点"])
        elif platform in {"知乎", "zhihu"}:
            expansions.extend(["为什么", "如何看待", "经验", "反例", "判断标准"])
        elif platform in {"小红书", "xiaohongshu"}:
            expansions.extend(["避坑", "清单", "普通人", "真实体验", "收藏"])

        if not expansions:
            expansions.extend(["热点", "趋势", "人群", "需求", "传播", "案例", "方法"])

        return self._dedupe_strings([*raw_terms, *expansions])

    def fallback_sources_for_platform(self, topic: str, platforms: list[str], limit: int) -> tuple[list[WorldSource], str]:
        for platform in platforms:
            if self._is_wechat_platform(platform):
                sources = self._wechat_sources(topic, limit)
            elif platform in {"知乎", "zhihu"}:
                sources = self._platform_seed(topic, "知乎", limit)
            elif platform in {"博客", "blog"}:
                sources = self._platform_seed(topic, "博客", limit)
            elif platform in {"reddit", "hackernews", "hn", "x"}:
                sources = self.search_topic_for_platform(topic, platform=None, limit=limit)
                sources = [
                    WorldSource(source.title, source.url, source.platform, source.excerpt, {**source.metrics, "reference_platform": source.platform})
                    for source in sources
                ]
            else:
                sources = self.search_topic_for_platform(topic, platform=None, limit=limit)
            if sources:
                return sources[:limit], platform
        return self._offline_sources(limit), "offline"

    def _wechat_sources(self, topic: str, limit: int) -> list[WorldSource]:
        topic_variants = self.wechat_topic_variants(topic)
        local_sources = self._local_wechat_collection_sources(topic_variants, limit)
        if local_sources:
            return local_sources[:limit]

        if not self._should_use_wechat_ai_seed(topic):
            return []

        seeds = [
            ("OpenClaw安装经验：普通人第一次跑通最容易卡在哪", "教程开头先承认读者的挫败感，再给最短成功路径。"),
            ("AI Agent搭建不是技术问题，是路径问题", "公众号读者更容易收藏能拆清步骤、解释失败和给判断标准的文章。"),
            ("普通人搭AI助手：先别追工具，先做一个能用的工作流", "用故事进入，再给方法清单，最后引导读者保存和复盘。"),
            ("Claude Code教程为什么容易被收藏", "标题突出具体对象、具体收益和避坑承诺，正文短段落配图。"),
        ]
        return [
            WorldSource(
                title=title,
                url=f"wechat-local-seed://{index}",
                platform="公众号",
                excerpt=excerpt,
                metrics={"source": "wechat_seed", "reference_platform": "公众号"},
            )
            for index, (title, excerpt) in enumerate(seeds[:limit], start=1)
        ]

    def _should_use_wechat_ai_seed(self, topic: str) -> bool:
        lowered = topic.lower()
        return any(term in lowered for term in ["ai", "agent", "openclaw", "claude", "codex", "工具", "安装", "教程"])

    def health(self) -> dict[str, object]:
        if self.settings.world_source_mode == "offline":
            return {"mode": "offline", "ok": True, "items": len(self._offline_sources(4))}
        trendradar_sources = self._trendradar_sources(3)
        if trendradar_sources:
            return {
                "mode": "trendradar+rss",
                "ok": True,
                "trendradar": True,
                "items": len(trendradar_sources),
                "sample_titles": [source.title for source in trendradar_sources[:3]],
            }
        sources = self._rss_sources(3)
        if sources:
            return {
                "mode": "rss",
                "ok": True,
                "trendradar": False,
                "items": len(sources),
                "sample_titles": [source.title for source in sources[:3]],
            }
        return {"mode": "trendradar+rss", "ok": False, "trendradar": False, "detail": "No TrendRadar/RSS items fetched; offline seeds will be used."}

    def _offline_sources(self, limit: int) -> list[WorldSource]:
        seeds = [
            ("玄学内容为什么又火了", "zhihu", "不确定时代里，人们寻找解释系统和心理安全感。"),
            ("AI工具安装教程收藏量高", "xiaohongshu", "复杂工具被普通人采用时，最缺的是低挫败路径。"),
            ("独立开发者公开失败复盘", "reddit", "真实失败比成功叙事更容易让人产生信任。"),
            ("游戏社区热议开放世界疲劳", "news", "玩家不再只要更大地图，而要更高密度的意义。"),
        ]
        return [
            WorldSource(
                title=title,
                url=f"local://seed/{index}",
                platform=platform,
                excerpt=excerpt,
                metrics={"source": "offline_seed"},
            )
            for index, (title, platform, excerpt) in enumerate(seeds[:limit], start=1)
        ]

    def _rss_sources(self, limit: int) -> list[WorldSource]:
        feeds = self.settings.world_source_feeds or self.DEFAULT_FEEDS
        sources: list[WorldSource] = []
        for feed in feeds:
            sources.extend(self._fetch_feed(feed, limit=max(limit, 6)))
            if len(sources) >= limit:
                break
        return self._dedupe(sources)[:limit]

    def _topic_sources(self, topic: str, platform: str | None, limit: int) -> list[WorldSource]:
        sources: list[WorldSource] = []
        if self.settings.world_source_mode != "offline":
            if platform is None:
                sources.extend(self._web_search_sources(topic, limit=max(6, limit // 2)))
            sources.extend(self._trendradar_sources(limit, topic=topic, platform=platform))
            sources.extend(self._rss_sources(limit))
        if topic and self._needs_fable_sources(topic) and not self._has_fable_sources(sources):
            sources = [*self._fable_fact_sources(), *sources]
        if topic and self._needs_mbti_sources(topic) and not self._has_mbti_sources(sources):
            sources = [*self._mbti_fact_sources(), *sources]
        if not sources:
            sources = self._offline_sources(limit)
        return self._dedupe(sources)[:limit]

    def _needs_fable_sources(self, topic: str) -> bool:
        lowered = topic.lower().replace(" ", "")
        return "fable5" in lowered or "fable 5" in lowered or "mythos5" in lowered or "mythos 5" in lowered

    def _has_fable_sources(self, sources: list[WorldSource]) -> bool:
        haystack = " ".join(f"{source.title} {source.excerpt}" for source in sources).lower()
        return "fable" in haystack and ("anthropic" in haystack or "mythos" in haystack)

    def _needs_mbti_sources(self, topic: str) -> bool:
        lowered = topic.lower().replace(" ", "")
        return "mbti" in lowered or "myersbriggs" in lowered or "人格测试" in topic or "人格类型" in topic

    def _has_mbti_sources(self, sources: list[WorldSource]) -> bool:
        haystack = " ".join(f"{source.title} {source.excerpt}" for source in sources).lower()
        return "mbti" in haystack or "myers-briggs" in haystack or "myers briggs" in haystack

    def _mbti_fact_sources(self) -> list[WorldSource]:
        return [
            WorldSource(
                title="MBTI / Myers-Briggs Type Indicator overview",
                url="https://en.wikipedia.org/wiki/Myers%E2%80%93Briggs_Type_Indicator",
                platform="Wikipedia",
                excerpt=(
                    "MBTI, the Myers-Briggs Type Indicator, is a self-report questionnaire that categorizes people into 16 "
                    "types using four dichotomies: extraversion/introversion, sensing/intuition, thinking/feeling, "
                    "and judging/perceiving. It is popular but controversial regarding validity and reliability."
                ),
                metrics={"source": "mbti_fact_seed", "reference_platform": "web"},
            ),
            WorldSource(
                title="The Myers-Briggs Company: MBTI personality types",
                url="https://www.themyersbriggs.com/en-US/Products-and-Services/Myers-Briggs",
                platform="The Myers-Briggs Company",
                excerpt=(
                    "Official MBTI material positions the assessment as a tool for understanding personality "
                    "preferences, communication, teams, leadership, and personal development."
                ),
                metrics={"source": "mbti_fact_seed", "reference_platform": "official"},
            ),
            WorldSource(
                title="Verywell Mind: How the Myers-Briggs Type Indicator works",
                url="https://www.verywellmind.com/the-myers-briggs-type-indicator-2795583",
                platform="Verywell Mind",
                excerpt=(
                    "Explains the four MBTI preference pairs and 16 types, while noting that the assessment is used "
                    "for self-understanding rather than diagnosis and has scientific criticism."
                ),
                metrics={"source": "mbti_fact_seed", "reference_platform": "web"},
            ),
            WorldSource(
                title="Vox: Why the Myers-Briggs test is totally meaningless",
                url="https://www.vox.com/2014/7/15/5881947/myers-briggs-personality-test-meaningless",
                platform="Vox",
                excerpt=(
                    "A critical article summarizing common objections to MBTI, including test-retest reliability, "
                    "binary categories, and weak predictive validity."
                ),
                metrics={"source": "mbti_fact_seed", "reference_platform": "web"},
            ),
        ]

    def _fable_fact_sources(self) -> list[WorldSource]:
        return [
            WorldSource(
                title="Anthropic releases Claude Fable 5, a safeguarded Mythos-class AI model",
                url="https://www.businessinsider.com/anthropic-claude-fable-5-mythos-class-model-release-2026-6",
                platform="Business Insider",
                excerpt=(
                    "Claude Fable 5 is described as a public, safeguarded version of Anthropic's Mythos-class model. "
                    "It is positioned for software engineering, scientific tasks, and complex reasoning, with sensitive "
                    "cybersecurity, biology, and chemistry queries routed or restricted by safeguards."
                ),
                metrics={"source": "fable_fact_seed", "reference_platform": "English web"},
            ),
            WorldSource(
                title="U.S. export controls force Anthropic to disable Claude Fable 5 and Mythos 5",
                url="https://www.tomshardware.com/tech-industry/artificial-intelligence/us-export-control-order-forces-anthropic-to-disable-claude-fable-5-and-mythos-5-worldwide",
                platform="Tom's Hardware",
                excerpt=(
                    "Reports say the U.S. government ordered Anthropic to disable Fable 5 and Mythos 5 due to national "
                    "security and jailbreak concerns. The order reportedly affected access by foreign nationals, making "
                    "selective access difficult and leading to broader shutdown."
                ),
                metrics={"source": "fable_fact_seed", "reference_platform": "English web"},
            ),
            WorldSource(
                title="Claude Fable 5 blocks some biology and medical questions because of guardrails",
                url="https://www.theverge.com/ai-artificial-intelligence/947973/fable-wont-answer-basic-biology-questions",
                platform="The Verge",
                excerpt=(
                    "Fable 5 is reported to be Anthropic's most powerful public model, but with conservative guardrails. "
                    "Some biology and medical queries are refused or redirected, reflecting concern about misuse in sensitive domains."
                ),
                metrics={"source": "fable_fact_seed", "reference_platform": "English web"},
            ),
            WorldSource(
                title="外媒：Fable 5 和 Mythos 5 被限制引发对 AI 依赖与主权的讨论",
                url="fable-fact-seed://zh-summary",
                platform="中文事实摘要",
                excerpt=(
                    "中文写作应先说明：Fable 5 是 Anthropic Claude 系列中面向公众的高级模型版本，和更敏感的 Mythos-class 能力相关；"
                    "被限制的背景是美国出口管制、安全风险和越狱/网络安全能力担忧。"
                ),
                metrics={"source": "fable_fact_seed", "reference_platform": "中文摘要"},
            ),
        ]

    def _web_search_sources(self, topic: str, limit: int) -> list[WorldSource]:
        queries = self._web_queries(topic)
        sources: list[WorldSource] = []
        per_query = max(3, min(8, limit))
        for query in queries:
            sources.extend(self._duckduckgo_sources(query, per_query))
            if len(sources) >= limit:
                break
        return self._dedupe(sources)[:limit]

    def _web_queries(self, topic: str) -> list[str]:
        cleaned = self._clean(topic)
        queries = [cleaned]
        lowered = cleaned.lower()
        if "fable" in lowered:
            queries.extend(
                [
                    "Claude Fable 5 Anthropic Mythos-class model what is it",
                    "Fable 5 Mythos 5 US export controls Anthropic",
                    "Anthropic Claude Fable 5 model safeguards cybersecurity biology",
                    "Fable 5 模型 Anthropic 美国 禁令 是什么",
                ]
            )
        queries.extend(
            [
                f"{cleaned} English sources",
                f"{cleaned} 中文",
                f"{cleaned} 相关资料 背景 争议",
                f"{cleaned} research paper analysis",
            ]
        )
        return self._dedupe_strings(queries)

    def _duckduckgo_sources(self, query: str, limit: int) -> list[WorldSource]:
        url = "https://duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
        request = urllib.request.Request(url, headers=self.TREND_RADAR_HEADERS)
        try:
            with urllib.request.urlopen(request, timeout=12) as response:
                body = response.read().decode("utf-8", errors="ignore")
        except (OSError, urllib.error.URLError):
            return []

        results: list[WorldSource] = []
        pattern = re.compile(
            r'<a rel="nofollow" class="result__a" href="(?P<href>.*?)".*?>(?P<title>.*?)</a>.*?'
            r'<a class="result__snippet".*?>(?P<snippet>.*?)</a>',
            flags=re.S,
        )
        for index, match in enumerate(pattern.finditer(body), start=1):
            href = html.unescape(match.group("href"))
            title = self._clean(match.group("title"))
            snippet = self._clean(match.group("snippet"))
            real_url = self._duckduckgo_real_url(href)
            if not title:
                continue
            results.append(
                WorldSource(
                    title=title,
                    url=real_url,
                    platform=self._platform(real_url) if real_url else "web",
                    excerpt=snippet[:360],
                    metrics={"source": "web_search", "query": query, "rank": index, "reference_platform": "web"},
                )
            )
            if len(results) >= limit:
                break
        return results

    def _duckduckgo_real_url(self, href: str) -> str:
        parsed = urllib.parse.urlparse(href)
        query = urllib.parse.parse_qs(parsed.query)
        uddg = query.get("uddg")
        if uddg:
            return uddg[0]
        return href

    def _trendradar_sources(self, limit: int, topic: str | None = None, platform: str | None = None) -> list[WorldSource]:
        if not self.settings.trendradar_enabled:
            return []
        platform_pairs = self._trendradar_platform_pairs(platform)
        per_platform_limit = max(5, min(20, limit))
        platform_batches: list[list[WorldSource]] = []
        for platform_id, platform_name in platform_pairs:
            batch = self._fetch_trendradar_platform(platform_id, platform_name, per_platform_limit)
            if batch:
                platform_batches.append(batch)
            if sum(len(batch) for batch in platform_batches) >= limit * 3:
                break

        sources = self._round_robin(platform_batches)
        sources = self._dedupe(sources)
        if topic:
            terms = self.topic_terms(topic, platform)
            scored = [(self._score_source(source, terms), source) for source in sources]
            sources = [source for _, source in sorted(scored, key=lambda item: item[0], reverse=True)]
        return sources[:limit]

    def _fetch_trendradar_platform(self, platform_id: str, platform_name: str, limit: int) -> list[WorldSource]:
        query = urllib.parse.urlencode({"id": platform_id, "latest": ""})
        url = f"{self.settings.trendradar_api_url}?{query}".replace("latest=", "latest")
        request = urllib.request.Request(url, headers=self.TREND_RADAR_HEADERS)
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8", errors="ignore"))
        except (OSError, urllib.error.URLError, json.JSONDecodeError):
            return []

        if data.get("status") not in {"success", "cache"}:
            return []

        sources: list[WorldSource] = []
        for rank, item in enumerate(data.get("items", [])[:limit], start=1):
            title = self._clean(str(item.get("title") or ""))
            if not title:
                continue
            extra = item.get("extra") if isinstance(item.get("extra"), dict) else {}
            hover = self._clean(str(extra.get("hover") or ""))
            info = self._clean(str(extra.get("info") or ""))
            sources.append(
                WorldSource(
                    title=title,
                    url=str(item.get("url") or item.get("mobileUrl") or url),
                    platform=platform_name,
                    excerpt=(hover or info or title)[:300],
                    metrics={
                        "source": "trendradar",
                        "provider": "newsnow",
                        "platform_id": platform_id,
                        "rank": rank,
                        "hotness": info,
                        "updated_time": data.get("updatedTime", ""),
                        "reference_platform": platform_name,
                    },
                )
            )
        return sources

    def _trendradar_platform_pairs(self, platform: str | None = None) -> list[tuple[str, str]]:
        configured = self.settings.trendradar_platforms
        pairs = list(self.DEFAULT_TRENDRADAR_PLATFORMS)
        if configured:
            name_by_id = dict(pairs)
            pairs = [(item, name_by_id.get(item, item)) for item in configured]

        if not platform:
            return pairs

        aliases = {
            "知乎": {"zhihu"},
            "zhihu": {"zhihu"},
            "微博": {"weibo"},
            "weibo": {"weibo"},
            "抖音": {"douyin"},
            "douyin": {"douyin"},
            "B站": {"bilibili-hot-search"},
            "bilibili": {"bilibili-hot-search"},
            "财经": {"wallstreetcn-hot", "cls-hot"},
            "新闻": {"toutiao", "baidu", "thepaper", "ifeng"},
        }
        ids = aliases.get(platform)
        if not ids:
            return pairs
        matched = [pair for pair in pairs if pair[0] in ids]
        return matched or pairs

    def _fetch_feed(self, url: str, limit: int) -> list[WorldSource]:
        request = urllib.request.Request(url, headers={"User-Agent": "WorldObserverAgent/0.1"})
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                body = response.read()
        except (OSError, urllib.error.URLError):
            return []

        try:
            root = ET.fromstring(body)
        except ET.ParseError:
            return []

        items = root.findall(".//item")
        if items:
            return [self._source_from_rss_item(item, url) for item in items[:limit]]

        entries = root.findall("{http://www.w3.org/2005/Atom}entry")
        return [self._source_from_atom_entry(entry, url) for entry in entries[:limit]]

    def _source_from_rss_item(self, item: ET.Element, feed_url: str) -> WorldSource:
        title = self._text(item, "title") or "Untitled"
        link = self._text(item, "link") or feed_url
        excerpt = self._clean(self._text(item, "description") or self._text(item, "summary") or title)
        return WorldSource(
            title=self._clean(title),
            url=link,
            platform=self._platform(feed_url),
            excerpt=excerpt[:300],
            metrics={"source": "rss", "feed": feed_url},
        )

    def _source_from_atom_entry(self, entry: ET.Element, feed_url: str) -> WorldSource:
        namespace = "{http://www.w3.org/2005/Atom}"
        title = entry.findtext(f"{namespace}title") or "Untitled"
        summary = entry.findtext(f"{namespace}summary") or entry.findtext(f"{namespace}content") or title
        link = feed_url
        link_node = entry.find(f"{namespace}link")
        if link_node is not None and link_node.attrib.get("href"):
            link = link_node.attrib["href"]
        return WorldSource(
            title=self._clean(title),
            url=link,
            platform=self._platform(feed_url),
            excerpt=self._clean(summary)[:300],
            metrics={"source": "atom", "feed": feed_url},
        )

    def _text(self, item: ET.Element, tag: str) -> str:
        value = item.findtext(tag)
        return value or ""

    def _clean(self, value: str) -> str:
        value = html.unescape(value)
        value = re.sub(r"<[^>]+>", " ", value)
        return re.sub(r"\s+", " ", value).strip()

    def _platform(self, url: str) -> str:
        if "hnrss" in url:
            return "hackernews"
        if "sspai" in url:
            return "少数派"
        if "geekpark" in url:
            return "极客公园"
        if "ifanr" in url:
            return "爱范儿"
        if "ithome" in url:
            return "IT之家"
        if "infoq" in url:
            return "InfoQ"
        if "huxiu" in url:
            return "虎嗅"
        if "36kr" in url:
            return "36氪"
        if "technologyreview" in url:
            return "mit technology review"
        if "theverge" in url:
            return "the verge"
        return "rss"

    def _terms(self, topic: str) -> list[str]:
        return [term.lower() for term in re.findall(r"[\w\u4e00-\u9fff]+", topic)]

    def _score_source(self, source: WorldSource, terms: list[str]) -> int:
        haystack = f"{source.title} {source.excerpt} {source.platform}".lower()
        score = 0
        for term in terms:
            lowered = term.lower()
            if not lowered:
                continue
            if lowered in source.title.lower():
                score += 4
            score += haystack.count(lowered)
        rank = source.metrics.get("rank")
        if isinstance(rank, int) and rank <= 5:
            score += 1
        return score

    def _local_wechat_collection_sources(self, topic_variants: list[str], limit: int) -> list[WorldSource]:
        roots = [
            self.settings.output_dir / "微信开发平台" / "公众号收藏信息源",
            self.settings.output_dir / "微信开发平台" / "公众号" / "公众号收藏信息源",
        ]
        files: list[Path] = []
        for root in roots:
            if root.exists():
                files.extend(path for path in root.rglob("*") if path.suffix.lower() in {".md", ".txt", ".json", ".csv"})

        strict_terms = [term.lower() for term in self._terms(topic_variants[0] if topic_variants else "")]
        generic_terms = {
            "热点", "趋势", "人群", "需求", "传播", "案例", "方法", "公众号", "收藏", "转发",
            "小标题", "短段落", "教程", "复盘", "观点", "经验", "普通人",
        }
        terms = [
            term.lower()
            for variant in topic_variants
            for term in self._terms(variant)
            if term.lower() not in generic_terms
        ]
        sources: list[WorldSource] = []
        for path in files:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            haystack = f"{path.stem} {text}".lower()
            if strict_terms and not any(term in haystack for term in strict_terms):
                continue
            score = sum(haystack.count(term) for term in terms)
            if score <= 0:
                continue
            sources.append(
                WorldSource(
                    title=path.stem,
                    url=str(path),
                    platform="公众号",
                    excerpt=self._excerpt(text, terms),
                    metrics={"source": "local_wechat_collection", "score": score, "reference_platform": "公众号"},
                )
            )
        return sorted(sources, key=lambda source: source.metrics.get("score", 0), reverse=True)[:limit]

    def _excerpt(self, text: str, terms: list[str]) -> str:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        for line in lines:
            lowered = line.lower()
            if any(term in lowered for term in terms):
                return line[:320]
        return (lines[0] if lines else "")[:320]

    def _platform_seed(self, topic: str, platform: str, limit: int) -> list[WorldSource]:
        if platform == "知乎":
            seeds = [
                (f"{topic} 为什么对普通人这么难", "知乎回答通常先拆问题边界，再给经验、反例和判断标准。"),
                (f"普通人如何理解 {topic}", "知乎读者偏好可讨论的观点、充分限定条件和具体案例。"),
            ]
        else:
            seeds = [
                (f"{topic} 完整实践笔记", "博客读者偏好结构化步骤、背景说明、错误记录和可复现细节。"),
                (f"{topic} 从0到1记录", "博客适合沉淀长链路经验，收藏价值来自完整性。"),
            ]
        return [
            WorldSource(
                title=title,
                url=f"{platform}-seed://{index}",
                platform=platform,
                excerpt=excerpt,
                metrics={"source": "platform_seed", "reference_platform": platform},
            )
            for index, (title, excerpt) in enumerate(seeds[:limit], start=1)
        ]

    def _is_wechat_platform(self, platform: str | None) -> bool:
        return platform in {"公众号", "wechat", "wechat/blog", "微信"}

    def _dedupe_strings(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            normalized = value.strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                result.append(normalized)
        return result

    def _dedupe(self, sources: list[WorldSource]) -> list[WorldSource]:
        seen: set[str] = set()
        result: list[WorldSource] = []
        for source in sources:
            key = source.url or source.title
            if key not in seen:
                seen.add(key)
                result.append(source)
        return result

    def _round_robin(self, batches: list[list[WorldSource]]) -> list[WorldSource]:
        result: list[WorldSource] = []
        max_len = max((len(batch) for batch in batches), default=0)
        for index in range(max_len):
            for batch in batches:
                if index < len(batch):
                    result.append(batch[index])
        return result
