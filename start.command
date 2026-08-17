#!/bin/bash
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

pause_with_error() {
  echo "$1"
  read -r -p "按回车键关闭…" || true
  exit 1
}

if [ -x "python-version/.venv/bin/python" ]; then
  LAUNCHER_PYTHON="python-version/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  LAUNCHER_PYTHON="$(command -v python3)"
else
  pause_with_error "统一启动器需要 Python 3.10 或更高版本。"
fi

if ! "$LAUNCHER_PYTHON" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
  pause_with_error "Python 版本过低。统一启动器需要 Python 3.10 或更高版本。"
fi

"$LAUNCHER_PYTHON" start.py "$@"
STATUS=$?
if [ "$STATUS" -ne 0 ] && [ -t 0 ]; then
  read -r -p "按回车键关闭…" || true
fi
exit "$STATUS"
