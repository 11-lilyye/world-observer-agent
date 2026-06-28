# World Observer Agent

World Observer Agent is a local-first research assistant for the loop:

```text
observe the world -> extract human patterns -> connect your notes -> create -> publish -> learn from feedback
```

It is not only a WeChat article generator. WeChat/公众号 is one export channel. The core idea is to turn outside-world signals into reusable understanding, then turn that understanding back into platform-aware drafts.

## What It Does

- Scans web/RSS/TrendRadar-style hot lists or runs offline seed observations.
- Studies platform-specific reference material before writing.
- Reads your Obsidian vault without moving or restructuring it.
- Generates drafts, research notes, metadata, and optional cover prompts.
- Keeps a local agent library for observations, viral patterns, learning notes, and feedback.
- Supports both CLI usage and conversational Agent-style invocation.

## Project Status

This is an alpha, local-first agent skeleton. It is useful for personal research workflows and content experiments, but it is not a hosted service. Network sources, WeChat crawling, image generation, and publishing integrations are intentionally modular and can be replaced.

## Quick Start

```bash
git clone https://github.com/11-lilyye/world-observer-agent.git
cd world-observer-agent
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
python3 run.py --mode doctor
```

Run the interactive menu:

```bash
./create.sh
```

Or call the agent directly:

```bash
python3 agent_interface.py "写一篇公众号文章"
python3 agent_interface.py "观察最近 AI Agent 热点"
python3 agent_interface.py "根据 OpenClaw 安装经验生成教程"
```

After `pip install -e .`, you can also use:

```bash
woa "写一篇公众号文章"
world-observer --mode doctor
```

## Configuration

Copy `.env.example` to `.env` and edit it for your machine.

The safe public defaults are:

```bash
OBSIDIAN_VAULT=./data/obsidian_vault
WORLD_OBSERVER_OUTPUT_DIR=./data/04_实验设计记录
WORLD_OBSERVER_SOURCE_MODE=auto
WORLD_OBSERVER_CREATION_ENGINE=auto
WORLD_OBSERVER_IMAGE_BACKEND=prompt_only
```

If you use Obsidian, point `OBSIDIAN_VAULT` at your vault:

```bash
OBSIDIAN_VAULT=/absolute/path/to/your/obsidian-vault
WORLD_OBSERVER_OUTPUT_DIR=/absolute/path/to/your/output-root/04_实验设计记录
```

The agent only searches the vault. It does not move or restructure your notes.

## Output Layout

All runtime files should live under `WORLD_OBSERVER_OUTPUT_DIR`.

```text
04_实验设计记录/
  agent资料库/
    爆款库/
    观察库/
    学习库/
    反馈库/
  系统/
    模型库/
    运行日志/
  微信开发平台/
    公众号/
      公众号收藏信息源/
      输出/
        未发布/
          YYYY-MM-DD_title/
            article.md
            analysis.md
            metadata.json
            cover_prompt.txt
            images/
        已发布/
```

`article.md` is the reader-facing draft.

`analysis.md` is the research notebook: topic recognition, reference structure, title pool, reasoning, Obsidian material usage, and quality checks.

`metadata.json` is machine-readable agent state.

## CLI Modes

Doctor:

```bash
python3 run.py --mode doctor
```

Observe:

```bash
python3 run.py --mode observe
```

Suggest topics:

```bash
python3 run.py --mode topics --topic-category "AI科技" --count 10
```

Create one article:

```bash
python3 run.py --mode create --topic "OpenClaw 安装经验" --platform "公众号" --purpose "教程"
```

Create multiple drafts:

```bash
python3 run.py --mode create --count 5 --platform "公众号" --article-length fast
```

Import WeChat article references:

```bash
python3 run.py --mode import-wechat --url "https://mp.weixin.qq.com/s/xxx"
python3 run.py --mode import-wechat --url-file urls.txt
```

Feedback:

```bash
python3 run.py --mode feedback --article-id "YYYY-MM-DD_title"
```

## Agent Interface

`agent_interface.py` parses natural-language commands and asks for confirmation before running.

Examples:

```text
创建10篇公众号文章
观察最近AI Agent热点
复盘最近文章
帮我写一篇关于 MBTI 的公众号长文
```

Before execution, it shows a plan:

```text
即将执行：
- 模式：create
- 主题：...
- 平台：公众号
- 生成数量：...
- 参考源：...
- 输出路径：...

是否允许？
1. Yes
2. Yes, and don't ask again for similar commands
3. No, and tell Agent what to do differently
```

`No` means "revise the plan", not "cancel". Use `cancel`, `stop`, or `退出` to stop.

## Reference Workflow

For public/default WeChat-style drafting, the agent uses this order:

1. Search web material, hot topics, RSS/TrendRadar sources, or related references.
2. Check local WeChat/公众号 saved references for relevance. Relevant local references can inform content analysis.
3. Extract the output format and rhythm from local WeChat-style articles.
4. Search your Obsidian vault for your own viewpoints, notes, cases, and experiments.

The structure is not fixed. It should depend on:

- user topic
- target reader
- platform
- reference article structure
- platform expression habits
- article purpose: tutorial, observation, opinion, review, tool recommendation, emotional resonance, etc.

When external references are insufficient, the default principle is reader-first, pattern-second, personal-opinion-light.

## Creation Engines

```bash
WORLD_OBSERVER_CREATION_ENGINE=auto
```

Supported values:

- `auto`: try Codex first, then local model if configured.
- `codex`: call local `codex exec`.
- `local`: use Ollama-compatible local model.

Local model defaults:

```bash
WORLD_OBSERVER_LLM=local
OLLAMA_MODEL=qwen2.5:7b
```

Small local models can run the workflow, but article quality may be lower than stronger models.

## World Sources

`WORLD_OBSERVER_SOURCE_MODE=auto` uses TrendRadar/newsnow-compatible hot-list APIs plus RSS/Atom feeds, then falls back to offline seeds if network sources fail. The default hot-list endpoint is configurable and is not bundled with this repository.

Optional settings:

```bash
TREND_RADAR_ENABLED=true
TREND_RADAR_API_URL=https://newsnow.busiyi.world/api/s
TREND_RADAR_PLATFORMS=zhihu,weibo,douyin,bilibili-hot-search,toutiao,baidu,thepaper,wallstreetcn-hot,cls-hot,ifeng
WORLD_OBSERVER_FEEDS=https://sspai.com/feed,https://www.geekpark.net/rss
```

Use offline mode for deterministic local tests:

```bash
WORLD_OBSERVER_SOURCE_MODE=offline
```

Hot-source implementation lives in:

```text
world_observer/integrations/browser.py
```

Important entry points:

- `daily_world_scan()` collects broad hot topics.
- `_trendradar_sources()` reads TrendRadar/newsnow-compatible hot-list APIs.
- `_rss_sources()` reads RSS/Atom feeds.
- `search_topic_for_platform()` expands topic-specific references.

The default `TREND_RADAR_API_URL` is treated as a configurable public endpoint. If you self-host or use a different hot-list service, point `TREND_RADAR_API_URL` to your own compatible API.

## WeChat Article Import

The importer can optionally use `gxcsoccer/wechat-article-crawler` for single-article WeChat imports.

```bash
mkdir -p external
git clone https://github.com/gxcsoccer/wechat-article-crawler.git external/wechat-article-crawler
pip install ".[wechat]"
```

Or set:

```bash
WECHAT_ARTICLE_CRAWLER_DIR=/path/to/wechat-article-crawler
```

If the crawler is unavailable, blocked by login, or hits a verification page, the agent does not bypass platform limits.

## Acknowledgements

World Observer Agent is designed to work with public or self-hosted hot-topic sources:

- TrendRadar/newsnow-compatible hot-list APIs are used as optional world-observation sources.
- RSS/Atom feeds are used as optional public reference sources.
- [gxcsoccer/wechat-article-crawler](https://github.com/gxcsoccer/wechat-article-crawler) is only an optional helper for WeChat article import, not a bundled dependency.

Please follow the original licenses and terms of any external source or service you configure.

## Why Python?

Python is used as the core runtime because it is practical for agent orchestration: file IO, RSS parsing, local model calls, Obsidian search, CLI workflows, and Markdown output are all simple to maintain in one place.

Other runtimes can make the project stronger:

- TypeScript/Node.js: browser automation, web dashboards, API services, and richer integrations with Playwright or browser-use.
- React/Next.js: a local review UI for selecting topics, editing drafts, and comparing article performance.
- SQLite/Postgres: durable memory for topics, references, duplicate detection, feedback metrics, and long-term experiments.
- n8n: scheduled observe/create/feedback workflows without keeping a terminal open.
- Browser-use/Computer Use: logged-in platform research, publishing assistance, and feedback collection where APIs are unavailable.
- Rust/Go: faster crawlers or background workers if source collection becomes heavy.

The current repository keeps Python as the stable core and leaves these integrations as replaceable boundaries.

## Development

```bash
pip install -e ".[dev]"
pytest
python3 -B -m py_compile run.py agent_interface.py
```

Useful files:

```text
run.py                         # structured CLI
agent_interface.py             # natural language interface
world_observer/app.py          # app orchestration
world_observer/agents/         # observe / pattern / creation / feedback agents
world_observer/integrations/   # config / storage / browser / llm / obsidian
tests/test_smoke.py            # offline smoke test
```

## Privacy And Safety

- `.env`, `data/`, generated drafts, and runtime libraries are ignored by git.
- The agent reads Obsidian notes but should not reorganize them.
- Article drafts should not include internal agent analysis, local file paths, or private notes unless you intentionally add them.
- `analysis.md` may include source paths and research details; review it before publishing or sharing.

## License

MIT
