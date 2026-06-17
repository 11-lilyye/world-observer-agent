from __future__ import annotations

from world_observer.integrations.llm import LlmClient
from world_observer.integrations.storage import Storage


class FeedbackAgent:
    def __init__(self, llm: LlmClient, storage: Storage) -> None:
        self.llm = llm
        self.storage = storage

    def analyze(self, article_id: str) -> str:
        fallback = f"""# {article_id} 反馈复盘

## 当前状态

尚未接入公众号后台自动抓取。请先把阅读、点赞、收藏、分享、关注、评论写入 `agent资料库/反馈库/数据.csv`。

## 分析框架

- 阅读：标题和选题是否完成了第一层吸引。
- 点赞：观点是否让读者产生认同。
- 收藏：方法或模型是否有复用价值。
- 分享：内容是否替读者表达了某种处境。
- 关注：读者是否期待后续连续观察。
- 评论：是否激发了个人经验补充或立场表达。

## 下一步

接入 Computer Use 登录公众号后台后，这里会自动生成成功模式、失败模式、传播规律和读者画像。
"""
        return self.llm.complete_text(
            prompt=f"Write a Chinese feedback analysis report for article_id={article_id}.",
            fallback=fallback,
            stage="feedback",
        )
