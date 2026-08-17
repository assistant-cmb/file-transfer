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

if ! command -v npm >/dev/null 2>&1; then
  pause_with_error "未找到 npm。请重新安装包含 npm 的 Node.js。"
fi

echo "正在安装锁定依赖…"
if ! npm ci --include=optional; then
  pause_with_error "依赖安装失败。请检查网络连接后重新运行 setup.command。"
fi

if ! node -e 'const sharp = require("sharp"); process.exit(sharp.versions.sharp === "0.35.3" ? 0 : 1)'; then
  pause_with_error "sharp 版本或本机二进制校验失败。请删除 node_modules 后重新运行 setup.command。"
fi

echo "安装完成。现在可以返回项目根目录双击 start.command。"
read -r -p "按回车键关闭…" || true
