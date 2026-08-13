#!/bin/bash
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

pause_with_error() {
  echo "$1"
  read -r -p "按回车键关闭…" || true
  exit 1
}

if ! command -v node >/dev/null 2>&1; then
  pause_with_error "未找到 Node.js。请先安装 Node.js 20.9.0 或更高版本。"
fi

if ! node -e 'const [major, minor] = process.versions.node.split(".").map(Number); process.exit(major > 20 || (major === 20 && minor >= 9) ? 0 : 1)'; then
  pause_with_error "Node.js 版本过低。请安装 Node.js 20.9.0 或更高版本。"
fi

if ! node -e 'const sharp = require("sharp"); process.exit(sharp.versions.sharp === "0.35.3" ? 0 : 1)' >/dev/null 2>&1; then
  pause_with_error "缺少 sharp 0.35.3 或本机二进制不可用。请先双击 setup.command 安装依赖。"
fi

exec node src/cli.js serve
