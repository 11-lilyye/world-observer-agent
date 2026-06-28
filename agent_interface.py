#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, replace
from pathlib import Path

from world_observer.app import WorldObserverApp, RunResult
from world_observer.integrations.config import Settings


@dataclass(frozen=True)
class AgentPlan:
    mode: str
    topic: str | None = None
    count: int = 1
    platform: str | None = None
    target_reader: str | None = None
    purpose: str | None = None
    engine: str | None = None
    article_length: str | None = None
    topic_category: str | None = None
    web_reference: bool = False
    output_form: str = "markdown draft"
    output_path: Path | None = None
    reference_source: str = "按平台智能选择"
    generate_analysis: bool = True
    generate_cover: bool = False
    temporary_preview: bool = False
    urls: list[str] | None = None
    needs_clarification: bool = False
    question: str | None = None
    choices: list[str] | None = None


PREFERENCES_PATH = Path(__file__).resolve().parent / "user_preferences.yaml"


def parse_agent_request(text: str, settings: Settings) -> AgentPlan:
    normalized = text.strip()
    preferences = load_preferences()
    count = _extract_count(normalized)
    platform = _extract_platform(normalized) or preferences.get("default_platform")
    purpose = _extract_purpose(normalized)
    engine = _extract_engine(normalized)
    article_length = _extract_article_length(normalized)
    topic_category = _extract_topic_category(normalized)
    web_reference = _wants_web_reference(normalized)
    topic = _extract_topic(normalized)
    if topic_category and topic and _clean_topic(topic).lower() in {
        topic_category.lower(),
        "ai",
        "科技",
        "ai科技",
        "商业",
        "产品",
        "商业产品",
        "商业产品主题",
        "商业产品主题的",
        "人类观察",
        "情绪共鸣",
        "教程工具",
        "不限制",
        "不限",
        "自动探索",
    }:
        topic = None
    if topic_category and topic and _is_category_only_topic(topic):
        topic = None
    urls = _extract_urls(normalized)

    if _is_topic_suggestion(normalized):
        return AgentPlan(
            mode="topics",
            topic=None,
            count=count if count > 1 else 10,
            platform=platform or "公众号",
            purpose=purpose or "观察",
            engine=engine,
            article_length=article_length,
            topic_category=topic_category,
            web_reference=web_reference,
            output_form="topic candidates",
            output_path=None,
            reference_source="只抓取热点选题：TrendRadar/newsnow、RSS/Atom；不写文章",
        )

    if _is_wechat_import(normalized):
        if not urls:
            return AgentPlan(
                mode="import-wechat",
                output_path=settings.output_dir / "微信开发平台" / "公众号" / "公众号收藏信息源",
                reference_source="gxcsoccer/wechat-article-crawler 优先；不可用时 Browser-use/直接抓取 fallback",
                needs_clarification=True,
                question="请提供要导入的微信公众号文章 URL。",
                choices=["1. 粘贴 mp.weixin.qq.com/s/... 链接", "2. 使用 url-file 批量导入"],
            )
        return AgentPlan(
            mode="import-wechat",
            topic="公众号文章导入",
            count=len(urls),
            platform="公众号",
            output_form="imported source article",
            output_path=settings.output_dir / "微信开发平台" / "公众号" / "公众号收藏信息源",
            reference_source="gxcsoccer/wechat-article-crawler 优先；不可用时 Browser-use/直接抓取 fallback",
            urls=urls,
        )

    if _is_feedback(normalized):
        return AgentPlan(
            mode="feedback",
            topic=topic,
            count=1,
            platform=platform,
            purpose=purpose,
            engine=engine,
            output_form="feedback report",
            output_path=settings.output_dir / "agent资料库" / "反馈库",
            reference_source="反馈库与公众号后台数据",
        )

    if _is_create(normalized) or (web_reference and topic):
        if not topic and count == 1 and normalized in {"创建文章", "写文章", "创建内容", "生成文章"}:
            return AgentPlan(
                mode="create",
                count=1,
                platform=platform or "公众号",
                purpose=purpose,
                engine=engine,
                article_length=article_length,
                web_reference=web_reference,
                output_form="article draft",
                output_path=settings.output_dir / "微信开发平台" / "公众号" / "输出" / "未发布",
                reference_source=_reference_source(platform or "公众号", auto_topic=True, web_reference=web_reference),
            )
        if count > 1 and not topic and not topic_category:
            return AgentPlan(
                mode="create",
                topic=None,
                count=count,
                platform=platform or "公众号",
                purpose=purpose,
                engine=engine,
                article_length=article_length,
                web_reference=web_reference,
                output_form="article draft",
                output_path=settings.output_dir / "微信开发平台" / "公众号" / "输出" / "未发布",
                reference_source=_reference_source(platform or "公众号", auto_topic=True, web_reference=web_reference),
                needs_clarification=True,
                question="这次是自动批量选题。你想偏向哪类主题？",
                choices=[
                    "1. AI科技：AI Agent、工具、效率、独立开发。",
                    "2. 人类观察：社会情绪、心理、趋势、普通人处境。",
                    "3. 商业产品：公司、产品、品牌、消费、增长。",
                    "4. 不限制：让 Agent 从全平台热点里自动探索。",
                ],
            )
        if count > 1 and not article_length:
            return AgentPlan(
                mode="create",
                topic=topic if topic_category else (topic or _domain_hint(normalized)),
                count=count,
                platform=platform or "公众号",
                purpose=purpose,
                engine=engine,
                topic_category=topic_category,
                web_reference=web_reference,
                output_path=settings.output_dir / "微信开发平台" / "公众号" / "输出" / "未发布",
                reference_source=_reference_source(platform or "公众号", auto_topic=not bool(topic or (None if topic_category else _domain_hint(normalized))), web_reference=web_reference),
                needs_clarification=True,
                question="这次是批量生成。你想要哪种文章长度？",
                choices=[
                    "1. 1000-2000字快写草稿：速度快，适合先生产100篇再筛选。",
                    "2. 3000字高质量长文：更像正式公众号，但会明显更慢。",
                ],
            )
        if not topic and count > 1 and not platform and not _has_domain_hint(normalized):
            return AgentPlan(
                mode="create",
                count=count,
                platform=platform or "公众号",
                purpose=purpose,
                engine=engine,
                article_length=article_length,
                topic_category=topic_category,
                web_reference=web_reference,
                output_path=settings.output_dir / "微信开发平台" / "公众号" / "输出" / "未发布",
                reference_source=_reference_source(platform or "公众号", auto_topic=True, web_reference=web_reference),
            )
        return AgentPlan(
            mode="create",
            topic=topic if topic_category else (topic or _domain_hint(normalized)),
            count=count,
            platform=platform,
            purpose=purpose,
            engine=engine,
            article_length=article_length,
            topic_category=topic_category,
            web_reference=web_reference,
            output_form="article draft",
            output_path=settings.output_dir / "微信开发平台" / "公众号" / "输出" / "未发布",
            reference_source=_reference_source(platform or "公众号", auto_topic=not bool(topic or (None if topic_category else _domain_hint(normalized))), web_reference=web_reference),
        )

    if _is_observe(normalized):
        return AgentPlan(
            mode="observe",
            topic=topic,
            count=count,
            platform=platform,
            purpose=purpose or "观察",
            engine=engine,
            output_form="observation batch",
            output_path=settings.output_dir / "agent资料库" / "观察库",
            reference_source="RSS/热点源；失败时离线 seed",
        )

    return AgentPlan(
        mode="unknown",
        output_path=settings.output_dir,
        needs_clarification=True,
        question="我还不能确定你想让我做什么。你想观察、创作，还是复盘？",
        choices=["1. 自动观察世界", "2. 创建内容", "3. 数据反馈"],
    )


def render_plan(plan: AgentPlan) -> str:
    if plan.needs_clarification:
        choices = "\n".join(plan.choices or [])
        return f"{plan.question}\n\n{choices}".strip()

    lines = [
            "即将执行：",
            "",
            f"- 模式：{plan.mode}",
            f"- 主题：{plan.topic or '自动判断'}",
            f"- 平台：{plan.platform or '根据任务推断'}",
            f"- 文章目的：{plan.purpose or '根据任务推断'}",
            f"- 生成数量：{plan.count}",
            f"- 目标用户：{plan.target_reader or '根据主题和平台推断'}",
            f"- 固定流程：1. 搜网上资料/热点/相关文献  2. 查阅本地公众号收藏资料判断相关性；有相关性可作为内容分析一部分；公众号输出格式统一从本地公众号文章提取  3. 提取你的知识库观点",
            f"- 参考源：{plan.reference_source}",
            f"- 创作引擎：{plan.engine or '默认'}",
            f"- 文章长度：{_article_length_label(plan.article_length, plan.count)}",
            f"- 主题类型：{plan.topic_category or '未指定/不限制'}",
            f"- 事实资料策略：中外网站/热点/相关资料优先；公众号仅作格式参考；知识库用于注入你的观点",
            f"- 输出形式：{plan.output_form}",
            f"- 输出路径：{plan.output_path}",
            f"- 导入链接数：{len(plan.urls) if plan.urls else 0}" if plan.mode == "import-wechat" else "",
            f"- 是否生成 analysis.md：{'是' if plan.generate_analysis else '否'}",
            f"- 是否生成封面：{'是' if plan.generate_cover else '否'}",
            f"- 是否临时预览：{'是' if plan.temporary_preview else '否'}",
            "",
            "是否允许？",
            "",
            "1. Yes",
            "2. Yes, and don't ask again for similar commands",
            "3. No, and tell Agent what to do differently",
    ]
    return "\n".join(line for line in lines if line != "")


def execute_plan(plan: AgentPlan) -> RunResult:
    app = WorldObserverApp.from_env()
    if plan.mode == "observe":
        return app.observe(limit=max(plan.count, 8))
    if plan.mode == "topics":
        return app.suggest_topics(count=plan.count, topic_category=plan.topic_category or plan.topic)
    if plan.mode == "feedback":
        article_id = plan.topic or "latest"
        return app.feedback(article_id=article_id)
    if plan.mode == "create":
        if plan.count > 1 or not plan.topic:
            return app.create_many(
                count=plan.count,
                topic=plan.topic,
                target_reader=plan.target_reader,
                platform=plan.platform,
                purpose=plan.purpose,
            engine=plan.engine,
            article_length=plan.article_length,
            topic_category=plan.topic_category,
        )
        if not plan.topic:
            raise ValueError("create mode needs a topic or a batch count")
        return app.create(
            topic=plan.topic,
            target_reader=plan.target_reader,
            platform=plan.platform,
            purpose=plan.purpose,
            engine=plan.engine,
            prefer_web_hotspots=plan.web_reference,
        )
    if plan.mode == "import-wechat":
        return app.import_wechat_articles(plan.urls or [])
    raise ValueError(f"Unsupported mode: {plan.mode}")


def main() -> None:
    parser = argparse.ArgumentParser(description="World Observer Agent natural language interface")
    parser.add_argument("request", nargs="*", help="Natural language request.")
    parser.add_argument("--yes", action="store_true", help="Execute after showing the plan.")
    args = parser.parse_args()

    request = " ".join(args.request).strip()
    if not request:
        request = input("你想让 World Observer Agent 做什么？\n> ").strip()

    settings = Settings.from_env()
    plan = parse_agent_request(request, settings)

    if plan.needs_clarification:
        plan = clarification_loop(plan, settings)
        if not plan:
            return

    confirmed_plan = confirm_plan_loop(plan, settings, auto_yes=args.yes)
    if not confirmed_plan:
        return

    result = execute_plan(confirmed_plan)
    print(result.summary)
    if result.path:
        print(f"Output: {result.path}")
    if result.paths:
        for path in result.paths:
            print(f"Draft: {path}")


def clarification_loop(plan: AgentPlan, settings: Settings) -> AgentPlan | None:
    while plan.needs_clarification:
        print(render_plan(plan))
        try:
            answer = input("> ").strip()
        except EOFError:
            print("未收到选择，已停止。")
            return None
        if answer.lower() in {"退出", "cancel", "stop", "停止"}:
            print("已停止。")
            return None
        plan = apply_clarification_answer(plan, answer, settings)
    return plan


def apply_clarification_answer(plan: AgentPlan, answer: str, settings: Settings) -> AgentPlan:
    question = plan.question or ""
    if "自动批量选题" in question:
        topic_category = _topic_category_from_choice(answer) or _extract_topic_category(answer)
        if not topic_category:
            print("请选择 1、2、3、4，或输入主题类型，例如：商业产品。")
            return plan
        updated = replace(
            plan,
            topic=None,
            topic_category=topic_category,
            needs_clarification=False,
            question=None,
            choices=None,
            reference_source=_reference_source(plan.platform or "公众号", auto_topic=True, web_reference=plan.web_reference),
        )
        if updated.count > 1 and not updated.article_length:
            return replace(
                updated,
                needs_clarification=True,
                question="这次是批量生成。你想要哪种文章长度？",
                choices=[
                    "1. 1000-2000字快写草稿：速度快，适合先生产100篇再筛选。",
                    "2. 3000字高质量长文：更像正式公众号，但会明显更慢。",
                ],
            )
        return updated

    if "文章长度" in question:
        article_length = _article_length_from_choice(answer) or _extract_article_length(answer)
        if not article_length:
            print("请选择 1 或 2，或输入“快写”/“长文”。")
            return plan
        return replace(
            plan,
            article_length=article_length,
            needs_clarification=False,
            question=None,
            choices=None,
            reference_source=_reference_source(
                plan.platform or "公众号",
                auto_topic=not bool(plan.topic),
                web_reference=plan.web_reference,
            ),
        )

    updated = update_plan_from_feedback(plan, answer, settings)
    return replace(updated, needs_clarification=False, question=None, choices=None)


def confirm_plan_loop(plan: AgentPlan, settings: Settings, auto_yes: bool = False) -> AgentPlan | None:
    preferences = load_preferences()
    if auto_yes or should_skip_confirmation(plan, preferences):
        print(render_plan(plan))
        if should_skip_confirmation(plan, preferences):
            print("已根据 user_preferences.yaml 跳过同类确认。")
        return plan

    while True:
        print(render_plan(plan))
        try:
            answer = input("> ").strip()
        except EOFError:
            print("未收到确认，已停在计划阶段。")
            return None

        normalized = answer.lower()
        if normalized in {"1", "y", "yes", "是", "执行"}:
            return plan
        if normalized in {"2", "yes, and don't ask again for similar commands", "yes dont ask again", "不再询问"}:
            save_confirmation_preference(plan)
            return plan
        if normalized in {"退出", "cancel", "stop", "停止"}:
            print("已停止。")
            return None
        if normalized not in {"3", "n", "no", "否", "修改"}:
            print("请选择 1、2、3，或输入 退出 / cancel / stop。")
            continue

        print("请告诉我你想怎么改？")
        print("例如：只参考公众号，不要 HackerNews / 改成小红书 / 生成 1 篇 / 目标读者改成非程序员小白")
        try:
            change_request = input("> ").strip()
        except EOFError:
            print("未收到修改要求，已停在计划阶段。")
            return None
        if change_request.lower() in {"退出", "cancel", "stop", "停止"}:
            print("已停止。")
            return None
        plan = update_plan_from_feedback(plan, change_request, settings)


def should_skip_confirmation(plan: AgentPlan, preferences: dict[str, object]) -> bool:
    skip = preferences.get("skip_confirmations")
    if not isinstance(skip, dict):
        return False
    if plan.mode == "create":
        return bool(skip.get("create_plan") and skip.get("platform") and skip.get("output_path"))
    return bool(skip.get(f"{plan.mode}_plan"))


def save_confirmation_preference(plan: AgentPlan) -> None:
    preferences = load_preferences()
    skip = preferences.get("skip_confirmations")
    if not isinstance(skip, dict):
        skip = {}
    skip[f"{plan.mode}_plan"] = True
    if plan.mode == "create":
        skip["create_plan"] = True
        skip["platform"] = True
        skip["output_path"] = True
    preferences["skip_confirmations"] = skip
    if plan.platform:
        preferences["default_platform"] = plan.platform
    if plan.output_path:
        preferences["default_output_path"] = str(plan.output_path)
    write_preferences(preferences)
    print(f"已保存偏好：{PREFERENCES_PATH}")


def load_preferences() -> dict[str, object]:
    if not PREFERENCES_PATH.exists():
        return {}
    preferences: dict[str, object] = {}
    current_section: str | None = None
    for raw_line in PREFERENCES_PATH.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.rstrip()
        if not line.strip() or line.strip().startswith("#"):
            continue
        if not line.startswith(" ") and line.endswith(":"):
            current_section = line[:-1]
            preferences[current_section] = {}
            continue
        if ":" not in line:
            continue
        key, value = line.strip().split(":", 1)
        parsed = parse_preference_value(value.strip())
        if current_section and raw_line.startswith(" "):
            section = preferences.setdefault(current_section, {})
            if isinstance(section, dict):
                section[key] = parsed
        else:
            current_section = None
            preferences[key] = parsed
    return preferences


def write_preferences(preferences: dict[str, object]) -> None:
    lines: list[str] = []
    skip = preferences.get("skip_confirmations")
    if isinstance(skip, dict):
        lines.append("skip_confirmations:")
        for key, value in skip.items():
            lines.append(f"  {key}: {str(bool(value)).lower()}")
    for key in ("default_platform", "default_output_path"):
        value = preferences.get(key)
        if value:
            lines.append(f"{key}: {value}")
    PREFERENCES_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_preference_value(value: str) -> object:
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    return value.strip('"')


def update_plan_from_feedback(plan: AgentPlan, text: str, settings: Settings) -> AgentPlan:
    platform = _extract_platform(text) or plan.platform
    purpose = _extract_purpose(text) or plan.purpose
    engine = _extract_engine(text) or plan.engine
    article_length = _extract_article_length(text) or plan.article_length
    topic_category = _extract_topic_category(text) or plan.topic_category
    web_reference = plan.web_reference or _wants_web_reference(text)
    count = _extract_count(text) if re.search(r"\d+", text) else plan.count
    target_reader = _extract_target_reader(text) or plan.target_reader
    topic = _extract_topic_change(text) or plan.topic
    temporary_preview = plan.temporary_preview or any(term in text for term in ["临时预览", "不要写入", "先不要写入"])
    generate_cover = plan.generate_cover and not any(term in text for term in ["不要生成封面", "不要封面", "不生成封面"])
    reference_source = _reference_source(platform or "公众号", auto_topic=not bool(topic), web_reference=web_reference)
    if "只参考公众号" in text or "不要 HackerNews" in text or "不要HN" in text or "不要 Reddit" in text:
        reference_source = "只参考公众号：本地公众号爆款库、微信公众号同主题文章、用户手动提供文章"

    output_path = plan.output_path
    output_match = re.search(r"输出路径(?:改到|到|：|:)\s*(.+)$", text)
    if output_match:
        output_path = Path(output_match.group(1).strip()).expanduser()
    elif platform and platform != plan.platform:
        output_path = output_path_for_platform(settings, platform, plan.mode)

    return AgentPlan(
        mode=plan.mode,
        topic=topic,
        count=count,
        platform=platform,
        target_reader=target_reader,
        purpose=purpose,
        engine=engine,
        article_length=article_length,
        topic_category=topic_category,
        web_reference=web_reference,
        output_form="temporary preview" if temporary_preview else plan.output_form,
        output_path=output_path,
        reference_source=reference_source,
        generate_analysis=plan.generate_analysis,
        generate_cover=generate_cover,
        temporary_preview=temporary_preview,
        urls=plan.urls,
    )


def output_path_for_platform(settings: Settings, platform: str, mode: str) -> Path:
    if mode == "create" and platform in {"公众号", "公总号", "wechat", "微信"}:
        return settings.output_dir / "微信开发平台" / "公众号" / "输出" / "未发布"
    if mode == "create" and platform == "小红书":
        return settings.output_dir / "小红书" / "输出" / "未发布"
    if mode == "create" and platform == "博客":
        return settings.output_dir / "博客" / "输出" / "未发布"
    return settings.output_dir


def _reference_source(platform: str | None, auto_topic: bool = False, web_reference: bool = False) -> str:
    if platform in {"公众号", "公总号", "wechat", "微信", None}:
        if web_reference:
            return "固定顺序：先搜网上资料/热点/相关文献；再查阅本地公众号收藏资料判断相关性，有相关性可作为内容分析一部分，公众号输出格式统一从本地公众号文章提取；最后提取你的知识库观点"
        if auto_topic:
            return "固定顺序：先搜网上资料/热点/相关文献；再查阅本地公众号收藏资料判断相关性，有相关性可作为内容分析一部分，公众号输出格式统一从本地公众号文章提取；最后提取你的知识库观点"
        return "固定顺序：先搜网上资料/热点/相关文献；再查阅本地公众号收藏资料判断相关性，有相关性可作为内容分析一部分，公众号输出格式统一从本地公众号文章提取；最后提取你的知识库观点"
    if platform == "小红书":
        return "小红书优先：同主题笔记、封面标题、收藏/评论结构"
    if platform == "博客":
        return "博客优先：同主题长文、教程、实践复盘"
    if platform in {"HackerNews", "hackernews", "HN"}:
        return "HackerNews 优先：技术讨论、项目发布、评论动机"
    if platform in {"Reddit", "reddit"}:
        return "Reddit 优先：社区讨论、真实经验、评论争议点"
    if platform == "X":
        return "X 优先：短观点、线程结构、转发理由"
    return f"{platform} 平台优先：按该平台读者习惯选择参考源"


def _extract_target_reader(text: str) -> str | None:
    match = re.search(r"目标读者(?:改成|改为|是|：|:)\s*([^，,。]+)", text)
    if match:
        return match.group(1).strip()
    if "非程序员小白" in text:
        return "非程序员小白"
    return None


def _extract_topic_change(text: str) -> str | None:
    patterns = [
        r"主题(?:改成|改为|是|：|:)\s*([^，,。]+)",
        r"改成关于\s*([^，,。]+)",
        r"改为关于\s*([^，,。]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return _clean_topic(match.group(1))
    return None


def _extract_count(text: str) -> int:
    match = re.search(r"(\d+)\s*篇", text)
    if match:
        return int(match.group(1))
    match = re.search(r"([一二两三四五六七八九十]+)\s*篇", text)
    if match:
        return _chinese_number(match.group(1))
    return 1


def _extract_platform(text: str) -> str | None:
    if "公总号" in text:
        return "公众号"
    for platform in ["公众号", "小红书", "知乎", "博客", "视频", "Reddit", "X"]:
        if platform in text:
            return platform
    return None


def _extract_purpose(text: str) -> str | None:
    for purpose in ["教程", "观察", "观点", "复盘", "工具推荐", "情绪共鸣"]:
        if purpose in text:
            return purpose
    if "安装" in text or "指南" in text:
        return "教程"
    if "推荐" in text:
        return "工具推荐"
    return None


def _extract_engine(text: str) -> str | None:
    lowered = text.lower()
    if "codex" in lowered:
        return "codex"
    if "本地" in text or "ollama" in lowered:
        return "local"
    return None


def _wants_web_reference(text: str) -> bool:
    lowered = text.lower()
    return any(term in text for term in ["中英文", "中英文网站", "英文网站", "中文网站", "爬取", "爬取网站", "网上资料", "全网", "外网"]) or any(
        term in lowered for term in ["english", "web", "website"]
    )


def _extract_topic_category(text: str) -> str | None:
    normalized = text.replace("/", "").replace(" ", "")
    if any(term in normalized for term in ["AI科技", "ai科技", "科技AI", "科技", "AI", "ai"]):
        return "AI科技"
    if any(term in normalized for term in ["人类观察", "社会观察", "心理", "情绪", "普通人"]):
        return "人类观察"
    if any(term in normalized for term in ["商业产品", "商业", "产品", "品牌", "消费"]):
        return "商业产品"
    if any(term in normalized for term in ["情绪共鸣", "情绪"]):
        return "情绪共鸣"
    if any(term in normalized for term in ["教程工具", "教程", "工具"]):
        return "教程工具"
    if any(term in normalized for term in ["不限制", "不限", "自动探索", "随便", "全平台"]):
        return "不限制"
    return None


def _topic_category_from_choice(text: str) -> str | None:
    stripped = text.strip()
    mapping = {
        "1": "AI科技",
        "选1": "AI科技",
        "选择1": "AI科技",
        "2": "人类观察",
        "选2": "人类观察",
        "选择2": "人类观察",
        "3": "商业产品",
        "选3": "商业产品",
        "选择3": "商业产品",
        "4": "不限制",
        "选4": "不限制",
        "选择4": "不限制",
    }
    return mapping.get(stripped)


def _extract_article_length(text: str) -> str | None:
    normalized = text.lower()
    stripped = text.strip()
    if stripped in {"1", "选1", "选择1"}:
        return "fast"
    if stripped in {"2", "选2", "选择2"}:
        return "long"
    if any(term in text for term in ["长文", "3000", "三千", "深度", "高质量"]):
        return "long"
    if any(term in text for term in ["快写", "草稿", "1000", "2000", "一千", "两千", "批量快"]):
        return "fast"
    if "fast" in normalized:
        return "fast"
    if "long" in normalized:
        return "long"
    return None


def _article_length_from_choice(text: str) -> str | None:
    stripped = text.strip()
    if stripped in {"1", "选1", "选择1"}:
        return "fast"
    if stripped in {"2", "选2", "选择2"}:
        return "long"
    return None


def _article_length_label(article_length: str | None, count: int) -> str:
    if article_length == "long":
        return "3000字高质量长文（逐篇生成）"
    if article_length == "fast":
        return "1000-2000字快写草稿（批量生成）"
    if count > 1:
        return "待选择：1000-2000快写 / 3000长文"
    return "高质量长文（单篇默认）"


def _extract_urls(text: str) -> list[str]:
    return re.findall(r"https?://mp\.weixin\.qq\.com/[^\s，,。]+", text)


def _is_wechat_import(text: str) -> bool:
    return any(word in text for word in ["导入公众号", "导入微信", "抓取公众号", "抓取微信", "导入文章"]) or (
        "mp.weixin.qq.com" in text and any(word in text for word in ["导入", "抓取", "保存", "收藏"])
    )


def _extract_topic(text: str) -> str | None:
    patterns = [
        r"(?:创建|生成|写|帮我写|帮我生成).*?(?:公众号文章|公众号|文章|观察文)[：:]\s*([^，,。]+)",
        r"帮我写一篇关于\s*([^，,。]+?)\s*的公众号",
        r"生成\s*([^，,。]+?)\s*观察文",
        r"根据\s*(.+?)\s*生成",
        r"关于\s*(.+?)\s*(?:生成|创建|写|做|的)",
        r"观察(?:最近|今天)?\s*(.+?)\s*(?:热点|趋势|内容)?$",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            topic = _clean_topic(match.group(1))
            return None if _is_invalid_topic(topic) else topic

    if re.search(r"(安装指南|安装经验|教程|指南)$", text) and not _has_action_word(text):
        topic = _clean_topic(text)
        return None if _is_invalid_topic(topic) else topic

    if _is_bare_create_request(text):
        return None

    cleaned = _remove_count_phrases(text)
    cleaned = re.sub(
        r"公众号文章|公总号文章|公众号|公总号|帮我|创建|生成|写|做|一个|一篇|文章|内容|教程|观察文|观察|热点|最近|今天|复盘|数据|反馈|爬取中英文网站|中英文网站|英文网站|中文网站|爬取|网上资料|全网|外网|快写|草稿|长文|高质量|深度|主题的|主题|AI科技|ai科技|人类观察|商业产品|情绪共鸣|教程工具|\d+\s*字|[一二两三四五六七八九十千]+\s*字",
        " ",
        cleaned,
    )
    cleaned = _remove_count_phrases(cleaned)
    cleaned = _clean_topic(cleaned)
    if _is_invalid_topic(cleaned):
        return None
    return cleaned or None


def _clean_topic(text: str) -> str:
    text = str(text or "")
    text = re.sub(r"[“”\"'`]", " ", text)
    text = re.sub(r"需要\s*(?:爬取)?\s*(?:中英文网站|英文网站|中文网站|网上资料|全网|外网|web|website|english).*?$", " ", text, flags=re.I)
    text = re.sub(r"(?:爬取)?\s*(?:中英文网站|英文网站|中文网站|网上资料|全网|外网|web|website|english).*?$", " ", text, flags=re.I)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", text)
    text = text.strip(" ：:，,。")
    text = re.sub(r"^关于", "", text)
    text = re.sub(r"(?:需要|请)$", "", text)
    return text.strip(" ：:，,。")


def _remove_count_phrases(text: str) -> str:
    text = re.sub(r"\d+\s*篇", " ", text)
    return re.sub(r"[一二两三四五六七八九十]+\s*篇", " ", text)


def _is_invalid_topic(topic: str | None) -> bool:
    if not topic:
        return True
    normalized = _clean_topic(_remove_count_phrases(topic))
    return normalized in {"", "公众号", "公总号", "文章", "内容", "篇", "几篇", "快", "快写", "草稿", "长文", "高质量", "深度", "字", "主题", "主题的", "ai科技", "AI科技", "科技", "商业", "产品", "商业产品", "商业产品主题", "人类观察", "情绪共鸣", "教程工具", "一", "二", "两", "三", "四", "五", "六", "七", "八", "九", "十"}


def _is_category_only_topic(topic: str) -> bool:
    normalized = _clean_topic(topic).replace(" ", "")
    normalized = re.sub(r"(主题的?|方向|类型)$", "", normalized)
    return normalized in {
        "ai",
        "AI",
        "科技",
        "AI科技",
        "ai科技",
        "商业",
        "产品",
        "商业产品",
        "人类观察",
        "情绪",
        "情绪共鸣",
        "教程",
        "工具",
        "教程工具",
        "不限制",
        "不限",
    }


def _chinese_number(value: str) -> int:
    digits = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    if value == "十":
        return 10
    if value.startswith("十"):
        return 10 + digits.get(value[-1], 0)
    if "十" in value:
        left, _, right = value.partition("十")
        return digits.get(left, 1) * 10 + digits.get(right, 0)
    return digits.get(value, 1)


def _is_create(text: str) -> bool:
    return any(word in text for word in ["创建", "生成", "写", "文章", "内容", "教程", "指南"])


def _is_topic_suggestion(text: str) -> bool:
    return any(word in text for word in ["热点选题", "选题建议", "给我几个主题", "推荐主题", "主题候选", "抓取热点主题", "先选题"])


def _has_action_word(text: str) -> bool:
    return any(word in text for word in ["创建", "生成", "写", "做", "观察", "复盘", "反馈"])


def _has_domain_hint(text: str) -> bool:
    return _domain_hint(text) is not None


def _is_bare_create_request(text: str) -> bool:
    cleaned = _remove_count_phrases(text)
    cleaned = re.sub(
        r"公众号文章|公总号文章|公众号|公总号|帮我|请|创建|生成|写|做|一个|一篇|文章|内容|篇|教程|观察文|爬取中英文网站|中英文网站|英文网站|中文网站|爬取|网上资料|全网|外网|AI科技|ai科技|科技|快写|草稿|长文|高质量|深度|\d+\s*字|[一二两三四五六七八九十千]+\s*字",
        " ",
        cleaned,
    )
    cleaned = _clean_topic(cleaned)
    return not cleaned


def _domain_hint(text: str) -> str | None:
    domain_terms = ["AI", "科技", "人类观察", "游戏", "产品", "商业", "心理", "工具"]
    for term in domain_terms:
        if term in text:
            return term
    return None


def _is_observe(text: str) -> bool:
    return any(word in text for word in ["观察", "热点", "趋势"])


def _is_feedback(text: str) -> bool:
    return any(word in text for word in ["复盘", "反馈", "数据"])


if __name__ == "__main__":
    main()
