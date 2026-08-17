#!/bin/bash

set -e
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "未找到 Python 3.10 或更高版本，无法执行打包。"
  read -r -p "按回车键关闭..."
  exit 1
fi

if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
  echo "Python 版本过低，打包工具需要 Python 3.10 或更高版本。"
  read -r -p "按回车键关闭..."
  exit 1
fi

python3 package_release.py "$@"

if [ -t 0 ]; then
  echo
  read -r -p "按回车键关闭..."
fi
