#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
if ! command -v python3 >/dev/null 2>&1; then
  echo "未找到 Python 3。请先安装 Python 3.11 或更高版本。"
  read -r -p "按回车键关闭…"
  exit 1
fi
if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
  echo "Python 版本过低。请安装 Python 3.11 或更高版本。"
  read -r -p "按回车键关闭…"
  exit 1
fi
python3 -m file_transfer serve
