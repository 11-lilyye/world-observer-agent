from __future__ import annotations

from dataclasses import dataclass, field
import re


@dataclass(frozen=True)
class VisualRoute:
    key: str
    name: str
    applies_to: list[str]
    artist_mix: list[str]
    feeling: str
    elements: list[str]
    prompt: str


@dataclass(frozen=True)
class VisualPlan:
    system_name: str
    category: str
    route_name: str
    artist_mix: list[str]
    why: str
    metaphor: str
    core_problem: str
    human_conflict: str
    hidden_pattern: str
    emotional_energy: str
    cover_prompt: str
    image_prompts: list[str]
    negative_prompt: str
    backend: str
    fallback_backend: str
    generated_files: list[str] = field(default_factory=list)
    generation_note: str = ""


BASE_PROMPT = (
    "modern art editorial illustration, museum poster aesthetic, large negative space, "
    "bold color relationship, conceptual metaphor, future laboratory notebook aesthetic, "
    "16:9 horizontal composition"
)

NEGATIVE_PROMPT = (
    "cyberpunk, glowing AI robot, blue purple neon, photorealistic stock image, 3D render, over detailed"
)


ROUTES: tuple[VisualRoute, ...] = (
    VisualRoute(
        key="ai_code_system",
        name="AI / Code / System",
        applies_to=["OpenClaw", "Codex", "AI Agent", "GitHub", "API", "技术教程", "代码", "自动化"],
        artist_mix=["Bauhaus 45%", "Josef Albers 35%", "Swiss Design 20%"],
        feeling="世界是一台可以拆开的机器。",
        elements=["abstract machine", "system map", "colored modules", "data pipeline", "information architecture", "network"],
        prompt=(
            "bauhaus inspired editorial design, josef albers color interaction, geometric abstraction, "
            "modular system, abstract machine, information architecture, clean white space, precise composition"
        ),
    ),
    VisualRoute(
        key="human_profile_creator",
        name="Human Profile / Creator",
        applies_to=["李飞飞", "创业者", "科学家", "艺术家", "人物", "自传", "作者", "创造者"],
        artist_mix=["Olimpia Zagnoli 40%", "Malika Favre 30%", "Matisse 30%"],
        feeling="画人的内在世界，而不是头像。",
        elements=["inner landscape", "memory", "knowledge universe", "symbolic portrait", "book", "eye", "map"],
        prompt=(
            "modern editorial portrait, bold color blocks, negative space, human emotion, "
            "abstract inner landscape, matisse organic shapes, simplified editorial portrait"
        ),
    ),
    VisualRoute(
        key="life_lab_psychology",
        name="Life Lab / Psychology",
        applies_to=["人生", "心理", "成长", "关系", "哲学", "实验室", "情绪", "自我"],
        artist_mix=["Paul Klee 35%", "Joan Miro 35%", "Blexbolex 30%"],
        feeling="成年人研究世界的童话。",
        elements=["door", "planet", "maze", "tree", "ocean", "tiny explorer", "dream world"],
        prompt=(
            "poetic abstract illustration, symbolic universe, simple shapes, childlike curiosity, "
            "philosophical mood, print texture, tiny explorer"
        ),
    ),
    VisualRoute(
        key="business_brand",
        name="Business / Brand",
        applies_to=["公司", "产品", "商业", "品牌", "制造", "增长", "市场", "中国制造"],
        artist_mix=["Malika Favre 40%", "Swiss Poster 35%", "Josef Albers 25%"],
        feeling="高级商业杂志封面。",
        elements=["market system", "city blocks", "signal", "growth", "symbolic product"],
        prompt=(
            "premium editorial illustration, strong negative space, bold symbolic object, "
            "business magazine cover, geometric color relationship"
        ),
    ),
    VisualRoute(
        key="culture_observation",
        name="Culture Observation",
        applies_to=["社会", "趋势", "消费", "玄学", "互联网文化", "热点", "文化", "人群"],
        artist_mix=["Blexbolex 40%", "Matisse 30%", "Joan Miro 30%"],
        feeling="未来人类观察图鉴。",
        elements=["crowd", "city", "behavior pattern", "strange symbols", "social map"],
        prompt=(
            "anthropological visual notebook, abstract society map, symbolic humans, "
            "editorial illustration, modern art language"
        ),
    ),
    VisualRoute(
        key="racing_manufacturing",
        name="Racing / Manufacturing",
        applies_to=["WSBK", "WorldSSP", "张雪", "机车", "汽车", "工业", "赛车", "赛道"],
        artist_mix=["Swiss Racing Poster 40%", "Bauhaus 30%", "Futurism 30%"],
        feeling="速度和机器系统被压缩成一张秩序图。",
        elements=["track geometry", "speed line", "machine system", "motion abstraction", "rider as symbol"],
        prompt=(
            "minimal racing poster, abstract track geometry, motion lines, bauhaus machine system, "
            "bold color relationship"
        ),
    ),
)


class VisualStyleRouter:
    system_name = "World Observer Visual System"

    def build_plan(
        self,
        topic: str,
        article_markdown: str,
        purpose: str | None,
        backend: str = "canva_figma",
        fallback_backend: str = "prompt_only",
    ) -> VisualPlan:
        route = self.route(topic, article_markdown, purpose)
        core = self._extract_core_problem(article_markdown, topic)
        conflict = self._extract_human_conflict(article_markdown, purpose)
        pattern = self._extract_hidden_pattern(article_markdown, route)
        emotion = self._extract_emotional_energy(article_markdown, purpose)
        metaphor = self._metaphor(route, core)
        prompt = self._cover_prompt(topic, route, core, conflict, pattern, metaphor)
        image_prompts = self._image_prompts(topic, route, core, pattern, metaphor)
        return VisualPlan(
            system_name=self.system_name,
            category=route.key,
            route_name=route.name,
            artist_mix=route.artist_mix,
            why=f"主题和文章目的更接近「{route.name}」：{route.feeling}",
            metaphor=metaphor,
            core_problem=core,
            human_conflict=conflict,
            hidden_pattern=pattern,
            emotional_energy=emotion,
            cover_prompt=prompt,
            image_prompts=image_prompts,
            negative_prompt=NEGATIVE_PROMPT,
            backend=backend,
            fallback_backend=fallback_backend,
        )

    def route(self, topic: str, article_markdown: str, purpose: str | None) -> VisualRoute:
        haystack = f"{topic} {purpose or ''} {article_markdown[:600]}".lower()
        best = ROUTES[4]
        best_score = -1
        for route in ROUTES:
            score = 0
            for keyword in route.applies_to:
                if keyword.lower() in haystack:
                    score += 2 if keyword.lower() in f"{topic} {purpose or ''}".lower() else 1
            if route.key == "culture_observation":
                score += 1
            if score > best_score:
                best = route
                best_score = score
        return best

    def _cover_prompt(self, topic: str, route: VisualRoute, core: str, conflict: str, pattern: str, metaphor: str) -> str:
        elements = ", ".join(route.elements[:5])
        return (
            f"{BASE_PROMPT}, {route.prompt}, metaphor: {metaphor}, topic: {topic}, "
            f"core: {core}, elements: {elements}, cover for WeChat article, "
            f"leave clean space for Chinese title typography. Negative prompt: {NEGATIVE_PROMPT}"
        )

    def _image_prompts(self, topic: str, route: VisualRoute, core: str, pattern: str, metaphor: str) -> list[str]:
        return [
            (
                f"Interior editorial diagram for '{topic}': show the hidden pattern '{pattern}', "
                f"{route.name}, modern art notebook, abstract but readable, 16:9."
            ),
        ]

    def _metaphor(self, route: VisualRoute, core: str) -> str:
        if route.key == "ai_code_system":
            return f"一张被拆开的机器地图，普通人沿着模块找到进入 {core} 的入口"
        if route.key == "human_profile_creator":
            return f"一个人的内在宇宙被展开成地图，知识、记忆和问题意识围绕中心发光"
        if route.key == "life_lab_psychology":
            return f"一个 tiny explorer 站在门、迷宫和星球之间，研究自己的下一步"
        if route.key == "business_brand":
            return f"市场像城市街区一样被重新排列，一个信号从中心物体向外扩散"
        if route.key == "racing_manufacturing":
            return f"赛道、机器和速度线变成一套可观察的工业系统"
        return f"未来观察者摊开一张社会地图，看见人群行为背后的隐形规律"

    def _extract_core_problem(self, markdown: str, topic: str) -> str:
        for line in markdown.splitlines():
            text = line.strip(" #*")
            if "？" in text or "?" in text:
                return self._clean_text(text)
        return f"{topic}背后的隐形结构是什么"

    def _extract_human_conflict(self, markdown: str, purpose: str | None) -> str:
        text = self._clean_text(markdown[:1200])
        if "焦虑" in text or "不确定" in text:
            return "人想获得确定感，但世界变化太快"
        if "教程" in (purpose or "") or "安装" in text:
            return "人想开始行动，但第一步被工具和流程挡住"
        if "人物" in (purpose or ""):
            return "人想理解一个人真正厉害的地方，而不是只看履历"
        return "人想理解世界，却常被信息碎片拖着走"

    def _extract_hidden_pattern(self, markdown: str, route: VisualRoute) -> str:
        text = self._clean_text(markdown[:2000])
        if "行动" in text or "实验" in text:
            return "低成本实验正在改变普通人的行动门槛"
        if "收藏" in text or "转发" in text:
            return "内容传播背后是解释系统和身份确认"
        if route.key == "ai_code_system":
            return "复杂系统正在被工具拆成普通人可操作的模块"
        return "被关注的不是事件本身，而是它解释了某种时代情绪"

    def _extract_emotional_energy(self, markdown: str, purpose: str | None) -> str:
        text = self._clean_text(markdown[:1600])
        if "焦虑" in text:
            return "焦虑被转化为理解和行动"
        if "普通人" in text:
            return "普通人获得重新定位自己的可能性"
        if "人物" in (purpose or ""):
            return "从崇拜人物转向学习问题意识"
        return "好奇、判断和轻微的不确定感"

    @staticmethod
    def _clean_text(text: str) -> str:
        text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
        text = re.sub(r"[#>*_`]+", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()[:120]
