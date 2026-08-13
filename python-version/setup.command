#!/bin/bash
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

pause_with_error() {
  echo "$1"
  read -r -p "按回车键关闭…" || true
  exit 1
}

if ! command -v python3 >/dev/null 2>&1; then
  pause_with_error "未找到 Python 3。请先安装 Python 3.11 或更高版本。"
fi

if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
  pause_with_error "Python 版本过低。请安装 Python 3.11 或更高版本。"
fi

if [ ! -x ".venv/bin/python" ]; then
  echo "正在创建 Python 虚拟环境…"
  if ! python3 -m venv .venv; then
    pause_with_error "无法创建 .venv。请确认当前 Python 包含 venv 模块。"
  fi
fi

echo "正在安装锁定依赖…"
if ! ".venv/bin/python" -m pip install --disable-pip-version-check -r requirements.txt; then
  pause_with_error "依赖安装失败。请检查网络连接后重新运行 setup.command。"
fi

if ! ".venv/bin/python" -c 'import PIL; raise SystemExit(0 if PIL.__version__ == "12.3.0" else 1)'; then
  pause_with_error "Pillow 版本校验失败。请删除 .venv 后重新运行 setup.command。"
fi

echo "安装完成。现在可以双击 start.command。"
read -r -p "按回车键关闭…" || true
