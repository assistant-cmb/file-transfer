#!/bin/bash
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

pause_with_error() {
  echo "$1"
  read -r -p "按回车键关闭…" || true
  exit 1
}

if [ -x ".venv/bin/python" ]; then
  PYTHON_BIN=".venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
else
  pause_with_error "未找到 Python 3。请先安装 Python 3.11 或更高版本。"
fi

if ! "$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
  pause_with_error "Python 版本过低。请安装 Python 3.11 或更高版本。"
fi

if ! "$PYTHON_BIN" -c 'import PIL; raise SystemExit(0 if PIL.__version__ == "12.3.0" else 1)' >/dev/null 2>&1; then
  pause_with_error "缺少 Pillow 12.3.0。请先双击 setup.command 安装依赖。"
fi

exec "$PYTHON_BIN" -m file_transfer serve
