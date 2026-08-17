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
  pause_with_error "统一安装器需要 Python 3.10 或更高版本。"
fi

if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
  pause_with_error "Python 版本过低。统一安装器需要 Python 3.10 或更高版本。"
fi

python3 setup.py "$@"
STATUS=$?
if [ "$STATUS" -ne 0 ] && [ -t 0 ]; then
  read -r -p "按回车键关闭…" || true
fi
exit "$STATUS"
