# World Observer Agent

观察世界，提炼规律，连接个人知识库，再把理解重新输出到世界。

这个项目不是公众号生成器。公众号只是一个 export。核心目标是建立：

```text
观察世界 -> 理解人性/模式 -> 连接 Obsidian -> 创造 -> 发布 -> 反馈 -> 更新模型
```

## 普通使用

```bash
./create.sh
```

打开交互菜单：

```text
1. 创建内容
2. 自动观察世界
3. 指定主题创作
4. 数据反馈
5. 退出
```

也可以快速传参：

```bash
./create.sh "OpenClaw安装指南"
./create.sh --count 10
```

## Agent 使用

在 Codex 对话里，可以把它当成研究助手调用：

```text
@world_observer_agent 创建10篇公众号文章
@world_observer_agent 根据 OpenClaw 安装经验生成教程
@world_observer_agent 今天观察AI领域热点
@world_observer_agent 复盘最近文章
```

Agent 调用不会立刻执行。它会先返回计划：

```text
我准备：

模式：
主题：
数量：
目标用户：
输出形式：
输出路径：

是否执行？ y/n
```

如果信息不足，它会先追问，而不是报错。

确认选项统一为：

```text
1. Yes
2. Yes, and don't ask again for similar commands
3. No, and tell Agent what to do differently
```

`No` 不是取消，而是进入修改模式。只有输入 `退出` / `cancel` / `stop` 才停止。选择 2 会保存偏好到项目根目录的 `user_preferences.yaml`，以后同类命令会跳过确认。

本地可用同一套 Agent 接口模拟：

```bash
python3 agent_interface.py "创建10篇公众号文章"
python3 agent_interface.py "观察最近AI Agent热点"
```

## 开发模式

```bash
python3 run.py --mode doctor
python3 run.py --mode observe
python3 run.py --mode create --topic "OpenClaw安装经验"
python3 run.py --mode create --topic "OpenClaw安装经验" --engine codex
python3 run.py --mode create --topic "OpenClaw安装经验" --target-reader "第一次安装 OpenClaw 的非程序员" --platform "公众号" --purpose "教程"
python3 run.py --mode create --count 10 --platform "公众号"
python3 run.py --mode import-wechat --url "https://mp.weixin.qq.com/s/xxx"
python3 run.py --mode feedback --article-id "2026-06-12_openclaw"
```

默认不会修改你的 Obsidian，也不会重构文件。Agent 只读取 `OBSIDIAN_VAULT` 指向的目录，并把新产物写入 `WORLD_OBSERVER_OUTPUT_DIR`。

`WORLD_OBSERVER_OUTPUT_DIR` 应指向实验设计记录根目录，例如：

- `04_实验设计记录/`

最终目录结构：

```text
04_实验设计记录/
  agent资料库/
    爆款库/
    观察库/
    学习库/
    反馈库/
  微信开发平台/
    公众号/
      输出/
        未发布/
          日期_标题/
            article.md
            analysis.md
            cover_prompt.txt
            images/
        已发布/
```

底层架构放在 `LifeOS/01_AI项目/World Observer Agent/`：

```text
World Observer Agent/
  系统/
    Prompt/
    模型库/
    运行日志/
  README.md
  agent_interface.py
  create.sh
  run.py
  tests/
  world_observer/
```

原则：`World Observer Agent` 是观察与创造系统，公众号只是其中一个 export 渠道。Agent 资料库不要放到公众号下面，底层架构也不要放到人生地图的公众号目录下面。

## 公众号文章导入

优先使用 `gxcsoccer/wechat-article-crawler` 抓取单篇微信公众号文章，保存为本地 Markdown，并进入公众号收藏信息源。

安装推荐路径：

```bash
mkdir -p external
git clone https://github.com/gxcsoccer/wechat-article-crawler.git external/wechat-article-crawler
pip install crawl4ai aiohttp
crawl4ai-setup
```

也可以放到任意位置，然后配置：

```bash
export WECHAT_ARTICLE_CRAWLER_DIR="/path/to/wechat-article-crawler"
```

导入单篇：

```bash
python3 run.py --mode import-wechat --url "https://mp.weixin.qq.com/s/xxx"
```

批量导入：

```bash
python3 run.py --mode import-wechat --url-file urls.txt
```

Agent 调用：

```bash
woa "导入公众号文章 https://mp.weixin.qq.com/s/xxx"
```

导入结果写入：

```text
04_实验设计记录/微信开发平台/公众号/公众号收藏信息源/
04_实验设计记录/agent资料库/爆款库/公众号导入/
```

如果 crawler 未安装，Agent 会退回到只读微信 UA 抓取；如果微信触发验证码、过期链接或登录限制，不会绕过限制。

## Environment

```bash
export OBSIDIAN_VAULT="/Users/yeqiuyi/LifeOS/10_人生OS/叶总的人生游戏试验站/叶总的人生地图"
export WORLD_OBSERVER_OUTPUT_DIR="/Users/yeqiuyi/LifeOS/10_人生OS/叶总的人生游戏试验站/叶总的人生地图/03_Research_研究复盘/实验室/04_实验设计记录"
export WORLD_OBSERVER_LLM="local"
```

可选：

```bash
export OLLAMA_MODEL="qwen2.5:7b"
export OPENAI_API_KEY="..."
export WORLD_OBSERVER_SOURCE_MODE="auto"
export WORLD_OBSERVER_FEEDS="https://sspai.com/feed,https://www.geekpark.net/rss,https://www.ifanr.com/feed,https://www.ithome.com/rss/,https://www.infoq.cn/feed,https://www.huxiu.com/rss/0.xml,https://www.36kr.com/feed"
export WORLD_OBSERVER_ANALYSIS_DEPTH="balanced"
export WORLD_OBSERVER_CREATION_ENGINE="auto"
export TREND_RADAR_ENABLED="true"
export TREND_RADAR_API_URL="https://newsnow.busiyi.world/api/s"
export TREND_RADAR_PLATFORMS="zhihu,weibo,douyin,bilibili-hot-search,toutiao,baidu,thepaper,wallstreetcn-hot,cls-hot,ifeng,tieba"
```

`WORLD_OBSERVER_SOURCE_MODE=auto` 会优先读取 TrendRadar/newsnow 多平台热榜，再补充网上 RSS/Atom 热点源，失败时自动使用离线 seed。设为 `offline` 可强制离线运行。项目根目录支持 `.env`，可以把常用爆款源写在那里。

TrendRadar 接入是轻量模式：WOA 直接读取 TrendRadar 使用的 newsnow 热榜 API，不强制安装完整 TrendRadar 服务。之后如果你自部署 TrendRadar/newsnow，只要把 `TREND_RADAR_API_URL` 改成你的地址即可。主题搜索不会只盯几个固定关键词，会先拉多个平台当前榜单，再按主题、平台、文章目的扩展词做相关性排序。

`WORLD_OBSERVER_ANALYSIS_DEPTH` 可选：

- `balanced`：默认。中间分析走稳定启发式，最终文章/反馈调用 Ollama。
- `deep`：每个 Agent 都调用 Ollama，质量更高但更慢。
- `fast`：完全不用 Ollama，适合快速冒烟测试。
- `off`：关闭模型调用。

`WORLD_OBSERVER_CREATION_ENGINE` 可选：

- `auto`：默认。优先 Codex，不可用时再尝试本地模型/API。
- `local`：用 Ollama/API 完成创作；如果是 `qwen2.5:7b`，公众号质量可能下降，建议 Codex。
- `codex`：调用本机 `codex exec` 完成创作。

## Modes

### Observe

```bash
python run.py --mode observe
```

生成：

- `agent资料库/爆款库/*.json`
- `agent资料库/观察库/*.md`
- `LifeOS/01_AI项目/World Observer Agent/系统/模型库/human-pattern-library.md`
- `LifeOS/01_AI项目/World Observer Agent/系统/运行日志/*.log`

### Doctor

```bash
python3 run.py --mode doctor
```

检查：

- Obsidian Vault 是否可读
- Ollama 是否可访问、模型是否存在
- RSS/Atom 热点源是否可抓取
- TrendRadar/newsnow 多平台热榜是否可抓取
- Agent 资料库、公众号未发布、系统目录的实际路径

### Create

```bash
python run.py --mode create --topic "OpenClaw安装经验"
```

如果没有指定主题，Agent 会按固定流程先抓外部资料，再判断本地公众号收藏的内容相关性，并从本地公众号文章提取输出格式，最后连接你的知识库观点：

```bash
woa "写一篇公众号文章"
python3 run.py --mode create --platform "公众号"
```

默认策略：

- 搜网上资料/热点/相关文献。
- 查阅本地公众号收藏资料判断相关性；有相关性可作为内容分析一部分。
- 公众号输出格式统一从本地公众号文章提取。
- 提取你的知识库观点。

文章结构不会固定使用某个比例。Agent 会根据这些因素决定结构：

- 用户输入主题
- 目标读者
- 同主题爆款文章结构
- 平台读者偏好的表达方式
- 文章目的：教程/观察/观点/复盘/工具推荐/情绪共鸣

只有当外部参考不足时，才退回到“读者优先、规律其次、个人观点少量”的默认原则。

生成：

- `微信开发平台/公众号/输出/未发布/YYYY-MM-DD_topic/article.md`
- `微信开发平台/公众号/输出/未发布/YYYY-MM-DD_topic/analysis.md`
- `微信开发平台/公众号/输出/未发布/YYYY-MM-DD_topic/cover_prompt.txt`
- `微信开发平台/公众号/输出/未发布/YYYY-MM-DD_topic/images/`

### Feedback

```bash
python run.py --mode feedback --article-id "YYYY-MM-DD_topic"
```

生成：

- `agent资料库/反馈库/*.md`
- `agent资料库/反馈库/数据.csv`

## Architecture

```text
run.py
  |
world_observer/
  |-- agents/
  |   |-- platform_intelligence.py
  |   |-- observe.py
  |   |-- viral_intelligence.py
  |   |-- pattern.py
  |   |-- brain.py
  |   |-- decision.py
  |   |-- creation.py
  |   |-- design.py
  |   |-- publish.py
  |   `-- feedback.py
  |-- integrations/
  |   |-- browser.py
  |   |-- llm.py
  |   |-- obsidian.py
  |   `-- storage.py
  `-- models.py
```

## Platform Intelligence

生成内容前会先判断输出平台。

公众号模式优先级：

```text
本地公众号收藏信息源
  -> 微信生态类似账号文章
  -> 知乎
  -> 博客
  -> Reddit/HackerNews
```

只有当目标用户明确属于 Reddit、HackerNews、X 等平台时，才默认参考这些平台。`analysis.md` 会保存 `reference_platform`、标题公式、开头结构、正文骨架、排版习惯、传播原因和迁移方式；`article.md` 只保存最终文章，不暴露参考链接和分析过程。

后续可接入的 API 边界：

- `公众号收藏信息源`：本地文件、Browser-use、微信生态抓取、第三方搜索 API。
- `WorldSource`：RSS、搜索 API、平台 API、人工收藏库。
- `Creation Engine`：local/Ollama、Codex、OpenAI API、其他模型 API。

## Current State

这是一个本地优先的可运行骨架：

- Obsidian 只读搜索。
- 输出目录自动创建。
- LLM 支持本地 Ollama，失败时使用离线启发式 fallback。
- Browser/WeChat/Canva/Figma/n8n 接口先保留清晰边界，后续接入工具即可替换。
