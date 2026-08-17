#!/bin/bash

set -e
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "未找到 Python 3，无法执行打包。"
  read -r -p "按回车键关闭..."
  exit 1
fi

python3 package_release.py "$@"

if [ -t 0 ]; then
  echo
  read -r -p "按回车键关闭..."
fi
