#!/usr/bin/env python3
"""Build a clean, transferable ZIP release using only the Python standard library."""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import os
from pathlib import Path
import stat
import sys
import tempfile
import zipfile


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "dist"

# Installed dependencies, generated files, source-control metadata and test assets.
EXCLUDED_DIR_NAMES = {
    ".git",
    ".agents",
    ".codex",
    ".github",
    ".idea",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    ".vscode",
    "__pycache__",
    "coverage",
    "dist",
    "env",
    "fixtures",
    "node_modules",
    "tests",
    "venv",
}

EXCLUDED_FILE_NAMES = {
    ".DS_Store",
    ".coverage",
    ".gitignore",
    "PLAN.md",
    "REQUIREMENTS.md",
    "package-lock.json",
    "package.bat",
    "package.command",
    "package_release.py",
}

EXCLUDED_SUFFIXES = {".log", ".pyc", ".pyo", ".swp", ".tmp"}


def should_include(path: Path) -> bool:
    relative = path.relative_to(PROJECT_ROOT)
    if any(part in EXCLUDED_DIR_NAMES for part in relative.parts[:-1]):
        return False
    if path.name in EXCLUDED_FILE_NAMES:
        return False
    return path.suffix.lower() not in EXCLUDED_SUFFIXES


def iter_release_files(output_dir: Path) -> list[Path]:
    try:
        output_relative = output_dir.relative_to(PROJECT_ROOT)
    except ValueError:
        output_relative = None

    files = [
        path
        for path in PROJECT_ROOT.rglob("*")
        if path.is_file()
        and not path.is_symlink()
        and should_include(path)
        and (
            output_relative is None
            or not path.relative_to(PROJECT_ROOT).is_relative_to(output_relative)
        )
    ]
    return sorted(files, key=lambda path: path.relative_to(PROJECT_ROOT).as_posix())


def zip_info(archive_name: str, source: Path) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(archive_name)
    modified = datetime.fromtimestamp(source.stat().st_mtime)
    # ZIP timestamps cannot represent years before 1980.
    info.date_time = (
        max(modified.year, 1980), modified.month, modified.day,
        modified.hour, modified.minute, modified.second,
    )
    permissions = 0o755 if source.stat().st_mode & stat.S_IXUSR else 0o644
    info.external_attr = (stat.S_IFREG | permissions) << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    return info


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_release(output_dir: Path, archive_name: str | None) -> tuple[Path, int, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = archive_name or f"file-transfer-{timestamp}.zip"
    if Path(filename).name != filename or filename in {"", ".", ".."}:
        raise RuntimeError("--name 只能是文件名，不能包含目录")
    if not filename.lower().endswith(".zip"):
        filename += ".zip"
    destination = (output_dir / filename).resolve()

    files = iter_release_files(output_dir)
    if not files:
        raise RuntimeError("没有找到可以打包的文件")

    try:
        destination_relative = destination.relative_to(PROJECT_ROOT)
    except ValueError:
        destination_relative = None

    with tempfile.NamedTemporaryFile(
        prefix=".file-transfer-package-", suffix=".zip", dir=output_dir, delete=False
    ) as temporary:
        temporary_path = Path(temporary.name)

    try:
        with zipfile.ZipFile(temporary_path, "w", allowZip64=True) as archive:
            for source in files:
                relative = source.relative_to(PROJECT_ROOT)
                if destination_relative is not None and relative == destination_relative:
                    continue
                archive_path = (Path("file-transfer") / relative).as_posix()
                archive.writestr(zip_info(archive_path, source), source.read_bytes())
        os.replace(temporary_path, destination)
    finally:
        temporary_path.unlink(missing_ok=True)

    digest = sha256_file(destination)
    checksum = destination.with_suffix(destination.suffix + ".sha256")
    checksum.write_text(f"{digest}  {destination.name}\n", encoding="utf-8")
    return destination, len(files), digest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成不包含依赖和开发文件的传输包")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="输出目录")
    parser.add_argument("--name", help="ZIP 文件名；默认使用当前时间")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        archive, count, digest = build_release(args.output_dir.resolve(), args.name)
    except (OSError, RuntimeError, zipfile.BadZipFile) as error:
        print(f"打包失败：{error}", file=sys.stderr)
        return 1

    print(f"打包完成：{archive}")
    print(f"文件数量：{count}")
    print(f"SHA-256：{digest}")
    print(f"校验文件：{archive.with_suffix(archive.suffix + '.sha256')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
