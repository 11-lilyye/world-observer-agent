from __future__ import annotations

from dataclasses import dataclass, replace
from difflib import SequenceMatcher
import json
from pathlib import Path
import re

from world_observer.agents.brain import MyBrainAgent
from world_observer.agents.creation import CreationAgent
from world_observer.agents.decision import DecisionAgent
from world_observer.agents.feedback import FeedbackAgent
from world_observer.agents.observe import ObserveAgent
from world_observer.agents.pattern import PatternAgent
from world_observer.agents.platform_intelligence import PlatformIntelligenceAgent
from world_observer.agents.viral_intelligence import ViralIntelligenceAgent
from world_observer.integrations.browser import BrowserWorldSource
from world_observer.integrations.codex import CodexClient
from world_observer.integrations.config import Settings
from world_observer.integrations.llm import LlmClient
from world_observer.integrations.obsidian import ObsidianSearch
from world_observer.integrations.storage import Storage
from world_observer.integrations.wechat_importer import WechatArticleImporter
from world_observer.models import Decision, PlatformReferencePlan


@dataclass(frozen=True)
class RunResult:
    summary: str
    path: Path | None = None
    paths: list[Path] | None = None


class WorldObserverApp:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.storage = Storage(settings.output_dir)
        self.llm = LlmClient(settings)
        self.codex = CodexClient(Path(__file__).resolve().parents[1])
        self.world = BrowserWorldSource(settings)
        self.obsidian = ObsidianSearch(settings.obsidian_vault)

    @classmethod
    def from_env(cls) -> "WorldObserverApp":
        return cls(Settings.from_env())

    def observe(self, limit: int = 8) -> RunResult:
        observations = ObserveAgent(self.world, self.llm).run(limit=limit)
        viral_models = ViralIntelligenceAgent(self.llm).analyze_many(observations)
        patterns = PatternAgent(self.llm).extract(observations, viral_models)
        decision = DecisionAgent(self.llm).classify_observations(observations)

        root = self.storage.write_observation_batch(observations, viral_models, patterns, decision)
        return RunResult(
            summary=f"Observe complete: {len(observations)} observations, {len(patterns)} patterns.",
            path=root,
        )

    def suggest_topics(self, count: int = 10, topic_category: str | None = None) -> RunResult:
        sources = self.world.daily_world_scan(max(count * 3, 20))
        topics = self._select_topics_from_sources(sources, count, topic_category)
        label = topic_category or "不限制"
        lines = [f"热点选题建议（类型：{label}）", ""]
        for index, topic in enumerate(topics, start=1):
            lines.append(f"{index}. {topic}")
        lines.extend(
            [
                "",
                "使用示例：",
                f'woa "根据{topics[0] if topics else "选题"}写一篇公众号文章"' if topics else 'woa "写一篇公众号文章"',
                f'woa "创建10篇公众号快写文章 {label}"',
            ]
        )
        return RunResult(summary="\n".join(lines))

    def create(
        self,
        topic: str,
        limit: int = 8,
        target_reader: str | None = None,
        platform: str | None = None,
        purpose: str | None = None,
        engine: str | None = None,
        prefer_web_hotspots: bool = False,
        extra_forbidden_titles: list[str] | None = None,
    ) -> RunResult:
        if self._normalize_batch_topic(topic) is None:
            selected_topics = self._select_topics_from_sources(
                self._expanded_hotspot_sources(1, limit),
                1,
            )
            if selected_topics:
                topic = selected_topics[0]
                prefer_web_hotspots = True
                print(f"[Create] auto selected topic from hotspots: {topic}", flush=True)
        print(f"[Create] topic={topic} platform={platform or '公众号'} purpose={purpose or 'auto'}", flush=True)
        print("[Create] step 1/3: 搜网上资料/热点/相关文献", flush=True)
        print("[Create] step 2/3: 看本地公众号收藏资料并提取格式", flush=True)
        reference_plan = PlatformIntelligenceAgent(self.world).build_reference_plan(
            topic,
            platform or "公众号",
            limit,
            prefer_web_hotspots=prefer_web_hotspots,
        )
        world_hits = reference_plan.sources
        print(f"[Create] world sources={len(world_hits)} reference_platform={reference_plan.reference_platform}", flush=True)
        print("[Create] step 3/3: 提取你的知识库观点", flush=True)
        brain_hits = MyBrainAgent(self.obsidian).search(topic, limit=limit)
        print(f"[Create] Obsidian hits={len(brain_hits)}", flush=True)
        print("[Create] analyzing observations and viral structures...", flush=True)
        observations = ObserveAgent(self.world, self.llm).from_sources(world_hits)
        viral_models = ViralIntelligenceAgent(self.llm).analyze_many(observations)
        patterns = PatternAgent(self.llm).extract(observations, viral_models)
        decision = DecisionAgent(self.llm).classify_creation(topic, brain_hits, patterns)
        forbidden_titles = self.storage.existing_article_titles() + (extra_forbidden_titles or [])
        print(f"[Create] generating article with engine={engine or self.settings.creation_engine} forbidden_titles={len(forbidden_titles)}", flush=True)
        article = CreationAgent(
            self.llm,
            codex=self.codex,
            engine=engine or self.settings.creation_engine,
            allow_fallback=self.settings.allow_fallback_article,
            codex_timeout_seconds=self.settings.codex_timeout_seconds,
            auto_local_fallback=self.settings.auto_local_fallback,
        ).create(
            topic,
            brain_hits,
            world_hits,
            viral_models,
            patterns,
            decision,
            target_reader=target_reader,
            platform=platform,
            purpose=purpose,
            forbidden_titles=forbidden_titles,
        )
        article = self._ensure_unique_article_title(article, forbidden_titles)
        print(f"[Create] article generated: {article.title}", flush=True)
        print(f"[Create] writing article package...", flush=True)

        root = self.storage.write_article(
            topic,
            article,
            brain_hits,
            world_hits,
            viral_models,
            patterns,
            decision,
            reference_plan,
            None,
            None,
        )
        print(f"[Create] wrote: {root}", flush=True)
        return RunResult(summary=f"Create complete: draft generated for {topic}.", path=root)

    def create_many(
        self,
        count: int,
        topic: str | None = None,
        limit: int = 8,
        target_reader: str | None = None,
        platform: str | None = None,
        purpose: str | None = None,
        engine: str | None = None,
        article_length: str | None = None,
        topic_category: str | None = None,
    ) -> RunResult:
        topic = self._normalize_batch_topic(topic)
        topics = self._topic_batch(topic, count, limit, topic_category=topic_category)
        length_mode = (article_length or "fast").lower()
        if len(topics) > 1 and length_mode in {"long", "3000", "长文"}:
            print("[CreateBatch] long-form mode: generating one high-quality article at a time.", flush=True)
        elif len(topics) > 1 and (engine or self.settings.creation_engine) in {"auto", "codex", None}:
            return self._create_many_fast(
                topics=topics,
                limit=limit,
                target_reader=target_reader,
                platform=platform,
                purpose=purpose,
                engine=engine,
                article_length=article_length,
                topic_category=topic_category,
            )
        prefer_web_hotspots = topic is None
        paths: list[Path] = []
        used_titles: list[str] = []
        for item in topics:
            result = self.create(
                topic=item,
                limit=limit,
                target_reader=target_reader,
                platform=platform,
                purpose=purpose,
                engine=engine,
                prefer_web_hotspots=prefer_web_hotspots,
                extra_forbidden_titles=used_titles,
            )
            if result.path:
                paths.append(result.path)
                title = self._title_from_metadata(result.path)
                if title:
                    used_titles.append(title)
        return RunResult(
            summary=f"Create batch complete: {len(paths)} drafts generated.",
            path=paths[0] if paths else None,
            paths=paths,
        )

    def _create_many_fast(
        self,
        topics: list[str],
        limit: int = 8,
        target_reader: str | None = None,
        platform: str | None = None,
        purpose: str | None = None,
        engine: str | None = None,
        article_length: str | None = None,
        topic_category: str | None = None,
    ) -> RunResult:
        print(f"[BatchCreate] fast mode topics={len(topics)} batch_size={self.settings.batch_size}", flush=True)
        print("[BatchCreate] building shared references once...", flush=True)
        sources = self.world.daily_world_scan(max(len(topics) * 2, limit, 20))
        if not sources:
            sources = []
        shared_sources = self._filter_sources_by_category(sources, topic_category)[: max(limit, min(len(sources), 20))]
        if not shared_sources:
            shared_sources = sources[: max(limit, min(len(sources), 20))]
        observations = ObserveAgent(self.world, self.llm).from_sources(shared_sources)
        viral_models = ViralIntelligenceAgent(self.llm).analyze_many(observations)
        patterns = PatternAgent(self.llm).extract(observations, viral_models)
        reference_plan = PlatformReferencePlan(
            output_platform=platform or "公众号",
            reference_platform="批量快写：平台热点+公众号表达结构",
            topic_variants=topics,
            sources=shared_sources,
            fallback_path=["TrendRadar/newsnow", "RSS/Atom", "本地公众号收藏信息源", "公众号爆款库"],
            notes=["批量快写模式：共享热点参考，减少每篇重复搜索和分析。"],
        )
        paths: list[Path] = []
        used_titles: list[str] = []
        forbidden_titles = self.storage.existing_article_titles()
        batch_size = max(1, self.settings.batch_size)
        creator = CreationAgent(
            self.llm,
            codex=self.codex,
            engine=engine or self.settings.creation_engine,
            allow_fallback=self.settings.allow_fallback_article,
            codex_timeout_seconds=self.settings.codex_timeout_seconds,
            auto_local_fallback=self.settings.auto_local_fallback,
        )
        for start in range(0, len(topics), batch_size):
            batch_topics = topics[start : start + batch_size]
            print(f"[BatchCreate] generating batch {start // batch_size + 1}: {len(batch_topics)} articles", flush=True)
            articles = self._create_batch_with_split(
                creator,
                batch_topics,
                shared_sources,
                viral_models,
                patterns,
                platform=platform,
                purpose=purpose,
                target_reader=target_reader,
                forbidden_titles=forbidden_titles + used_titles,
            )
            for item_topic, article in zip(batch_topics, articles):
                article = self._ensure_unique_article_title(article, forbidden_titles + used_titles)
                decision = Decision(
                    label="A Create",
                    reason="批量快写模式：热点选题与公众号表达结构有连接，先生成可精修草稿。",
                    next_action="人工挑选、精修并发布。",
                )
                root = self.storage.write_article(
                    item_topic,
                    article,
                    [],
                    shared_sources,
                    viral_models,
                    patterns,
                    decision,
                    reference_plan,
                    None,
                    None,
                )
                paths.append(root)
                used_titles.append(article.title)
                print(f"[BatchCreate] wrote: {root.name}", flush=True)
        return RunResult(
            summary=f"Fast batch create complete: {len(paths)} drafts generated.",
            path=paths[0] if paths else None,
            paths=paths,
        )

    def _create_batch_with_split(
        self,
        creator: CreationAgent,
        topics: list[str],
        shared_sources: list[object],
        viral_models: list[object],
        patterns: list[str],
        platform: str | None,
        purpose: str | None,
        target_reader: str | None,
        forbidden_titles: list[str],
    ) -> list[object]:
        try:
            return creator.create_batch(
                topics,
                shared_sources,
                viral_models,
                patterns,
                platform=platform,
                purpose=purpose,
                target_reader=target_reader,
                forbidden_titles=forbidden_titles,
                min_chars=self.settings.batch_article_min_chars,
                max_chars=self.settings.batch_article_max_chars,
            )
        except RuntimeError as error:
            if len(topics) <= 1:
                raise
            print(f"[BatchCreate] batch failed, splitting: {error}", flush=True)
            midpoint = max(1, len(topics) // 2)
            return self._create_batch_with_split(
                creator,
                topics[:midpoint],
                shared_sources,
                viral_models,
                patterns,
                platform,
                purpose,
                target_reader,
                forbidden_titles,
            ) + self._create_batch_with_split(
                creator,
                topics[midpoint:],
                shared_sources,
                viral_models,
                patterns,
                platform,
                purpose,
                target_reader,
                forbidden_titles,
            )

    def feedback(self, article_id: str) -> RunResult:
        report = FeedbackAgent(self.llm, self.storage).analyze(article_id)
        path = self.storage.write_feedback(article_id, report)
        return RunResult(summary=f"Feedback complete: report generated for {article_id}.", path=path)

    def import_wechat_articles(self, urls: list[str]) -> RunResult:
        importer = WechatArticleImporter(self.settings)
        paths: list[Path] = []
        for url in urls:
            article = importer.import_url(url)
            paths.append(self.storage.write_imported_wechat_article(article))
        return RunResult(
            summary=f"WeChat import complete: {len(paths)} articles imported.",
            path=paths[0] if paths else None,
            paths=paths,
        )

    def doctor(self) -> RunResult:
        llm_status = self.llm.health()
        codex_status = self.codex.health()
        world_status = self.world.health()
        wechat_import_status = WechatArticleImporter(self.settings).health()
        lines = [
            "World Observer Agent doctor",
            "",
            f"Project output root: {self.settings.output_dir}",
            f"Obsidian vault: {self.settings.obsidian_vault}",
            f"Obsidian readable: {bool(self.settings.obsidian_vault and self.settings.obsidian_vault.exists())}",
            f"Ollama: {'ok' if llm_status.get('ok') else 'needs attention'}",
            f"Ollama detail: {llm_status}",
            f"Codex: {'ok' if codex_status.get('ok') else 'needs attention'}",
            f"Codex detail: {codex_status}",
            f"Creation engine: {self.settings.creation_engine}",
            f"Codex timeout: {self.settings.codex_timeout_seconds}s",
            f"Auto local fallback: {self.settings.auto_local_fallback}",
            f"Image backend: {self.settings.image_backend}",
            f"Image fallback backend: {self.settings.image_fallback_backend}",
            f"Batch size: {self.settings.batch_size}",
            f"Batch article chars: {self.settings.batch_article_min_chars}-{self.settings.batch_article_max_chars}",
            f"Fallback article allowed: {self.settings.allow_fallback_article}",
            f"Analysis depth: {self.settings.analysis_depth}",
            f"World source: {'ok' if world_status.get('ok') else 'fallback/offline'}",
            f"World source detail: {world_status}",
            f"WeChat importer: {'ok' if wechat_import_status.get('crawler_configured') else 'fallback-only'}",
            f"WeChat importer detail: {wechat_import_status}",
            f"Agent library: {self.storage.library_root}",
            f"WeChat unpublished: {self.storage.wechat_root / '未发布'}",
            f"System dir: {self.storage.system_root}",
        ]
        return RunResult(summary="\n".join(lines))

    def _topic_batch(self, topic: str | None, count: int, limit: int, topic_category: str | None = None) -> list[str]:
        topic = self._normalize_batch_topic(topic)
        if count <= 1 and topic:
            return [topic]
        if topic:
            return self._topic_variants(topic, count)

        sources = self._expanded_hotspot_sources(count, limit, topic_category)
        return self._select_topics_from_sources(sources, count, topic_category)

    def _expanded_hotspot_sources(self, count: int, limit: int, topic_category: str | None = None) -> list[object]:
        target = max(count * 12, limit * 4, 80)
        sources = self.world.daily_world_scan(target)
        if len(sources) < count * 4:
            for query in self._category_hotspot_queries(topic_category):
                sources.extend(self.world.search_web(query, limit=max(8, count)))
                if len(sources) >= target:
                    break
        return self._dedupe_sources_by_title_url(sources)

    def _normalize_batch_topic(self, topic: str | None) -> str | None:
        if not topic:
            return None
        cleaned = re.sub(r"\s+", "", topic.strip())
        if cleaned in {"不限制主题", "不限主题", "不限制", "不限", "自动选题", "自动", "全平台热点", "平台热点"}:
            return None
        return topic.strip()

    def _select_topics_from_sources(self, sources: list[object], count: int, topic_category: str | None = None) -> list[str]:
        topics: list[str] = []
        existing_items = self.storage.existing_article_signatures()
        existing_signatures = [item["signature"] for item in existing_items]
        existing_topic_keys = {
            self.storage.normalized_title(" ".join([item.get("topic", ""), item.get("title", "")]))
            for item in existing_items
        }
        selected_signatures: list[str] = []
        selected_topic_keys: set[str] = set()
        selected_subject_counts: dict[str, int] = {}
        filtered_sources = self._filter_sources_by_category(sources, topic_category)
        if len(filtered_sources) < count and self._allows_uncategorized_fill(topic_category):
            seen_source_ids = {id(source) for source in filtered_sources}
            filtered_sources = filtered_sources + [source for source in sources if id(source) not in seen_source_ids]
        for source in filtered_sources:
            candidate = source.title.strip()
            signature = self.storage.topic_signature(candidate)
            if not signature:
                continue
            if self._is_duplicate_topic_candidate(candidate, existing_items, topics):
                continue
            if self._is_duplicate_signature(signature, selected_signatures + existing_signatures):
                continue
            topics.append(candidate)
            selected_signatures.append(signature)
            selected_topic_keys.add(self.storage.normalized_title(candidate))
            self._count_topic_subject(candidate, selected_subject_counts)
            if len(topics) >= count:
                break
        for seed in self._category_seed_topics(topic_category):
            if len(topics) >= count:
                break
            if self._is_duplicate_topic_candidate(seed, existing_items, topics):
                continue
            signature = self.storage.topic_signature(seed)
            if self._is_duplicate_signature(signature, selected_signatures + existing_signatures):
                continue
            topics.append(seed)
            selected_signatures.append(signature)
            selected_topic_keys.add(self.storage.normalized_title(seed))
            self._count_topic_subject(seed, selected_subject_counts)
        while len(topics) < count:
            before = len(topics)
            for fallback in self._fallback_topic_candidates(topic_category):
                if self._is_duplicate_topic_candidate(fallback, existing_items, topics):
                    continue
                key = self.storage.normalized_title(fallback)
                subject = self._topic_subject(fallback)
                if key in selected_topic_keys or key in existing_topic_keys:
                    continue
                if selected_subject_counts.get(subject, 0) >= 2:
                    continue
                topics.append(fallback)
                selected_topic_keys.add(key)
                self._count_topic_subject(fallback, selected_subject_counts)
                if len(topics) >= count:
                    break
            if len(topics) == before:
                print(
                    f"[CreateBatch] unique topic pool exhausted: requested={count}, selected={len(topics)}. "
                    "不会用重复弱选题硬凑数量。",
                    flush=True,
                )
                break
        return topics

    def _allows_uncategorized_fill(self, topic_category: str | None) -> bool:
        return not topic_category or topic_category in {"不限制", "自动", "不限"}

    def _category_hotspot_queries(self, topic_category: str | None) -> list[str]:
        normalized = (topic_category or "不限制").lower().replace("/", "").replace(" ", "")
        queries = {
            "ai科技": [
                "AI Agent 最新热点",
                "人工智能 创业 产品 热点",
                "AI 工具 最新 趋势",
                "Claude Codex 开发者 热点",
            ],
            "商业产品": [
                "商业 产品 创业 热点",
                "消费品牌 产品 增长 案例",
                "SaaS 产品 增长 热点",
                "出海 产品 商业化 热点",
            ],
            "人类观察": [
                "社会情绪 年轻人 热点",
                "普通人 焦虑 趋势",
                "消费心理 社会观察 热点",
            ],
            "情绪共鸣": [
                "年轻人 情绪 共鸣 热点",
                "焦虑 治愈 内容 热点",
                "普通人 情绪价值 热点",
            ],
            "教程工具": [
                "AI 工具 教程 热点",
                "开发工具 安装 教程 热点",
                "效率工具 使用经验 热点",
            ],
        }
        return queries.get(normalized, ["今日 热点 深度 观察", "科技 商业 社会 热点", "公众号 热点 选题"])

    def _dedupe_sources_by_title_url(self, sources: list[object]) -> list[object]:
        seen: set[str] = set()
        result: list[object] = []
        for source in sources:
            title = getattr(source, "title", "").strip()
            url = getattr(source, "url", "").strip()
            key = self.storage.normalized_title(title) or url
            if not key or key in seen:
                continue
            seen.add(key)
            result.append(source)
        return result

    def _is_duplicate_topic_candidate(self, candidate: str, existing_items: list[dict[str, str]], selected_topics: list[str]) -> bool:
        candidate_key = self.storage.normalized_title(candidate)
        candidate_signature = self.storage.topic_signature(candidate)
        candidate_subject = self._topic_subject(candidate)
        candidate_subject_key = self.storage.normalized_title(candidate_subject)
        if not candidate_key or not candidate_signature:
            return True
        for topic in selected_topics:
            if self._topic_similarity(candidate, topic) >= 0.72:
                return True
            if self._topic_subject(topic) == candidate_subject:
                return True
        for item in existing_items:
            existing_text = " ".join([item.get("topic", ""), item.get("title", ""), item.get("folder", "")])
            existing_key = self.storage.normalized_title(existing_text)
            existing_subject_key = self.storage.normalized_title(self._topic_subject(existing_text))
            existing_signature = item.get("signature", "")
            if candidate_key and existing_key and (candidate_key in existing_key or existing_key in candidate_key):
                return True
            if candidate_subject_key and existing_key and candidate_subject_key in existing_key:
                return True
            if existing_subject_key and candidate_key and existing_subject_key in candidate_key:
                return True
            if existing_signature and self._signature_overlap(candidate_signature, existing_signature) >= 0.55:
                return True
            if self._topic_similarity(candidate, existing_text) >= 0.68:
                return True
        return False

    def _topic_similarity(self, left: str, right: str) -> float:
        left_key = self.storage.normalized_title(left)
        right_key = self.storage.normalized_title(right)
        if not left_key or not right_key:
            return 0.0
        return SequenceMatcher(None, left_key, right_key).ratio()

    def _signature_overlap(self, left: str, right: str) -> float:
        left_terms = set(left.split())
        right_terms = set(right.split())
        if not left_terms or not right_terms:
            return 0.0
        return len(left_terms & right_terms) / max(1, min(len(left_terms), len(right_terms)))

    def _topic_subject(self, topic: str) -> str:
        subject = re.split(r"[：:，,。？?]", topic, maxsplit=1)[0]
        subject = re.sub(r"^(为什么|从|关于)", "", subject)
        return subject.strip()[:18] or topic.strip()[:18]

    def _count_topic_subject(self, topic: str, counts: dict[str, int]) -> None:
        subject = self._topic_subject(topic)
        counts[subject] = counts.get(subject, 0) + 1

    def _fallback_topic(self, index: int, topic_category: str | None) -> str:
        candidates = self._fallback_topic_candidates(topic_category)
        if candidates:
            return candidates[(index - 1) % len(candidates)]
        return self._last_resort_topic(index, topic_category)

    def _fallback_topic_candidates(self, topic_category: str | None) -> list[str]:
        seeds = self._category_seed_topics(topic_category)
        generic = [
            "AI工具普及后，普通人为什么更需要判断力",
            "为什么越来越多内容让人收藏，却很少让人行动",
            "热点变多之后，真正稀缺的是解释系统",
            "普通人做低成本实验，最难的不是开始而是验证",
            "内容生产变快以后，什么才算真正有价值",
        ]
        category = (topic_category or "").lower().replace("/", "").replace(" ", "")
        if category == "商业产品":
            subjects = [
                "AI工具站",
                "知识付费产品",
                "低价订阅工具",
                "小红书店铺",
                "本地生活团购",
                "独立开发者产品",
                "SaaS小工具",
                "情绪消费品牌",
                "银发经济产品",
                "宠物消费品牌",
                "AI硬件",
                "出海工具产品",
                "会员制社群",
                "效率插件",
                "垂直社区",
                "个人IP课程",
                "二手交易平台",
                "健康管理应用",
                "儿童教育产品",
                "线下体验店",
            ]
            angles = [
                "为什么容易被收藏但很难被持续使用",
                "真正应该先验证的是付费场景",
                "用户说喜欢和愿意付费之间差了什么",
                "从第一批真实用户看需求强度",
                "为什么功能越多反而越难卖",
                "怎样判断它是刚需、痒点还是情绪消费",
                "增长瓶颈往往不是流量，而是复购理由",
                "普通人做它，最容易高估哪件事",
                "什么时候该做产品，什么时候只该做服务",
                "从爆火到消失，中间通常发生了什么",
            ]
            commercial_topics: list[str] = []
            for subject_index, subject in enumerate(subjects):
                for offset in range(2):
                    angle = angles[(subject_index * 2 + offset) % len(angles)]
                    commercial_topics.append(f"{subject}：{angle}")
            for angle_index, angle in enumerate(angles):
                for subject_index, subject in enumerate(subjects):
                    rotated = angles[(angle_index + subject_index) % len(angles)]
                    commercial_topics.append(f"{subject}：{rotated}")
            return seeds + commercial_topics
        return seeds + generic

    def _last_resort_topic(self, index: int, topic_category: str | None) -> str:
        label = topic_category or "综合"
        dimensions = ["用户需求", "付费动机", "传播结构", "行动门槛", "反馈机制", "复购理由", "信任成本", "场景强度"]
        dimension = dimensions[(index - 1) % len(dimensions)]
        return f"{label}观察：从{dimension}重新选择第{index}个选题"

    def _filter_sources_by_category(self, sources: list[object], topic_category: str | None) -> list[object]:
        if not topic_category or topic_category in {"不限制", "自动", "不限"}:
            return sources
        terms = self._category_terms(topic_category)
        if not terms:
            return sources
        matched = [
            source
            for source in sources
            if any(term.lower() in f"{getattr(source, 'title', '')} {getattr(source, 'excerpt', '')} {getattr(source, 'platform', '')}".lower() for term in terms)
        ]
        return matched

    def _category_terms(self, category: str) -> list[str]:
        normalized = category.lower().replace("/", "").replace(" ", "")
        mapping = {
            "ai科技": ["ai", "人工智能", "agent", "模型", "科技", "工具", "codex", "claude", "机器人"],
            "科技": ["ai", "人工智能", "科技", "工具", "模型", "芯片", "机器人"],
            "人类观察": ["普通人", "心理", "情绪", "焦虑", "社会", "年轻人", "消费", "玄学"],
            "商业产品": ["商业", "产品", "公司", "品牌", "增长", "消费", "创业", "出海"],
            "情绪共鸣": ["焦虑", "情绪", "迷茫", "关系", "治愈", "孤独", "普通人"],
            "教程工具": ["教程", "工具", "安装", "配置", "避坑", "指南", "上手"],
        }
        return mapping.get(normalized, [category])

    def _category_seed_topics(self, category: str | None) -> list[str]:
        if not category or category in {"不限制", "自动", "不限"}:
            return []
        normalized = category.lower().replace("/", "").replace(" ", "")
        seeds = {
            "ai科技": [
                "AI Agent为什么开始从玩具变成工作流",
                "普通人使用AI工具，真正的门槛不是工具而是任务拆解",
                "Claude Code和Codex正在改变个人开发者的工作方式",
                "AI自动化最值得观察的不是效率，而是判断权如何转移",
                "为什么越来越多人想搭自己的本地AI助手",
                "普通人做AI工作流，最容易失败的不是模型而是场景",
                "AI工具收藏越多，为什么行动反而可能越少",
                "从AI Agent热潮看见个人生产力的新分工",
            ],
            "科技": [
                "AI工具普及后，普通人的学习方式正在改变",
                "新技术为什么总是先制造焦虑，再制造新机会",
            ],
            "人类观察": [
                "为什么普通人越来越需要解释系统",
                "不确定时代，人们为什么更愿意收藏方法论",
                "玄学内容流行背后的控制感需求",
                "年轻人为什么开始用低成本实验重新定位自己",
            ],
            "商业产品": [
                "AI工具站为什么容易火，也容易消失",
                "一个产品真正被需要，往往不是因为功能更多",
                "普通人做小产品，最先验证的不是商业模式而是需求强度",
            ],
            "情绪共鸣": [
                "为什么很多人不是懒，而是缺少开始的确定感",
                "焦虑内容为什么容易传播，因为它提供了命名能力",
                "普通人的情绪价值，正在变成内容传播的核心入口",
            ],
            "教程工具": [
                "一个工具教程为什么会被收藏，关键不是步骤而是避坑",
                "普通人上手AI工具，最需要的是最短成功路径",
                "技术教程真正解决的不是安装，而是降低挫败感",
            ],
        }
        return seeds.get(normalized, [])

    def _topic_variants(self, topic: str, count: int) -> list[str]:
        templates = [
            "{topic}：普通人最容易误解的地方",
            "从{topic}看见一个正在变化的机会",
            "{topic}实践复盘：从第一步到真实反馈",
            "{topic}背后的用户需求和时代情绪",
            "如果重新理解{topic}，普通人该先做什么",
            "{topic}为什么值得收藏，而不只是围观",
            "{topic}的失败点：哪些经验不能直接复制",
            "{topic}给内容创作者的启发",
            "{topic}和低成本实验：先做出来再判断",
            "关于{topic}，我更关心它改变了谁",
        ]
        variants = [item.format(topic=topic) for item in templates]
        while len(variants) < count:
            variants.append(f"{topic}的第{len(variants) + 1}个观察角度")
        existing_signatures = [item["signature"] for item in self.storage.existing_article_signatures()]
        selected: list[str] = []
        for variant in variants:
            signature = self.storage.topic_signature(variant)
            if signature in existing_signatures:
                continue
            selected.append(variant)
            if len(selected) >= count:
                break
        while len(selected) < count:
            selected.append(f"{topic}的第{len(selected) + 1}个观察角度")
        return selected

    def _is_duplicate_signature(self, signature: str, existing: list[str]) -> bool:
        if not signature:
            return True
        signature_terms = set(signature.split())
        for item in existing:
            if not item:
                continue
            item_terms = set(item.split())
            shared_entities = {
                term
                for term in signature_terms & item_terms
                if re.fullmatch(r"[a-zA-Z][a-zA-Z0-9+-]*", term)
            }
            if signature == item:
                return True
            if len(shared_entities) >= 2:
                return True
            if len(signature_terms & item_terms) >= 3:
                return True
            overlap = len(signature_terms & item_terms) / max(1, min(len(signature_terms), len(item_terms)))
            if overlap >= 0.72:
                return True
            if SequenceMatcher(None, signature, item).ratio() >= 0.82:
                return True
        return False

    def _ensure_unique_article_title(self, article: object, forbidden_titles: list[str]) -> object:
        title = getattr(article, "title", "")
        if not self._is_duplicate_title(title, forbidden_titles):
            return article

        print(f"[Create] duplicate title detected: {title}", flush=True)
        for candidate in self._candidate_titles_from_strategy(getattr(article, "structure_strategy", "")):
            if not self._is_duplicate_title(candidate, forbidden_titles):
                print(f"[Create] title replaced with: {candidate}", flush=True)
                return replace(
                    article,
                    title=candidate,
                    markdown=self._replace_markdown_title(getattr(article, "markdown", ""), candidate),
                    cover_prompt=f"为「{candidate}」生成一张公众号封面：克制、清晰、有真实人物/场景感，避免营销感。",
                )

        fallback = self._unique_title_variant(title or "新的公众号观察", forbidden_titles)
        print(f"[Create] title replaced with fallback: {fallback}", flush=True)
        return replace(
            article,
            title=fallback,
            markdown=self._replace_markdown_title(getattr(article, "markdown", ""), fallback),
            cover_prompt=f"为「{fallback}」生成一张公众号封面：克制、清晰、有真实人物/场景感，避免营销感。",
        )

    def _candidate_titles_from_strategy(self, strategy: str) -> list[str]:
        titles: list[str] = []
        in_pool = False
        for line in strategy.splitlines():
            stripped = line.strip()
            if stripped.startswith("标题池"):
                in_pool = True
                continue
            if in_pool and stripped.startswith("- "):
                title = stripped[2:].strip()
                if title:
                    titles.append(title)
        return titles

    def _replace_markdown_title(self, markdown: str, title: str) -> str:
        lines = markdown.splitlines()
        for index, line in enumerate(lines):
            if line.startswith("# "):
                lines[index] = f"# {title}"
                return "\n".join(lines).strip() + "\n"
        return f"# {title}\n\n{markdown.strip()}\n"

    def _unique_title_variant(self, title: str, forbidden_titles: list[str]) -> str:
        bases = [
            f"{title}：一个新的观察角度",
            f"{title}：这次我更关心什么",
            f"{title}：普通人可以怎么理解",
            f"{title}：从现象到行动",
        ]
        for candidate in bases:
            if not self._is_duplicate_title(candidate, forbidden_titles):
                return candidate
        for index in range(2, 20):
            candidate = f"{title}：新的观察角度{index}"
            if not self._is_duplicate_title(candidate, forbidden_titles):
                return candidate
        return f"{title}：{len(forbidden_titles) + 1}"

    def _is_duplicate_title(self, title: str, forbidden_titles: list[str]) -> bool:
        title_key = self.storage.normalized_title(title)
        if not title_key:
            return True
        for item in forbidden_titles:
            item_key = self.storage.normalized_title(item)
            if not item_key:
                continue
            if title_key == item_key:
                return True
            if SequenceMatcher(None, title_key, item_key).ratio() >= 0.9:
                return True
        return False

    def _title_from_metadata(self, root: Path) -> str | None:
        metadata_path = root / "metadata.json"
        if metadata_path.exists():
            try:
                data = json.loads(metadata_path.read_text(encoding="utf-8", errors="ignore"))
                title = str(data.get("title") or "").strip()
                if title:
                    return title
            except (OSError, json.JSONDecodeError):
                pass
        article_path = root / "article.md"
        if article_path.exists():
            try:
                for line in article_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                    if line.startswith("# "):
                        return line[2:].strip()
            except OSError:
                pass
        return None
