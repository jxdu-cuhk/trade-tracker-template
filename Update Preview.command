#!/bin/zsh

set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [[ -x "$SCRIPT_DIR/.venv/bin/python" ]]; then
  PYTHON_BIN="$SCRIPT_DIR/.venv/bin/python"
else
  PYTHON_BIN="$(command -v python3 || true)"
fi
if [[ -z "$PYTHON_BIN" ]]; then
  echo "没有找到可用的 Python 3。"
  echo "请先安装 Python 3，再重新运行这个脚本。"
  echo
  read "?按回车关闭..."
  exit 1
fi

PREVIEW_URL="http://127.0.0.1:8765/preview/index.html"
SERVER_SCRIPT="$SCRIPT_DIR/.trade-tracker/tools/preview_server.py"

finish() {
  local exit_code=$?
  echo
  if [[ $exit_code -eq 0 ]]; then
    echo "操作完成。"
    echo "现在可以直接打开韭菜账本：$SCRIPT_DIR/Trade Tracker.html"
  else
    echo "预览服务启动失败，退出码：$exit_code"
    echo "如果反复失败，把这个窗口截图发给我就行。"
  fi
  echo
  read "?按回车关闭..."
}
trap finish EXIT

echo "正在启动韭菜账本本地预览服务..."
echo "网页入口：$PREVIEW_URL"
echo "保持这个窗口打开，网页里的刷新按钮才能运行。"
echo
"$PYTHON_BIN" "$SERVER_SCRIPT"
