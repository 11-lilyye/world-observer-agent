from __future__ import annotations

import csv
import json
import shutil
import re
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any


class Storage:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.project_root = Path(__file__).resolve().parents[2]
        self.library_root = root / "agent资料库"
        self.system_root = self.project_root / "系统"
        self.wechat_root = root / "微信开发平台" / "公众号" / "输出"
        self._ensure_base_dirs()

    def write_observation_batch(self, observations: list[Any], viral_models: list[Any], patterns: list[str], decision: Any) -> Path:
        day = date.today().isoformat()
        viral_dir = self.library_root / "爆款库"
        observation_dir = self.library_root / "观察库"
        learning_dir = self.library_root / "学习库"
        model_dir = self.system_root / "模型库"
        log_dir = self.system_root / "运行日志"
        viral_dir.mkdir(parents=True, exist_ok=True)
        observation_dir.mkdir(parents=True, exist_ok=True)
        learning_dir.mkdir(parents=True, exist_ok=True)
        model_dir.mkdir(parents=True, exist_ok=True)
        log_dir.mkdir(parents=True, exist_ok=True)

        self._write_json(viral_dir / f"{day}.json", {"viral_models": viral_models, "decision": decision})
        (observation_dir / f"{day}.md").write_text(self._case_markdown(observations), encoding="utf-8")
        self._append_patterns(model_dir / "human-pattern-library.md", patterns)
        self._write_log(log_dir / f"{day}.log", f"observe: {len(observations)} observations, {len(patterns)} patterns")
        return observation_dir / f"{day}.md"

    def write_article(
        self,
        topic: str,
        article: Any,
        brain_hits: list[Any],
        world_hits: list[Any],
        viral_models: list[Any],
        patterns: list[str],
        decision: Any,
        reference_plan: Any = None,
        visual_plan: Any = None,
        image_result: Any = None,
    ) -> Path:
        slug = self._slug(topic)
        root = self._unique_dir(self.wechat_root / "未发布" / f"{date.today().isoformat()}_{slug}")
        root.mkdir(parents=True, exist_ok=True)
        article_markdown = self._append_reference_section(article.markdown, world_hits, reference_plan)
        (root / "article.md").write_text(article_markdown, encoding="utf-8")
        has_generated_images = bool(getattr(image_result, "generated_files", []) or [])
        if has_generated_images:
            (root / "images").mkdir(parents=True, exist_ok=True)
        (root / "analysis.md").write_text(
            self._analysis_markdown(
                topic,
                article,
                brain_hits,
                world_hits,
                viral_models,
                patterns,
                decision,
                reference_plan,
                visual_plan if has_generated_images else None,
                image_result if has_generated_images else None,
            ),
            encoding="utf-8",
        )
        metadata = {
            "topic": topic,
            "title": article.title,
            "structure_strategy": article.structure_strategy,
            "reference_plan": self._compact_reference_plan(reference_plan),
            "brain_hits": self._compact_brain_hits(brain_hits[:3]),
            "world_hits": self._compact_world_sources(world_hits[:3]),
            "viral_models": self._compact_viral_models(viral_models[:3]),
            "patterns": patterns[:5],
            "decision": self._plain(decision),
        }
        if has_generated_images:
            metadata["visual_plan"] = self._compact_visual_plan(visual_plan)
            metadata["image_backend_result"] = self._plain(image_result)
            cover_prompt = getattr(visual_plan, "cover_prompt", "") or article.cover_prompt
            image_prompts = getattr(visual_plan, "image_prompts", None) or article.image_prompts
            (root / "cover_prompt.txt").write_text(cover_prompt, encoding="utf-8")
            self._write_json(
                root / "image_prompts.json",
                {
                    "cover_prompt": cover_prompt,
                    "image_prompts": image_prompts,
                    "negative_prompt": getattr(visual_plan, "negative_prompt", ""),
                    "backend": getattr(image_result, "backend", getattr(visual_plan, "backend", "")),
                    "requested_backend": getattr(image_result, "requested_backend", getattr(visual_plan, "backend", "")),
                    "note": getattr(image_result, "note", ""),
                },
            )
        self._write_json(root / "metadata.json", metadata)
        return root

    def _append_reference_section(self, markdown: str, world_hits: list[Any], reference_plan: Any = None) -> str:
        body = (markdown or "").strip()
        if "## 参考来源" in body:
            return body + "\n"
        article_title = self._first_heading(body)
        links = self._reference_links(world_hits, reference_plan, article_title)
        if links:
            lines = ["", "## 参考来源", ""]
            lines.extend(f"- {title}" for title, _url in links[:8])
            return body + "\n" + "\n".join(lines) + "\n"
        return body + "\n"

    def _reference_links(self, world_hits: list[Any], reference_plan: Any = None, title: str = "") -> list[tuple[str, str]]:
        candidates: list[Any] = list(world_hits or [])
        plan_sources = getattr(reference_plan, "sources", None)
        if isinstance(reference_plan, dict):
            plan_sources = reference_plan.get("sources")
        if plan_sources:
            candidates.extend(plan_sources)

        links: list[tuple[str, str]] = []
        seen: set[str] = set()
        for source in candidates:
            url = self._source_value(source, "url")
            source_title = self._source_value(source, "title") or url
            platform = self._source_value(source, "platform")
            if not url or not url.startswith(("http://", "https://")):
                continue
            if not self._is_relevant_reference(source_title, self._source_value(source, "excerpt"), title_context=title):
                continue
            if url in seen:
                continue
            seen.add(url)
            label = f"{platform}｜{source_title}" if platform else source_title
            links.append((label[:120], url))
        return links

    def _is_relevant_reference(self, source_title: str, source_excerpt: str = "", title_context: str = "") -> bool:
        source_terms = self._reference_terms(f"{source_title} {source_excerpt}")
        context_terms = self._reference_terms(title_context)
        if not source_terms or not context_terms:
            return False
        return bool(source_terms & context_terms)

    @staticmethod
    def _reference_terms(text: str) -> set[str]:
        stopwords = {
            "为什么", "真正", "问题", "背后", "值得", "观察", "不是", "一个", "一种",
            "如何", "什么", "文章", "公众号", "普通人", "可以", "看见", "改变", "需要",
        }
        raw = re.findall(r"[a-zA-Z][a-zA-Z0-9+-]*|[\u4e00-\u9fff]{2,}", text.lower())
        terms: set[str] = set()
        for token in raw:
            if token in stopwords:
                continue
            terms.add(token)
            if re.fullmatch(r"[\u4e00-\u9fff]{4,}", token):
                terms.update(token[index : index + 2] for index in range(len(token) - 1))
        return {term for term in terms if term not in stopwords}

    @staticmethod
    def _first_heading(markdown: str) -> str:
        for line in markdown.splitlines():
            if line.startswith("# "):
                return line[2:].strip()
        return "文章主题"

    @staticmethod
    def _url_query(text: str) -> str:
        from urllib.parse import quote

        return quote(text.strip())

    @staticmethod
    def _source_value(source: Any, key: str) -> str:
        if isinstance(source, dict):
            value = source.get(key)
        else:
            value = getattr(source, key, "")
        return str(value or "").strip()

    def write_feedback(self, article_id: str, report: str) -> Path:
        root = self.library_root / "反馈库"
        root.mkdir(parents=True, exist_ok=True)
        path = root / f"{datetime.now().strftime('%Y-%m-%d_%H%M%S')}_{self._slug(article_id)}.md"
        path.write_text(report, encoding="utf-8")
        data_path = root / "数据.csv"
        data_path.parent.mkdir(parents=True, exist_ok=True)
        if not data_path.exists():
            with data_path.open("w", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                writer.writerow(["article_id", "created_at", "reads", "likes", "saves", "shares", "follows", "comments"])
        return path

    def existing_article_signatures(self) -> list[dict[str, str]]:
        signatures: list[dict[str, str]] = []
        for root in [self.wechat_root / "未发布", self.wechat_root / "已发布"]:
            if not root.exists():
                continue
            for folder in root.iterdir():
                if not folder.is_dir():
                    continue
                topic = ""
                title = ""
                metadata_path = folder / "metadata.json"
                if metadata_path.exists():
                    try:
                        data = json.loads(metadata_path.read_text(encoding="utf-8", errors="ignore"))
                        topic = str(data.get("topic") or "")
                        title = str(data.get("title") or "")
                    except (OSError, json.JSONDecodeError):
                        pass
                article_path = folder / "article.md"
                if not title and article_path.exists():
                    try:
                        for line in article_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                            if line.startswith("# "):
                                title = line[2:].strip()
                                break
                    except OSError:
                        pass
                signatures.append(
                    {
                        "folder": folder.name,
                        "topic": topic,
                        "title": title,
                        "signature": self.topic_signature(" ".join([topic, title, folder.name])),
                    }
                )
        return signatures

    def existing_article_titles(self) -> list[str]:
        titles: list[str] = []
        seen: set[str] = set()
        for item in self.existing_article_signatures():
            title = item.get("title", "").strip()
            key = self.normalized_title(title)
            if not title or key in seen:
                continue
            titles.append(title)
            seen.add(key)
        return titles

    @staticmethod
    def normalized_title(text: str) -> str:
        text = text.lower().strip()
        text = re.sub(r"^#+\s*", "", text)
        text = re.sub(r"\s+", "", text)
        text = re.sub(r"[《》“”\"'`*_#\[\]（）()\s:：,，.。!！?？\-—_]+", "", text)
        return text

    @staticmethod
    def topic_signature(text: str) -> str:
        text = text.lower()
        text = re.sub(r"https?://\S+", " ", text)
        text = re.sub(r"\d{4}-\d{2}-\d{2}", " ", text)
        text = re.sub(r"[\d_#\-]+", " ", text)
        stopwords = {
            "如何",
            "评价",
            "为什么",
            "怎么",
            "什么",
            "一个",
            "一种",
            "真正",
            "背后",
            "值得",
            "观察",
            "公众号",
            "文章",
            "热点",
            "最新",
            "今天",
        }
        raw_tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9+-]*|[\u4e00-\u9fff]{2,}", text)
        tokens: list[str] = []
        for token in raw_tokens:
            if token in stopwords:
                continue
            tokens.append(token)
            if re.fullmatch(r"[\u4e00-\u9fff]{4,}", token):
                tokens.extend(token[index : index + 2] for index in range(len(token) - 1))
        kept = [token for token in tokens if token not in stopwords]
        return " ".join(sorted(set(kept)))

    def write_imported_wechat_article(self, article: Any) -> Path:
        root = self.root / "微信开发平台" / "公众号" / "公众号收藏信息源"
        root.mkdir(parents=True, exist_ok=True)
        slug = self._slug(article.title)
        markdown_path = self._unique_file(root / f"{slug}.md")
        images_dir = root / "images" / markdown_path.stem
        images_dir.mkdir(parents=True, exist_ok=True)

        markdown = article.markdown
        for image in getattr(article, "images", []) or []:
            source = Path(image)
            if not source.exists() or not source.is_file():
                continue
            target = images_dir / source.name
            shutil.copy2(source, target)
            markdown = markdown.replace(str(source), f"images/{markdown_path.stem}/{target.name}")

        markdown_path.write_text(markdown, encoding="utf-8")
        self._write_json(
            markdown_path.with_suffix(".json"),
            {
                "title": article.title,
                "url": article.url,
                "author": article.author,
                "publish_time": article.publish_time,
                "account_desc": article.account_desc,
                "importer": article.importer,
                "markdown_path": str(markdown_path),
                "images_dir": str(images_dir),
                "imported_at": datetime.now().isoformat(timespec="seconds"),
            },
        )

        viral_import_dir = self.library_root / "爆款库" / "公众号导入"
        viral_import_dir.mkdir(parents=True, exist_ok=True)
        self._write_json(
            viral_import_dir / f"{markdown_path.stem}.json",
            {
                "title": article.title,
                "url": article.url,
                "author": article.author,
                "publish_time": article.publish_time,
                "importer": article.importer,
                "source_markdown": str(markdown_path),
            },
        )
        return markdown_path

    def _ensure_base_dirs(self) -> None:
        dirs = [
            self.library_root / "爆款库",
            self.library_root / "观察库",
            self.library_root / "学习库",
            self.library_root / "反馈库",
            self.system_root / "Prompt",
            self.system_root / "模型库",
            self.system_root / "运行日志",
            self.wechat_root / "未发布",
            self.wechat_root / "已发布",
        ]
        for item in dirs:
            item.mkdir(parents=True, exist_ok=True)

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.write_text(json.dumps(self._plain(payload), ensure_ascii=False, indent=2), encoding="utf-8")

    def _plain(self, value: Any) -> Any:
        if is_dataclass(value):
            return asdict(value)
        if isinstance(value, list):
            return [self._plain(item) for item in value]
        if isinstance(value, dict):
            return {key: self._plain(item) for key, item in value.items()}
        return value

    def _compact_reference_plan(self, value: Any) -> dict[str, Any]:
        if not value:
            return {}
        plain = self._plain(value)
        sources = plain.get("sources", []) if isinstance(plain, dict) else []
        if isinstance(plain, dict):
            plain["sources"] = self._compact_world_sources(sources[:3])
        return plain if isinstance(plain, dict) else {}

    def _compact_world_sources(self, values: list[Any]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for item in values:
            plain = self._plain(item)
            if not isinstance(plain, dict):
                continue
            result.append(
                {
                    "title": plain.get("title", ""),
                    "url": plain.get("url", ""),
                    "platform": plain.get("platform", ""),
                    "excerpt": self._short_text(plain.get("excerpt", ""), 120),
                    "metrics": plain.get("metrics", {}),
                }
            )
        return result

    def _compact_brain_hits(self, values: list[Any]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for item in values:
            plain = self._plain(item)
            if not isinstance(plain, dict):
                continue
            result.append(
                {
                    "path": plain.get("path", ""),
                    "title": plain.get("title", ""),
                    "excerpt": self._short_text(plain.get("excerpt", ""), 160),
                    "score": plain.get("score", 0),
                }
            )
        return result

    def _compact_viral_models(self, values: list[Any]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for item in values:
            plain = self._plain(item)
            if not isinstance(plain, dict):
                continue
            result.append(
                {
                    "title": plain.get("title", ""),
                    "reference_platform": plain.get("reference_platform", ""),
                    "title_formula": plain.get("title_formula", ""),
                    "click_reason": self._short_text(plain.get("click_reason", ""), 100),
                    "content_structure": (plain.get("content_structure") or [])[:3],
                    "body_structure": (plain.get("body_structure") or [])[:3],
                    "expression_notes": (plain.get("expression_notes") or [])[:3],
                    "migration_notes": (plain.get("migration_notes") or [])[:1],
                }
            )
        return result

    def _compact_visual_plan(self, value: Any) -> dict[str, Any]:
        plain = self._plain(value)
        if not isinstance(plain, dict):
            return {}
        return {
            "system_name": plain.get("system_name", ""),
            "category": plain.get("category", ""),
            "route_name": plain.get("route_name", ""),
            "artist_mix": plain.get("artist_mix", []),
            "why": plain.get("why", ""),
            "metaphor": plain.get("metaphor", ""),
            "core_problem": plain.get("core_problem", ""),
            "cover_prompt_path": "cover_prompt.txt",
            "image_prompts_path": "image_prompts.json",
            "backend": plain.get("backend", ""),
            "fallback_backend": plain.get("fallback_backend", ""),
        }

    def _short_text(self, value: Any, limit: int) -> str:
        text = " ".join(str(value or "").split())
        if len(text) <= limit:
            return text
        return text[:limit].rstrip() + "..."

    def _case_markdown(self, observations: list[Any]) -> str:
        lines = ["# 人类行为案例", ""]
        for item in observations:
            lines.extend(
                [
                    f"## {item.phenomenon}",
                    "",
                    f"- 谁喜欢：{item.who_likes_it}",
                    f"- 为什么喜欢：{item.why_they_like_it}",
                    f"- 显性需求：{item.explicit_need}",
                    f"- 隐藏需求：{item.hidden_need}",
                    f"- 满足情绪：{item.emotion}",
                    f"- 时代背景：{item.era_context}",
                    f"- 反映的人类规律：{item.human_pattern}",
                    f"- 来源：{item.source.title} ({item.source.platform})",
                    "",
                ]
            )
        return "\n".join(lines)

    def _analysis_markdown(
        self,
        topic: str,
        article: Any,
        brain_hits: list[Any],
        world_hits: list[Any],
        viral_models: list[Any],
        patterns: list[str],
        decision: Any,
        reference_plan: Any = None,
        visual_plan: Any = None,
        image_result: Any = None,
    ) -> str:
        reference = self._plain(reference_plan) if reference_plan else {}
        lines = [
            "# 创作分析",
            "",
            "## 1. 主题识别",
            "",
            f"原始输入：{topic}",
            f"清洗主题：{topic}",
            f"平台：{reference.get('output_platform', '')}",
            f"文章目的：{self._value_from_strategy(article.structure_strategy, '文章目的')}",
            "",
            "## 2. 爆款研究",
            "",
        ]
        for index, model in enumerate(viral_models[:5], start=1):
            lines.extend(
                [
                    f"### 参考{index}",
                    "",
                    f"标题：{getattr(model, 'title', '')}",
                    f"来源：{getattr(model, 'reference_platform', '')}",
                    "URL/路径：见 metadata.json",
                    f"为什么参考：{getattr(model, 'click_reason', '')}",
                    f"标题公式：{getattr(model, 'title_formula', '')}",
                    f"结构拆解：{' / '.join(getattr(model, 'body_structure', []) or getattr(model, 'content_structure', []))}",
                    f"可迁移点：{' / '.join(item.get('how_to_migrate', '') for item in getattr(model, 'migration_notes', []) if isinstance(item, dict))}",
                    "",
                ]
            )
        lines.extend(["## 3. 标题池", ""])
        titles = [line[2:] for line in article.structure_strategy.splitlines() if line.startswith("- ")]
        for index, title in enumerate(titles[:20], start=1):
            lines.append(f"{index}. {title}｜点击欲：中高｜匹配度：中高｜传播性：中")
        lines.extend(
            [
                "",
                "## 4. 最终选择",
                "",
                f"最终标题：{article.title}",
                "选择原因：兼顾平台读者的点击动机、主题匹配度和可展开的核心问题。",
                "",
                "## 5. 文章结构",
                "",
                f"Hook：{self._value_from_strategy(article.structure_strategy, '结构')}",
                "章节：见 article.md",
                "案例：结合参考源与 Obsidian 素材，不复制独特经历。",
                "结尾：回到读者可带走的判断或行动。",
                "",
                "## 6. Obsidian 素材使用",
                "",
            ]
        )
        if brain_hits:
            for index, hit in enumerate(brain_hits[:5], start=1):
                lines.extend(
                    [
                        f"### 素材{index}",
                        "",
                        f"来源：{getattr(hit, 'path', '')}",
                        "原始摘录：",
                        f"> {getattr(hit, 'excerpt', '')}",
                        "提炼观点：可作为个人知识连接或补充判断。",
                        "如何进入文章：只作为观点支撑，不暴露内部路径。",
                        "",
                    ]
                )
        else:
            lines.extend(["暂无命中的 Obsidian 素材。", ""])
        if visual_plan and image_result:
            lines.extend(
                [
                    "## 7. 视觉方案",
                    "",
                    f"- 分类：{getattr(visual_plan, 'route_name', '')}",
                    f"- 艺术路线：{' / '.join(getattr(visual_plan, 'artist_mix', []) or [])}",
                    f"- 为什么选择：{getattr(visual_plan, 'why', '')}",
                    f"- 隐喻：{getattr(visual_plan, 'metaphor', '')}",
                    "- prompt：见 cover_prompt.txt",
                    f"- backend：{getattr(image_result, 'backend', getattr(visual_plan, 'backend', ''))}",
                    f"- 生成结果：{getattr(image_result, 'note', '')}",
                    "",
                ]
            )
        reference_links = self._reference_links(world_hits, reference_plan, article.title)
        lines.extend(["## 7. 参考文献链接", ""])
        if reference_links:
            lines.extend(f"- {title}：{url}" for title, url in reference_links[:12])
        else:
            lines.append(f"- 待补充具体外部来源：{article.title}")
        lines.append("")
        lines.extend(
            [
                "## 8. Quality Check",
                "",
                "- 是否像公众号？待人工复核",
                "- 是否满足目标读者？待人工复核",
                "- 是否混入内部分析？article.md 不应包含 reference_platform、路径、JSON、decision。",
                "",
            ]
        )
        return "\n".join(lines)

    def _value_from_strategy(self, strategy: str, key: str) -> str:
        prefix = f"{key}："
        for line in strategy.splitlines():
            if line.startswith(prefix):
                return line[len(prefix) :]
        return ""

    def _append_patterns(self, path: Path, patterns: list[str]) -> None:
        existing = path.read_text(encoding="utf-8") if path.exists() else "# Human Pattern Library\n\n"
        with path.open("w", encoding="utf-8") as file:
            file.write(existing.rstrip() + "\n\n")
            for pattern in patterns:
                file.write(f"- {date.today().isoformat()}：{pattern}\n")

    def _write_log(self, path: Path, line: str) -> None:
        with path.open("a", encoding="utf-8") as file:
            file.write(f"{datetime.now().isoformat(timespec='seconds')} {line}\n")

    def _slug(self, text: str) -> str:
        text = re.sub(r"\s+", "-", text.strip())
        text = re.sub(r"[^\w\-\u4e00-\u9fff]+", "", text)
        return text[:80] or "untitled"

    def _unique_dir(self, path: Path) -> Path:
        if not path.exists():
            return path
        index = 2
        while True:
            candidate = Path(f"{path}-{index}")
            if not candidate.exists():
                return candidate
            index += 1

    def _unique_file(self, path: Path) -> Path:
        if not path.exists():
            return path
        stem = path.stem
        suffix = path.suffix
        parent = path.parent
        index = 2
        while True:
            candidate = parent / f"{stem}-{index}{suffix}"
            if not candidate.exists():
                return candidate
            index += 1
