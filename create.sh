#!/usr/bin/env bash
set -euo pipefail

SOURCE="${BASH_SOURCE[0]}"
while [[ -L "$SOURCE" ]]; do
  DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
  SOURCE="$(readlink "$SOURCE")"
  [[ "$SOURCE" != /* ]] && SOURCE="$DIR/$SOURCE"
done
ROOT_DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
cd "$ROOT_DIR"

if [[ "$#" -gt 0 ]]; then
  if [[ "${1:-}" == "--count" ]]; then
    count="${2:-1}"
    python3 agent_interface.py "创建${count}篇公众号文章"
  elif [[ "${1:-}" == --* ]]; then
    python3 agent_interface.py "$@"
  else
    request="$*"
    if [[ "$request" =~ (创建|生成|写|观察|复盘|反馈|导入|抓取|保存|文章|热点|公众号|公总号|mp.weixin.qq.com) ]]; then
      python3 agent_interface.py "$request"
    else
      python3 agent_interface.py "根据 $request 生成文章"
    fi
  fi
  exit 0
fi

while true; do
  cat <<'MENU'

World Observer Agent

1. 创建内容
2. 自动观察世界
3. 指定主题创作
4. 数据反馈
5. 退出

MENU
  read -r -p "选择： " choice

  case "$choice" in
    1)
      python3 agent_interface.py "创建文章"
      ;;
    2)
      python3 agent_interface.py "今天观察世界热点"
      ;;
    3)
      read -r -p "主题： " topic
      python3 agent_interface.py "根据 ${topic} 生成文章"
      ;;
    4)
      python3 agent_interface.py "复盘最近文章"
      ;;
    5)
      exit 0
      ;;
    *)
      echo "请输入 1-5。"
      ;;
  esac
done
