#!/bin/zsh

set -uo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
cd "$SCRIPT_DIR" || exit 1

APP_DIR="$SCRIPT_DIR/.trade-tracker"
TOOLS_DIR="$APP_DIR/tools"
SERVER_SCRIPT="$TOOLS_DIR/preview_server.py"
CORE_PYC="$TOOLS_DIR/export_trade_tracker_core.pyc"
WORKBOOK="$SCRIPT_DIR/Trade Tracker.xlsx"
VENV_DIR="$SCRIPT_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"
LOG_DIR="$APP_DIR/logs"
PREVIEW_PORT="${TRADE_PREVIEW_PORT:-8765}"
PREVIEW_URL="http://127.0.0.1:${PREVIEW_PORT}/preview/index.html"

PYTHON_BIN=""

finish() {
  local exit_code=$?
  echo
  if [[ $exit_code -eq 0 ]]; then
    echo "操作完成。"
    echo "网页入口：$PREVIEW_URL"
    echo "如果浏览器没有自动打开，可以手动打开：$SCRIPT_DIR/Trade Tracker.html"
  else
    echo "启动失败，退出码：$exit_code"
    echo "日志目录：$LOG_DIR"
    echo "如果反复失败，把这个窗口截图发给维护者就行。"
  fi
  echo
  read "?按回车关闭..."
}
trap finish EXIT

say_step() {
  echo
  echo "==> $1"
}

fail() {
  echo
  echo "错误：$1"
  exit 1
}

find_python3() {
  local candidates=(
    "$VENV_PYTHON"
    "/opt/homebrew/bin/python3.14"
    "/usr/local/bin/python3.14"
    "$(command -v python3.14 2>/dev/null || true)"
    "/opt/homebrew/bin/python3"
    "/usr/local/bin/python3"
    "/usr/bin/python3"
  )
  local command_python
  command_python="$(command -v python3 || true)"
  if [[ -n "$command_python" ]]; then
    candidates+=("$command_python")
  fi
  local candidate
  for candidate in "${candidates[@]}"; do
    if [[ -x "$candidate" ]]; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

find_compatible_python3() {
  local candidates=(
    "$VENV_PYTHON"
    "/opt/homebrew/bin/python3.14"
    "/usr/local/bin/python3.14"
    "$(command -v python3.14 2>/dev/null || true)"
    "/opt/homebrew/bin/python3"
    "/usr/local/bin/python3"
    "/usr/bin/python3"
  )
  local command_python
  command_python="$(command -v python3 || true)"
  if [[ -n "$command_python" ]]; then
    candidates+=("$command_python")
  fi
  local candidate
  for candidate in "${candidates[@]}"; do
    if [[ -n "$candidate" && -x "$candidate" ]] && python_version_ok "$candidate" && core_magic_ok "$candidate"; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

python_version_ok() {
  "$1" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY
}

core_magic_ok() {
  "$1" - "$CORE_PYC" <<'PY' >/dev/null 2>&1
import importlib.util
import pathlib
import sys

core = pathlib.Path(sys.argv[1])
if not core.exists():
    raise SystemExit(0)
raise SystemExit(0 if core.read_bytes()[:4] == importlib.util.MAGIC_NUMBER else 1)
PY
}

dependencies_ok() {
  "$1" - <<'PY' >/dev/null 2>&1
import openpyxl
import pandas
PY
}

ensure_base_files() {
  [[ -d "$APP_DIR" ]] || fail "找不到 .trade-tracker 目录：$APP_DIR"
  [[ -f "$SERVER_SCRIPT" ]] || fail "找不到预览服务脚本：$SERVER_SCRIPT"
  [[ -f "$CORE_PYC" ]] || fail "找不到看板核心文件：$CORE_PYC"
  [[ -f "$WORKBOOK" ]] || fail "找不到交易工作簿：$WORKBOOK"
  mkdir -p "$LOG_DIR"
}

ensure_python() {
  say_step "检查 Python 运行环境"
  local any_python base_python
  any_python="$(find_python3 || true)"
  [[ -n "$any_python" ]] || fail "没有找到 Python 3。请先安装 Python 3.10 或更新版本。"

  base_python="$(find_compatible_python3 || true)"
  if [[ -z "$base_python" ]]; then
    if ! python_version_ok "$any_python"; then
      echo "找到了 Python，但版本太旧：$("$any_python" -V 2>&1)"
    else
      echo "找到了 Python，但它不能读取仓库内置的看板核心文件。"
    fi
    echo "当前核心文件由 Python 3.14 生成，建议安装 Python 3.14 后重试。"
    echo "例如：brew install python@3.14"
    fail "没有找到与看板核心匹配的 Python。"
  fi

  if [[ ! -x "$VENV_PYTHON" ]] || ! core_magic_ok "$VENV_PYTHON"; then
    if [[ -d "$VENV_DIR" ]]; then
      echo "本地虚拟环境和当前看板核心不匹配，正在重建：$VENV_DIR"
      rm -rf "$VENV_DIR" || fail "重建虚拟环境前清理旧 .venv 失败。"
    else
      echo "未发现本地虚拟环境，正在创建：$VENV_DIR"
    fi
    "$base_python" -m venv "$VENV_DIR" || fail "创建虚拟环境失败。"
  fi

  PYTHON_BIN="$VENV_PYTHON"
  python_version_ok "$PYTHON_BIN" || fail "本地虚拟环境里的 Python 版本太旧：$PYTHON_BIN"
  if ! core_magic_ok "$PYTHON_BIN"; then
    echo "当前 Python 无法读取仓库内置的看板核心文件。"
    echo "Python：$("$PYTHON_BIN" -V 2>&1)"
    echo "核心文件：$CORE_PYC"
    fail "请换用与本仓库匹配的 Python，或重新生成/更新看板核心文件。"
  fi
}

ensure_dependencies() {
  say_step "检查 Python 依赖"
  if dependencies_ok "$PYTHON_BIN"; then
    echo "依赖已就绪。"
    return
  fi

  echo "缺少依赖，正在安装 openpyxl / pandas。首次运行可能需要一点时间。"
  "$PYTHON_BIN" -m ensurepip --upgrade >/dev/null 2>&1 || true
  "$PYTHON_BIN" -m pip install --upgrade pip || fail "升级 pip 失败。"
  "$PYTHON_BIN" -m pip install "openpyxl>=3.1,<4" "pandas>=2.2,<4" || fail "安装依赖失败，请检查网络或 Python 环境。"

  dependencies_ok "$PYTHON_BIN" || fail "依赖安装后仍无法导入 openpyxl/pandas。"
}

start_server() {
  say_step "启动韭菜账本本地预览服务"
  echo "网页入口：$PREVIEW_URL"
  echo "保持这个窗口打开，网页里的刷新按钮才能运行。"
  echo
  export TRADE_TRACKER_PROJECT_ROOT="$SCRIPT_DIR"
  export TRADE_TRACKER_PYTHON="$PYTHON_BIN"
  "$PYTHON_BIN" "$SERVER_SCRIPT"
}

ensure_base_files
ensure_python
ensure_dependencies
start_server
