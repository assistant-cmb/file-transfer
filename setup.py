#!/usr/bin/env python3
"""Install File Transfer runtime dependencies from one entry point."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parent
PYTHON_ROOT = PROJECT_ROOT / "python-version"
NODE_ROOT = PROJECT_ROOT / "node-version"
PILLOW_MIN_MAJOR = 12


class SetupError(RuntimeError):
    pass


def run(command: list[str], cwd: Path, error_message: str) -> None:
    try:
        result = subprocess.run(command, cwd=cwd, check=False)
    except OSError as error:
        raise SetupError(f"{error_message}：{error}") from error
    if result.returncode != 0:
        raise SetupError(error_message)


def platform_command(executable: str, *arguments: str) -> list[str]:
    if sys.platform == "win32" and Path(executable).suffix.lower() in {".bat", ".cmd"}:
        return [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", executable, *arguments]
    return [executable, *arguments]


def command_output(command: list[str], cwd: Path) -> str | None:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def python_venv_executable() -> Path:
    return (
        PYTHON_ROOT / ".venv" / "Scripts" / "python.exe"
        if sys.platform == "win32"
        else PYTHON_ROOT / ".venv" / "bin" / "python"
    )


def show_environment_status() -> None:
    print("当前运行环境检测：")
    python_version = ".".join(str(part) for part in sys.version_info[:3])
    python_supported = sys.version_info >= (3, 10)
    print(
        f"  Python：已找到 {python_version}（{'可用' if python_supported else '版本过低'}）\n"
        f"          {sys.executable}"
    )

    venv_python = python_venv_executable()
    if venv_python.exists():
        venv_status = command_output(
            [
                str(venv_python),
                "-c",
                "import sys; print('.'.join(map(str,sys.version_info[:3]))); "
                "\ntry:\n import PIL; print('Pillow '+PIL.__version__)\nexcept ImportError:\n print('Pillow 未安装')",
            ],
            PYTHON_ROOT,
        )
        if venv_status:
            print(f"  Python 虚拟环境：已存在（{venv_status.replace(chr(10), '，')}）")
        else:
            print("  Python 虚拟环境：存在但无法运行，可能指向已卸载的 Python")
    else:
        print("  Python 虚拟环境：尚未创建")

    node = shutil.which("node")
    if node is None:
        print("  Node.js：未找到")
    else:
        node_version = command_output([node, "--version"], NODE_ROOT)
        if node_version is None:
            print(f"  Node.js：已找到但无法运行\n           {node}")
        else:
            print(f"  Node.js：已找到 {node_version}\n           {node}")

    npm = shutil.which("npm")
    if npm is None:
        print("  npm：未找到")
    else:
        npm_version = command_output(platform_command(npm, "--version"), NODE_ROOT)
        if npm_version is None:
            print(f"  npm：已找到但无法运行\n       {npm}")
        else:
            print(f"  npm：已找到 {npm_version}\n       {npm}")
    print()


def install_python() -> None:
    if sys.version_info < (3, 10):
        raise SetupError("Python 版需要 Python 3.10 或更高版本")

    venv_python = python_venv_executable()
    if venv_python.exists():
        try:
            usable = subprocess.run(
                [str(venv_python), "-c", "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"],
                cwd=PYTHON_ROOT,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            ).returncode == 0
        except OSError:
            usable = False
        if not usable:
            raise SetupError(
                "现有 python-version/.venv 无效或指向已卸载的 Python；请删除该目录后重试"
            )
    else:
        print("正在创建 Python 虚拟环境…", flush=True)
        run(
            [sys.executable, "-m", "venv", str(PYTHON_ROOT / ".venv")],
            PYTHON_ROOT,
            "无法创建 Python 虚拟环境；请确认当前 Python 包含 venv 模块",
        )

    print(f"正在安装 Pillow {PILLOW_MIN_MAJOR} 或更高版本…", flush=True)
    run(
        [
            str(venv_python),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "-r",
            "requirements.txt",
        ],
        PYTHON_ROOT,
        "Python 依赖安装失败；请检查 pip 源和网络连接",
    )
    run(
        [
            str(venv_python),
            "-c",
            f"import PIL; raise SystemExit(0 if int(PIL.__version__.split('.')[0]) >= {PILLOW_MIN_MAJOR} else 1)",
        ],
        PYTHON_ROOT,
        f"Pillow {PILLOW_MIN_MAJOR}+ 校验失败",
    )
    print("Python 版安装完成。", flush=True)


def install_node() -> None:
    node = shutil.which("node")
    npm = shutil.which("npm")
    if node is None:
        raise SetupError("未找到 Node.js 20.9.0 或更高版本")
    if npm is None:
        raise SetupError("未找到 npm；请重新安装包含 npm 的 Node.js")

    run(
        [
            node,
            "-e",
            "const [a,b]=process.versions.node.split('.').map(Number);process.exit(a>20||(a===20&&b>=9)?0:1)",
        ],
        NODE_ROOT,
        "Node.js 版本过低；需要 20.9.0 或更高版本",
    )
    print("正在安装 npm 源中可用的 sharp…", flush=True)
    run(
        platform_command(npm, "install", "--include=optional", "--no-package-lock"),
        NODE_ROOT,
        "Node 依赖安装失败；请检查 npm 源和网络连接",
    )
    run(
        [node, "-e", "require('sharp')"],
        NODE_ROOT,
        "sharp 或本机二进制无法加载；请删除 node_modules 后重试",
    )
    print("Node.js 版安装完成。", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="安装 File Transfer 运行依赖")
    parser.add_argument(
        "--runtime",
        choices=("python", "node", "all"),
        help="安装目标；省略时显示交互选择，可选 python、node 或 all",
    )
    return parser.parse_args()


def choose_runtime(requested: str | None) -> str:
    if requested is not None:
        return requested

    print("请选择要安装的运行环境：")
    print("  1. Python（推荐，启动时优先使用）")
    print("  2. Node.js")
    print("  3. Python 和 Node.js 全部安装")
    choices = {"1": "python", "2": "node", "3": "all"}
    while True:
        try:
            selected = input("请输入 1、2 或 3 [默认 1]：").strip() or "1"
        except EOFError as error:
            raise SetupError("无法读取安装选择；请使用 --runtime python、node 或 all") from error
        if selected in choices:
            return choices[selected]
        print("输入无效，请输入 1、2 或 3。")


def main() -> int:
    args = parse_args()
    show_environment_status()
    try:
        runtime = choose_runtime(args.runtime)
    except SetupError as error:
        print(f"安装失败：{error}", file=sys.stderr)
        return 1

    installers = []
    if runtime in {"python", "all"}:
        installers.append(("Python", install_python))
    if runtime in {"node", "all"}:
        installers.append(("Node.js", install_node))

    failures: list[str] = []
    for label, installer in installers:
        try:
            installer()
        except SetupError as error:
            failures.append(f"{label}：{error}")
            print(f"{label} 安装失败：{error}", file=sys.stderr)

    if failures:
        if len(installers) > 1:
            print("已继续尝试其他所选运行环境。", file=sys.stderr)
        return 1

    print("安装完成。现在可以运行根目录的统一启动脚本。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
