from __future__ import annotations

from world_observer.integrations.llm import LlmClient
from world_observer.models import Observation, ViralModel


class ViralIntelligenceAgent:
    def __init__(self, llm: LlmClient) -> None:
        self.llm = llm

    def analyze_many(self, observations: list[Observation]) -> list[ViralModel]:
        return [self.analyze(item) for item in observations]

    def analyze(self, observation: Observation) -> ViralModel:
        reference_platform = observation.source.metrics.get("reference_platform", observation.source.platform)
        category = self._category(observation.phenomenon)
        type_defaults = self._defaults_for_category(category)
        fallback = {
            "title": observation.phenomenon,
            "click_reason": type_defaults["click_reason"],
            "finish_reason": type_defaults["finish_reason"],
            "save_reason": type_defaults["save_reason"],
            "share_reason": type_defaults["share_reason"],
            "comment_reason": type_defaults["comment_reason"],
            "title_mechanics": type_defaults["title_mechanics"],
            "content_structure": type_defaults["content_structure"],
            "expression_notes": type_defaults["expression_notes"],
            "reference_platform": reference_platform,
            "title_formula": self._title_formula(observation.phenomenon),
            "opening_structure": type_defaults["opening_structure"],
            "body_structure": type_defaults["body_structure"],
            "layout_notes": type_defaults["layout_notes"],
            "propagation_reason": type_defaults["propagation_reason"],
            "migration_notes": [
                {
                    "original_sentence": "不是因为____，而是因为____。",
                    "structure_formula": "不是因为A，而是因为B。",
                    "why_effective": "用转折制造认知升级，让读者获得一句可转述的判断。",
                    "how_to_migrate": "把A写成表层误解，把B写成主题背后的真实杠杆。",
                }
            ],
        }
        data = self.llm.complete_json(
            prompt=(
                "Return JSON with keys: title, click_reason, finish_reason, save_reason, "
                "share_reason, comment_reason, title_mechanics, content_structure, expression_notes, "
                "reference_platform, title_formula, opening_structure, body_structure, layout_notes, "
                "propagation_reason, migration_notes. Analyze platform-specific viral structure without copying original text.\n"
                f"Observation: {observation}"
            ),
            fallback=fallback,
            stage="viral",
        )
        normalized = {**fallback, **data}
        return ViralModel(**normalized)

    def _category(self, title: str) -> str:
        if any(name in title for name in ["李飞飞", "黄仁勋", "马斯克", "Sam Altman"]):
            return "人物"
        if any(term in title for term in ["安装", "教程", "搭建", "配置"]):
            return "教程"
        if any(term in title for term in ["工具", "AI Agent", "Claude Code", "OpenClaw"]):
            return "工具"
        if any(term in title for term in ["公司", "商业", "成本", "增长"]):
            return "商业案例"
        if any(term in title for term in ["读", "书", "自传", "世界"]):
            return "读书/自传"
        return "情绪观察"

    def _defaults_for_category(self, category: str) -> dict[str, list[str] | str]:
        defaults = {
            "人物": {
                "click_reason": "人物名背后有时代议题和读者可学习的问题意识。",
                "finish_reason": "读者期待从人物经历中获得判断、选择和行动启发。",
                "save_reason": "文章提炼出可复用的人物观察框架。",
                "share_reason": "分享人物背后的价值观和时代判断。",
                "comment_reason": "读者容易补充自己对人物和行业的看法。",
                "title_mechanics": ["人物名", "反常识", "真正厉害之处"],
                "content_structure": ["人物切入", "时代冲突", "关键选择", "问题意识", "普通人的启发"],
                "expression_notes": ["少讲履历", "多讲选择和问题意识", "用短故事承载观点"],
                "opening_structure": ["用一个反常识判断进入", "避免百科式介绍", "快速提出人物和读者的关系"],
                "body_structure": ["人物瞬间", "时代问题", "关键行动", "精神结构", "读者启发"],
                "layout_notes": ["人物段落短", "关键判断加粗", "可配书影/演讲截图"],
                "propagation_reason": ["人物提供身份投射", "时代判断可被转发"],
            },
            "教程": {
                "click_reason": "明确解决读者当下卡点。",
                "finish_reason": "步骤和避坑能降低失败成本。",
                "save_reason": "教程可复用。",
                "share_reason": "可分享给同样卡住的人。",
                "comment_reason": "读者会补充报错和环境差异。",
                "title_mechanics": ["具体对象", "避坑", "最短路径"],
                "content_structure": ["适用对象", "最短路径", "高频错误", "判断标准", "下一步"],
                "expression_notes": ["步骤清晰", "截图位置明确", "少讲空泛观点"],
                "opening_structure": ["先说卡点", "承诺跑通结果", "说明适用对象"],
                "body_structure": ["准备", "步骤", "报错", "验证", "延伸"],
                "layout_notes": ["每步配图", "命令单独代码块", "错误提示加粗"],
                "propagation_reason": ["降低行动成本", "收藏价值强"],
            },
        }
        return defaults.get(category, defaults["人物"])

    def _title_formula(self, title: str) -> str:
        if "：" in title:
            return "____：____"
        if "不要" in title:
            return "一个____真相：不要____"
        if "为什么" in title:
            return "为什么____会____"
        return "____：真正的问题不是____，而是____"
