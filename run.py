#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from world_observer.app import WorldObserverApp


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="World Observer Agent")
    parser.add_argument(
        "--mode",
        choices=["observe", "create", "feedback", "doctor", "import-wechat", "topics"],
        required=True,
        help="Run mode.",
    )
    parser.add_argument("--topic", help="Topic for create mode.")
    parser.add_argument("--article-id", help="Article id for feedback mode.")
    parser.add_argument("--url", action="append", help="WeChat article URL for import-wechat mode. Can be repeated.")
    parser.add_argument("--url-file", help="Text file with one WeChat article URL per line.")
    parser.add_argument("--target-reader", help="Target reader for create mode.")
    parser.add_argument("--platform", help="Target platform for create mode, such as 公众号/知乎/小红书/blog.")
    parser.add_argument("--purpose", help="Article purpose: 教程/观察/观点/复盘/工具推荐/情绪共鸣.")
    parser.add_argument("--count", type=int, default=1, help="Number of drafts to create in create mode.")
    parser.add_argument("--engine", choices=["local", "codex", "auto"], help="Creation engine for create mode.")
    parser.add_argument(
        "--article-length",
        choices=["fast", "long"],
        help="For batch create: fast means 1000-2000 character drafts; long means 3000 character high-quality articles.",
    )
    parser.add_argument("--topic-category", help="Auto topic category: AI科技/人类观察/商业产品/情绪共鸣/教程工具/不限制.")
    parser.add_argument(
        "--limit",
        type=int,
        default=8,
        help="Max observations or search results to process.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    app = WorldObserverApp.from_env()

    if args.mode == "observe":
        result = app.observe(limit=args.limit)
    elif args.mode == "topics":
        result = app.suggest_topics(count=args.count if args.count > 1 else args.limit, topic_category=args.topic_category)
    elif args.mode == "doctor":
        result = app.doctor()
    elif args.mode == "import-wechat":
        urls = list(args.url or [])
        if args.url_file:
            urls.extend(_read_urls(Path(args.url_file)))
        if not urls:
            raise SystemExit("--url or --url-file is required for import-wechat mode")
        result = app.import_wechat_articles(urls)
    elif args.mode == "create":
        if args.count > 1 or not args.topic:
            result = app.create_many(
                count=args.count,
                topic=args.topic,
                limit=args.limit,
                target_reader=args.target_reader,
                platform=args.platform,
                purpose=args.purpose,
                engine=args.engine,
                article_length=args.article_length,
                topic_category=args.topic_category,
            )
        else:
            result = app.create(
                topic=args.topic,
                limit=args.limit,
                target_reader=args.target_reader,
                platform=args.platform,
                purpose=args.purpose,
                engine=args.engine,
            )
    elif args.mode == "feedback":
        if not args.article_id:
            raise SystemExit("--article-id is required for feedback mode")
        result = app.feedback(article_id=args.article_id)
    else:
        raise SystemExit(f"Unsupported mode: {args.mode}")

    print(result.summary)
    if result.path:
        print(f"Output: {result.path}")
    if result.paths:
        for path in result.paths:
            print(f"Draft: {path}")


def _read_urls(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.expanduser().read_text(encoding="utf-8", errors="ignore").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


if __name__ == "__main__":
    main()
