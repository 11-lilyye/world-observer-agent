from __future__ import annotations

from world_observer.integrations.codex import CodexClient
from world_observer.integrations.llm import LlmClient
from world_observer.models import ArticleDraft, ArticleStrategy, BrainHit, Decision, ViralModel, WorldSource


class CreationAgent:
    def __init__(
        self,
        llm: LlmClient,
        codex: CodexClient | None = None,
        engine: str = "auto",
        allow_fallback: bool = False,
        codex_timeout_seconds: int = 240,
        auto_local_fallback: bool = False,
    ) -> None:
        self.llm = llm
        self.codex = codex
        self.engine = engine
        self.allow_fallback = allow_fallback
        self.codex_timeout_seconds = codex_timeout_seconds
        self.auto_local_fallback = auto_local_fallback

    def create(
        self,
        topic: str,
        brain_hits: list[BrainHit],
        world_hits: list[WorldSource],
        viral_models: list[ViralModel],
        patterns: list[str],
        decision: Decision,
        target_reader: str | None = None,
        platform: str | None = None,
        purpose: str | None = None,
        forbidden_titles: list[str] | None = None,
    ) -> ArticleDraft:
        llm_health = self.llm.health()
        codex_health = self.codex.health() if self.codex else {"ok": False, "detail": "codex client not configured"}
        print(f"[CreationAgent] engine={self.engine}")
        print(f"[CreationAgent] llm_health={llm_health}")
        print(f"[CreationAgent] codex_health={codex_health}")

        strategy = self._build_strategy(topic, world_hits, viral_models, target_reader, platform, purpose)
        themes = self._theme_candidates(topic, strategy, viral_models, forbidden_titles or [])
        selected = themes[0]
        prompt = self._article_prompt(topic, brain_hits, world_hits, viral_models, patterns, decision, strategy, themes, forbidden_titles or [])
        print(f"[CreationAgent] prompt chars={len(prompt)}", flush=True)

        engine = self._normalized_engine()
        if engine == "local":
            if not llm_health.get("ok"):
                raise RuntimeError(f"本地 Ollama 不可用: {llm_health.get('detail') or llm_health}")
            markdown = self.llm.complete_text(prompt=prompt, fallback="", stage="article")
            print(f"[CreationAgent] local returned chars={len(markdown)}", flush=True)
            if not self._is_internal_analysis(markdown):
                print("[CreationAgent] local article accepted", flush=True)
                return self._draft(selected["title"], markdown, strategy, themes)
            return self._fallback_or_raise("本地 Ollama 未返回有效公众号正文。", topic, selected, strategy, themes)

        if engine == "codex":
            if not self.codex or not codex_health.get("ok"):
                raise RuntimeError(f"Codex 不可用: {codex_health.get('detail') or codex_health}")
            markdown = self.codex.generate_text(prompt, fallback="", timeout_seconds=self.codex_timeout_seconds)
            print(f"[CreationAgent] codex returned chars={len(markdown)}", flush=True)
            if not self._is_internal_analysis(markdown):
                print("[CreationAgent] codex article accepted", flush=True)
                return self._draft(selected["title"], markdown, strategy, themes)
            return self._fallback_or_raise("Codex 未返回有效公众号正文。", topic, selected, strategy, themes)

        if engine == "auto":
            if self.codex and codex_health.get("ok"):
                markdown = self.codex.generate_text(prompt, fallback="", timeout_seconds=self.codex_timeout_seconds)
                print(f"[CreationAgent] auto/codex returned chars={len(markdown)}", flush=True)
                if not self._is_internal_analysis(markdown):
                    print("[CreationAgent] auto/codex article accepted", flush=True)
                    return self._draft(selected["title"], markdown, strategy, themes)
                if not self.auto_local_fallback:
                    raise RuntimeError(
                        f"Codex 在 {self.codex_timeout_seconds}s 内未返回有效公众号正文。"
                        "请稍后重试，或设置 WORLD_OBSERVER_CODEX_TIMEOUT_SECONDS=360。"
                    )
                print("[CreationAgent] auto/codex output rejected, falling back to local because WORLD_OBSERVER_AUTO_LOCAL_FALLBACK=true", flush=True)
            if llm_health.get("ok"):
                markdown = self.llm.complete_text(prompt=prompt, fallback="", stage="article")
                print(f"[CreationAgent] auto/local returned chars={len(markdown)}", flush=True)
                if not self._is_internal_analysis(markdown):
                    print("[CreationAgent] auto/local article accepted", flush=True)
                    return self._draft(selected["title"], markdown, strategy, themes)

        if self.allow_fallback:
            fallback = self._debug_article(topic, selected, strategy)
            return self._draft(selected["title"], fallback.markdown, strategy, themes)
        raise RuntimeError("创作模型未返回有效公众号正文。请优先使用 Codex，并适当提高 WORLD_OBSERVER_CODEX_TIMEOUT_SECONDS。")

    def create_batch(
        self,
        topics: list[str],
        world_hits: list[WorldSource],
        viral_models: list[ViralModel],
        patterns: list[str],
        platform: str | None = None,
        purpose: str | None = None,
        target_reader: str | None = None,
        forbidden_titles: list[str] | None = None,
        min_chars: int = 700,
        max_chars: int = 1000,
    ) -> list[ArticleDraft]:
        if not topics:
            return []
        engine = self._normalized_engine()
        if engine == "local":
            raise RuntimeError("批量快写不使用本地小模型，请使用 engine=codex 或 auto。")
        codex_health = self.codex.health() if self.codex else {"ok": False, "detail": "codex client not configured"}
        if not self.codex or not codex_health.get("ok"):
            raise RuntimeError(f"Codex 不可用，无法批量快写: {codex_health.get('detail') or codex_health}")

        strategies = {
            topic: self._build_strategy(topic, world_hits, viral_models, target_reader, platform, purpose)
            for topic in topics
        }
        theme_map = {
            topic: self._theme_candidates(topic, strategies[topic], viral_models, forbidden_titles or [])
            for topic in topics
        }
        prompt = self._batch_article_prompt(
            topics,
            world_hits,
            viral_models,
            patterns,
            strategies,
            theme_map,
            forbidden_titles or [],
            min_chars,
            max_chars,
        )
        print(f"[CreationAgent] batch prompt chars={len(prompt)} topics={len(topics)}", flush=True)
        markdown = self.codex.generate_text(prompt, fallback="", timeout_seconds=120)
        print(f"[CreationAgent] batch codex returned chars={len(markdown)}", flush=True)
        parsed = self._parse_batch_articles(markdown, len(topics))
        if len(parsed) != len(topics):
            raise RuntimeError(f"批量生成解析失败：需要 {len(topics)} 篇，实际解析到 {len(parsed)} 篇。")

        drafts: list[ArticleDraft] = []
        for index, body in enumerate(parsed):
            topic = topics[index]
            themes = theme_map[topic]
            selected = themes[0]
            if self._is_internal_analysis(body):
                raise RuntimeError(f"批量生成第 {index + 1} 篇不是有效正文。")
            drafts.append(self._draft(selected["title"], body, strategies[topic], themes))
        return drafts

    def _fallback_or_raise(
        self,
        message: str,
        topic: str,
        selected: dict[str, str],
        strategy: ArticleStrategy,
        themes: list[dict[str, str]],
    ) -> ArticleDraft:
        if self.allow_fallback:
            fallback = self._debug_article(topic, selected, strategy)
            return self._draft(selected["title"], fallback.markdown, strategy, themes)
        raise RuntimeError(message)

    def _normalized_engine(self) -> str:
        engine = (self.engine or "auto").strip().lower()
        if engine in {"默认", "default"}:
            return "auto"
        if engine in {"ollama", "local"}:
            return "local"
        if engine == "codex":
            return "codex"
        if engine == "auto":
            return "auto"
        return engine

    def _strict_article_prompt(self, prompt: str) -> str:
        return (
            prompt
            + "\n\n重新生成：上一次输出可能像策略文档。现在只输出最终公众号正文。\n"
            "禁止出现：文章策略规划、目标读者、平台选择、目的与内容定位、参考强度、结构示例、具体应用、Agent 分析、搜索结果、Obsidian 路径。\n"
            "第一行必须是一个面向公众号读者的 `# 标题`。随后直接进入正文。\n"
        )

    def _is_internal_analysis(self, markdown: str) -> bool:
        if not markdown or not markdown.strip():
            return True
        cleaned = self._clean_article(markdown)
        if len(cleaned) >= 600 and self._title_from_markdown(cleaned):
            return False
        forbidden_markers = [
            "文章策略规划",
            "目标读者",
            "平台选择",
            "目的与内容定位",
            "参考强度",
            "结构示例",
            "具体应用",
            "Agent 分析",
            "structure strategy",
            "world_hits",
            "brain_hits",
            "Obsidian",
            "搜索结果",
        ]
        return any(marker in markdown for marker in forbidden_markers)

    def _draft(self, title: str, markdown: str, strategy: ArticleStrategy, themes: list[dict[str, str]]) -> ArticleDraft:
        cleaned = self._clean_article(markdown)
        final_title = self._title_from_markdown(cleaned) or title
        return ArticleDraft(
            title=final_title,
            markdown=cleaned,
            cover_prompt=f"为「{final_title}」生成一张公众号封面：克制、清晰、有真实人物/场景感，避免营销感。",
            image_prompts=[
                f"文章配图：{final_title} 的核心问题",
                "结构图：人物/现象、冲突、问题意识、方法启发",
            ],
            structure_strategy=self._strategy_markdown(strategy) + "\n\n标题池：\n" + "\n".join(f"- {item['title']}" for item in themes),
        )

    def _article_prompt(
        self,
        topic: str,
        brain_hits: list[BrainHit],
        world_hits: list[WorldSource],
        viral_models: list[ViralModel],
        patterns: list[str],
        decision: Decision,
        strategy: ArticleStrategy,
        themes: list[dict[str, str]],
        forbidden_titles: list[str],
    ) -> str:
        forbidden_text = "\n".join(f"- {title}" for title in forbidden_titles[:30]) or "- 无"
        theme_text = "\n".join(
            f"{index}. 标题：{item['title']}；核心问题：{item['core_question']}；结构：{item['reference_structure']}"
            for index, item in enumerate(themes[:8], start=1)
        )
        brain_text = self._summarize_brain_hits(brain_hits)
        world_text = self._summarize_world_hits(world_hits)
        viral_text = self._summarize_viral_models(viral_models)
        pattern_text = "\n".join(f"- {item}" for item in patterns[:6]) or "- 暂无"
        explainer_instruction = self._explainer_instruction(topic)
        reference_link_text = self._reference_link_block(world_hits)
        reference_link_instruction = self._reference_link_instruction(reference_link_text)
        return (
            "你是 World Observer Agent 的 Creation Agent。请直接输出一篇中文 Markdown 文章，不要解释执行过程。\n"
            "请从给定标题池中选择最适合公众号读者的标题，作为文章一级标题。禁止把 raw topic 直接当标题。\n"
            "标题必须避开历史标题和本次批量已使用标题；不得生成完全相同或高度相似的标题。\n"
            "不要使用任何固定内容比例。文章结构必须由：用户主题、目标读者、同主题参考结构、平台表达偏好、文章目的决定。\n"
            "平台决定表达方式：公众号文章必须像公众号编辑一样思考；只有输出给 HackerNews/Reddit/X 时才使用那些平台的表达习惯。\n"
            "允许学习和迁移爆款表达模式：标题公式、开头结构、句式节奏、文章骨架、金句结构。\n"
            "禁止大段复制原文、复制别人独特经历、替换关键词式洗稿、或不理解逻辑直接套模板。\n"
            "article.md 禁止出现 reference_platform、拆解过程、分析过程，只保留最终文章。\n"
            "article.md 禁止出现 Obsidian 路径、world_hits、brain_hits、decision、JSON、搜索结果列表。\n"
            "每篇 article.md 都应该在文末保留 `## 参考来源`；正文中不要放 URL，不要暴露搜索过程。\n"
            "参考来源使用纯文本格式：`- 平台：文章标题` 或 `- 来源标题`。完整 URL 只进入 analysis.md，不进入 article.md。\n"
            "只有当外部参考不足时，才使用默认原则：读者优先、规律其次、个人观点少量。不要写成自传。\n"
            "单篇正式创作按高质量公众号长文写，目标约 2500-3500 中文字；开头要有真实读者问题，中段有完整解释，结尾有可带走的判断。\n"
            f"{explainer_instruction}"
            f"{reference_link_instruction}"
            "当前不生成图片，正文不要插入 `![](cover.png)` 或其他本地图片占位。\n\n"
            f"Forbidden titles:\n{forbidden_text}\n\n"
            f"Raw topic: {topic}\n\n"
            f"Theme candidates:\n{theme_text}\n\n"
            f"Article strategy:\n{self._strategy_markdown(strategy)}\n\n"
            f"World references:\n{world_text}\n\n"
            f"Reference links allowed at article end:\n{reference_link_text}\n\n"
            f"Viral structure notes:\n{viral_text}\n\n"
            f"Obsidian material summaries:\n{brain_text}\n\n"
            f"Human patterns:\n{pattern_text}\n\n"
            f"Decision: {decision.label} - {decision.reason}\n"
        )

    def _reference_link_instruction(self, reference_link_text: str) -> str:
        if reference_link_text == "- 无":
            return "不要编造参考来源；如果没有明确外部来源，文章末尾可以写 `- 主题相关检索：文章标题`，不要写 URL。\n"
        return (
            "文章最后加入 `## 参考来源`，列出 3-6 个外部参考来源。\n"
            "参考来源只能使用 `Reference links allowed at article end` 中和主题相关的来源标题，格式为纯文本 `- 平台：文章标题`。\n"
            "参考来源只放在全文最后；不要写 URL，不要暴露搜索过程，不要使用 Markdown 真链接。\n"
        )

    def _explainer_instruction(self, topic: str) -> str:
        if self._is_explainer_topic(topic, None):
            return (
                "这是一篇事实解释类文章。必须先完成事实说明，再做观点延展：\n"
                "1. 前 1/3 必须讲清楚“它是什么”：所属公司/产品线、模型定位、核心能力、与相关模型的关系。\n"
                "2. 必须交代事件时间线：发布/开放、被限制/下线、官方或媒体给出的原因。\n"
                "3. 必须区分已确认事实、媒体报道、推测和你的判断，不能把推测写成事实。\n"
                "4. 如果参考源不足，正文必须承认信息边界，不要用宏大叙事填补事实空白。\n"
                "5. 观点部分放在事实解释之后，不能一开头就泛泛写“工具箱”“时代提醒”。\n"
            )
        return ""

    def _is_explainer_topic(self, topic: str, purpose: str | None) -> bool:
        lowered = topic.lower()
        if purpose in {"新闻解释", "事实解释", "工具推荐", "教程"}:
            return True
        return any(term in topic for term in ["是什么", "解释", "被封", "封了", "禁令", "限制", "发生了什么"]) or any(
            term in lowered for term in ["model", "fable", "mythos", "ban", "export control", "what is"]
        )

    def _batch_article_prompt(
        self,
        topics: list[str],
        world_hits: list[WorldSource],
        viral_models: list[ViralModel],
        patterns: list[str],
        strategies: dict[str, ArticleStrategy],
        theme_map: dict[str, list[dict[str, str]]],
        forbidden_titles: list[str],
        min_chars: int,
        max_chars: int,
    ) -> str:
        forbidden_text = "\n".join(f"- {title}" for title in forbidden_titles[:30]) or "- 无"
        topic_blocks: list[str] = []
        for index, topic in enumerate(topics, start=1):
            themes = theme_map[topic]
            theme_text = "\n".join(
                f"  - {item['title']} | {item['reference_structure']}"
                for item in themes[:3]
            )
            strategy = strategies[topic]
            topic_blocks.append(
                f"ARTICLE {index}\n"
                f"Topic: {topic}\n"
                f"Purpose: {strategy.purpose}\n"
                f"Reader: {strategy.target_reader}\n"
                f"Structure: {' / '.join(strategy.structure[:5])}\n"
                f"Title pool:\n{theme_text}"
            )
        return (
            "你是 World Observer Agent 的批量 Creation Agent。请一次生成多篇中文公众号 Markdown 正文。\n"
            "目标是快速生产可继续人工精修的 article draft。不要写模板说明，不要写系统验证文。\n"
            "必须参考公众号写文规则：标题有点击理由，开头进入读者痛点，小标题承担阅读节奏，段落短，观点有转折和案例感。\n"
            "同一批文章必须覆盖不同产品、公司、用户场景或商业问题；不要把同一个主题改写成多个“角度”。\n"
            "每篇正文必须只包含读者可见内容：第一行 `# 标题`，不要插入 `![](cover.png)` 或其他本地图片占位。\n"
            "禁止输出分析过程、Obsidian 路径、JSON、world_hits、brain_hits、decision；参考来源只能放在文末 `## 参考来源`，且不写 URL。\n"
            "标题必须从各自标题池中选择或轻微改写，不得使用 forbidden titles，不得彼此重复。\n"
            f"每篇 {min_chars}-{max_chars} 中文字，短段落，3-5 个小标题，观点完整但不要过度展开。\n"
            "严格使用以下分隔符输出，不要添加总说明：\n"
            "<<<ARTICLE 1>>>\n# 标题\n...\n<<<END ARTICLE 1>>>\n"
            "<<<ARTICLE 2>>>\n# 标题\n...\n<<<END ARTICLE 2>>>\n\n"
            f"Forbidden titles:\n{forbidden_text}\n\n"
            f"Shared world references:\n{self._summarize_world_hits(world_hits[:4])}\n\n"
            f"Shared viral structure notes:\n{self._summarize_viral_models(viral_models)}\n\n"
            f"Shared human patterns:\n{chr(10).join(f'- {item}' for item in patterns[:5]) or '- 暂无'}\n\n"
            "Article tasks:\n\n"
            + "\n\n".join(topic_blocks)
        )

    def _parse_batch_articles(self, markdown: str, expected: int) -> list[str]:
        import re

        articles: list[str] = []
        for index in range(1, expected + 1):
            pattern = rf"<<<ARTICLE {index}>>>(.*?)<<<END ARTICLE {index}>>>"
            match = re.search(pattern, markdown, flags=re.S)
            if match:
                articles.append(match.group(1).strip())
        if articles:
            return articles
        chunks = re.split(r"^# ", markdown.strip(), flags=re.M)
        parsed = [("# " + chunk.strip()) for chunk in chunks if chunk.strip()]
        return parsed[:expected]

    def _summarize_brain_hits(self, brain_hits: list[BrainHit]) -> str:
        if not brain_hits:
            return "- 暂无"
        lines: list[str] = []
        for hit in brain_hits[:4]:
            excerpt = self._short(getattr(hit, "excerpt", ""), 220)
            lines.append(f"- {hit.title}: {excerpt}")
        return "\n".join(lines)

    def _summarize_world_hits(self, world_hits: list[WorldSource]) -> str:
        if not world_hits:
            return "- 暂无"
        lines: list[str] = []
        for hit in world_hits[:6]:
            excerpt = self._short(getattr(hit, "excerpt", ""), 220)
            lines.append(f"- [{hit.platform}] {hit.title}: {excerpt}")
        return "\n".join(lines)

    def _reference_link_block(self, world_hits: list[WorldSource]) -> str:
        lines: list[str] = []
        seen: set[str] = set()
        for hit in world_hits:
            url = (hit.url or "").strip()
            if not url.startswith(("http://", "https://")) or url in seen:
                continue
            seen.add(url)
            title = self._short(hit.title or url, 90)
            platform = hit.platform or "web"
            lines.append(f"- [{platform}] {title}: {url}")
            if len(lines) >= 8:
                break
        return "\n".join(lines) if lines else "- 无"

    def _summarize_viral_models(self, viral_models: list[ViralModel]) -> str:
        if not viral_models:
            return "- 暂无"
        lines: list[str] = []
        for model in viral_models[:5]:
            structure = " / ".join((model.body_structure or model.content_structure or [])[:4])
            lines.append(
                f"- {model.title}: 标题公式={model.title_formula or '无'}；点击={self._short(model.click_reason, 120)}；结构={structure}"
            )
        return "\n".join(lines)

    def _theme_candidates(
        self,
        topic: str,
        strategy: ArticleStrategy,
        viral_models: list[ViralModel],
        forbidden_titles: list[str] | None = None,
    ) -> list[dict[str, str]]:
        category = self._category(topic, strategy.purpose)
        if category == "person":
            titles = [
                f"{topic}真正厉害的地方，不只是她做出了什么",
                f"读懂{topic}：AI时代最稀缺的不是技术，而是问题意识",
                f"普通人为什么应该了解{topic}：不是学习成功，而是学习她怎么看世界",
                f"{topic}给普通人的启发：在巨大的浪潮里保持自己的问题",
                f"如果只把{topic}看成AI科学家，你就错过了更重要的东西",
            ]
            purpose = "人物观察 / AI人物 / 读书观察"
        elif strategy.purpose == "教程":
            titles = [
                f"{topic}第一次跑通，真正难的不是步骤",
                f"{topic}安装避坑：普通人最容易卡住的地方",
                f"别急着收藏工具，先把{topic}这条路走通",
                f"{topic}教程：从失败点开始，而不是从命令开始",
                f"普通人上手{topic}，先解决这三个问题",
            ]
            purpose = "教程"
        else:
            titles = [
                f"{topic}背后，真正值得观察的是什么",
                f"为什么{topic}会被这么多人关注",
                f"{topic}不是一个孤立现象",
                f"从{topic}看见一个新的时代问题",
                f"关于{topic}，我更关心它改变了谁",
            ]
            purpose = strategy.purpose
        formulas = [model.title_formula for model in viral_models if model.title_formula]
        candidates = [
            {
                "theme": title,
                "title": title,
                "target_reader": strategy.target_reader,
                "click_reason": "提供一个比人物介绍/教程步骤更深的观察角度。",
                "emotional_value": "让读者获得理解时代和自我行动的确定感。",
                "core_question": f"{topic}对普通读者真正有价值的问题是什么？",
                "reference_structure": formulas[index % len(formulas)] if formulas else "现象 -> 冲突 -> 解释 -> 方法 -> 结尾升华",
                "purpose": purpose,
            }
            for index, title in enumerate(titles[:10])
        ]
        forbidden_keys = {self._normalized_title(title) for title in forbidden_titles or []}
        filtered = [item for item in candidates if self._normalized_title(item["title"]) not in forbidden_keys]
        return filtered or candidates

    @staticmethod
    def _normalized_title(text: str) -> str:
        import re

        text = text.lower().strip()
        text = re.sub(r"^#+\s*", "", text)
        text = re.sub(r"\s+", "", text)
        return re.sub(r"[《》“”\"'`*_#\[\]（）()\s:：,，.。!！?？\-—_]+", "", text)

    def _category(self, topic: str, purpose: str) -> str:
        if purpose in {"人物观察", "AI人物", "读书观察"}:
            return "person"
        if topic in {"李飞飞", "Sam Altman", "黄仁勋", "马斯克"}:
            return "person"
        return "general"

    def _clean_article(self, markdown: str) -> str:
        markdown = markdown.strip()
        if markdown.startswith("```"):
            lines = markdown.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            markdown = "\n".join(lines).strip()
        banned = ["structure strategy", "reference_platform", "world_hits", "brain_hits", "decision", "Obsidian", "搜索结果"]
        lines = [
            line
            for line in markdown.splitlines()
            if not any(token in line for token in banned) and "cover.png" not in line and not line.strip().startswith("![](")
        ]
        return "\n".join(lines).strip() + "\n"

    def _title_from_markdown(self, markdown: str) -> str | None:
        for line in markdown.splitlines():
            if line.startswith("# "):
                return line[2:].strip()
        return None

    def _build_strategy(
        self,
        topic: str,
        world_hits: list[WorldSource],
        viral_models: list[ViralModel],
        target_reader: str | None,
        platform: str | None,
        purpose: str | None,
    ) -> ArticleStrategy:
        inferred_platform = platform or self._infer_platform(world_hits)
        inferred_purpose = purpose or self._infer_purpose(topic)
        inferred_reader = target_reader or self._infer_reader(topic, inferred_purpose)
        has_reference = len(world_hits) >= 3 and len(viral_models) >= 3

        if has_reference:
            structure = self._structure_from_references(inferred_purpose, viral_models)
            expression_style = self._style_for_platform(inferred_platform, viral_models)
            return ArticleStrategy(
                target_reader=inferred_reader,
                platform=inferred_platform,
                purpose=inferred_purpose,
                reference_strength="strong",
                structure=structure,
                expression_style=expression_style,
            )

        return ArticleStrategy(
            target_reader=inferred_reader,
            platform=inferred_platform,
            purpose=inferred_purpose,
            reference_strength="weak",
            structure=[
                "先进入读者问题，而不是先讲作者经历",
                "再抽象出可复用的规律或判断框架",
                "最后补充少量个人观点、边界和下一步行动",
            ],
            expression_style=[
                "短段落，先具体后抽象",
                "用问题意识组织章节",
                "个人经验服务于读者理解，不作为主线",
            ],
            default_principle_used=True,
        )

    def _infer_platform(self, world_hits: list[WorldSource]) -> str:
        platforms = [hit.platform for hit in world_hits if hit.platform]
        if not platforms:
            return "wechat/blog"
        return max(set(platforms), key=platforms.count)

    def _infer_purpose(self, topic: str) -> str:
        tutorial_terms = ["安装", "教程", "配置", "经验", "怎么", "指南"]
        retrospective_terms = ["复盘", "失败", "总结"]
        recommendation_terms = ["推荐", "工具", "清单"]
        emotional_terms = ["焦虑", "孤独", "迷茫", "治愈"]
        if any(term in topic for term in tutorial_terms):
            return "教程"
        if any(term in topic for term in retrospective_terms):
            return "复盘"
        if any(term in topic for term in recommendation_terms):
            return "工具推荐"
        if any(term in topic for term in emotional_terms):
            return "情绪共鸣"
        return "观察"

    def _infer_reader(self, topic: str, purpose: str) -> str:
        if purpose == "教程":
            return f"想完成「{topic}」但害怕踩坑的新手"
        if purpose == "工具推荐":
            return "想节省选择成本、快速判断是否值得使用的人"
        if purpose == "复盘":
            return "想从真实过程里提取经验和避坑方法的人"
        if purpose == "情绪共鸣":
            return "正在经历相似处境、需要被理解和重新获得解释的人"
        return "对世界现象背后规律感兴趣的读者"

    def _structure_from_references(self, purpose: str, viral_models: list[ViralModel]) -> list[str]:
        referenced_steps: list[str] = []
        for model in viral_models:
            referenced_steps.extend(model.content_structure)
        if purpose == "教程":
            return [
                "Hook: 直接说读者最可能卡住的地方",
                "适用对象和不适用对象",
                "最短成功路径",
                "高频失败点和判断方法",
                "完成后的下一步选择",
            ]
        if purpose == "观点":
            return [
                "Hook: 提出冲突或反常识判断",
                "用案例证明问题存在",
                "提出核心观点",
                "处理反方观点",
                "落到行动或判断标准",
            ]
        if purpose == "复盘":
            return [
                "先给结论和损失",
                "还原关键过程",
                "拆解决策错误",
                "提炼可复用原则",
                "列出下次检查清单",
            ]
        return referenced_steps[:6] or [
            "Hook: 说出现象",
            "拆显性需求和隐藏需求",
            "抽象成人类规律",
            "给读者一个新的观察角度",
        ]

    def _style_for_platform(self, platform: str, viral_models: list[ViralModel]) -> list[str]:
        notes: list[str] = []
        for model in viral_models:
            notes.extend(model.expression_notes)
        if platform in {"xiaohongshu", "小红书"}:
            notes.extend(["标题更具体，强调结果和避坑", "段落更短，适合截图式阅读"])
        elif platform in {"wechat", "公众号", "wechat/blog"}:
            notes.extend(["开头要快，正文允许有完整推理", "小标题承担阅读节奏"])
        elif platform in {"reddit", "zhihu", "知乎"}:
            notes.extend(["保留真实经验和边界条件", "观点需要可讨论，不要只下结论"])
        return self._dedupe(notes)[:8]

    def _strategy_markdown(self, strategy: ArticleStrategy) -> str:
        default_line = "是" if strategy.default_principle_used else "否"
        structure = " / ".join(strategy.structure)
        style = " / ".join(strategy.expression_style)
        return (
            f"目标读者：{strategy.target_reader}\n"
            f"平台：{strategy.platform}\n"
            f"文章目的：{strategy.purpose}\n"
            f"外部参考强度：{strategy.reference_strength}\n"
            f"使用默认原则：{default_line}\n"
            f"结构：{structure}\n"
            f"表达：{style}"
        )

    def _dedupe(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            normalized = value.strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                result.append(normalized)
        return result

    def _short(self, text: str, limit: int) -> str:
        text = " ".join(str(text or "").split())
        if len(text) <= limit:
            return text
        return text[:limit].rstrip() + "..."

    def _debug_article(
        self,
        topic: str,
        selected: dict[str, str],
        strategy: ArticleStrategy,
    ) -> ArticleDraft:
        title = selected["title"]
        markdown = f"""# {title}

这是一篇用于 smoke/debug 的占位正文。正式公众号创作必须使用 Codex、Ollama 或 API 生成。
"""
        return ArticleDraft(
            title=title,
            markdown=markdown,
            cover_prompt=f"公众号封面：{title}",
            image_prompts=[],
            structure_strategy=self._strategy_markdown(strategy),
        )
