#!/usr/bin/env python3
"""Select and start the local File Transfer server from one entry point."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parent
PYTHON_ROOT = PROJECT_ROOT / "python-version"
NODE_ROOT = PROJECT_ROOT / "node-version"
PILLOW_MIN_MAJOR = 12


def run_probe(command: list[str], cwd: Path) -> bool:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        return False
    return result.returncode == 0


def python_candidates() -> list[Path]:
    virtual_python = (
        PYTHON_ROOT / ".venv" / "Scripts" / "python.exe"
        if sys.platform == "win32"
        else PYTHON_ROOT / ".venv" / "bin" / "python"
    )
    candidates = [virtual_python, Path(sys.executable)]
    unique: list[Path] = []
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved not in unique:
            unique.append(resolved)
    return unique


def find_python_runtime() -> Path | None:
    probe = (
        "import sys, PIL; "
        f"raise SystemExit(0 if sys.version_info >= (3, 10) and int(PIL.__version__.split('.')[0]) >= {PILLOW_MIN_MAJOR} else 1)"
    )
    for executable in python_candidates():
        if executable.is_file() and run_probe([str(executable), "-c", probe], PYTHON_ROOT):
            return executable
    return None


def find_node_runtime() -> str | None:
    executable = shutil.which("node")
    if executable is None:
        return None
    probe = (
        "const [major,minor]=process.versions.node.split('.').map(Number);"
        "const sharp=require('sharp');process.exit((major>20||(major===20&&minor>=9))&&sharp?0:1)"
    )
    return executable if run_probe([executable, "-e", probe], NODE_ROOT) else None


def parse_args() -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(
        description="启动 File Transfer；默认优先 Python，不可用时回退 Node.js"
    )
    parser.add_argument(
        "--runtime",
        choices=("auto", "python", "node"),
        default="auto",
        help="指定运行时；默认 auto（Python 优先）",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="只检查并显示将使用的运行时，不启动服务",
    )
    return parser.parse_known_args()


def main() -> int:
    args, server_args = parse_args()
    python_runtime = find_python_runtime() if args.runtime != "node" else None
    node_runtime = find_node_runtime() if args.runtime != "python" else None

    if python_runtime is not None:
        label = f"Python ({python_runtime})"
        command = [str(python_runtime), "-m", "file_transfer", "serve", *server_args]
        cwd = PYTHON_ROOT
    elif node_runtime is not None:
        label = f"Node.js ({node_runtime})"
        command = [node_runtime, "src/cli.js", "serve", *server_args]
        cwd = NODE_ROOT
    else:
        if args.runtime == "python":
            detail = "Python 3.10+ 或 Pillow 12+ 不可用"
        elif args.runtime == "node":
            detail = "Node.js 20.9.0+ 或兼容的 sharp 不可用"
        else:
            detail = "Python 版和 Node.js 版都不可用"
        print(f"启动失败：{detail}。", file=sys.stderr)
        print("请先运行根目录的统一 setup 脚本。", file=sys.stderr)
        return 1

    print(f"使用 {label}")
    if args.check:
        return 0

    try:
        return subprocess.call(command, cwd=cwd)
    except KeyboardInterrupt:
        return 130
    except OSError as error:
        print(f"启动失败：{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
