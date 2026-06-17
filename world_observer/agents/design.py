from __future__ import annotations


class DesignAgent:
    """Placeholder boundary for Canva/Figma/image generation pipelines."""

    def choose_tool(self, visual_goal: str) -> str:
        if any(keyword in visual_goal for keyword in ["结构", "信息图", "模板", "品牌"]):
            return "Canva/Figma"
        if any(keyword in visual_goal for keyword in ["概念", "氛围", "艺术", "抽象"]):
            return "image2/Nano Banana"
        return "network image or screenshot"

