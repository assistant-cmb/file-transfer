from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .codec import decode_bytes, encode_bytes
from .errors import FileTransferError
from .format import safe_output_name, unique_path


def _read(path: Path) -> bytes:
    if not path.is_file():
        raise FileTransferError("INPUT_NOT_FOUND", f"输入文件不存在：{path}")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise FileTransferError("IO_ERROR", f"无法读取输入文件：{exc}") from exc


def _write(path: Path, data: bytes) -> Path:
    path = unique_path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    except OSError as exc:
        raise FileTransferError("IO_ERROR", f"无法写入输出文件：{exc}") from exc
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m file_transfer", description="File Transfer PNG v1.0")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("encode", "decode", "inspect"):
        item = sub.add_parser(command)
        item.add_argument("input")
        if command != "inspect":
            item.add_argument("-o", "--output")
        item.add_argument("--json", action="store_true")
    serve = sub.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=0)
    serve.add_argument("--no-browser", action="store_true")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "serve":
            from .server import serve
            serve(args.host, args.port, not args.no_browser)
            return 0
        input_path = Path(args.input)
        raw = _read(input_path)
        if args.command == "encode":
            png, metadata = encode_bytes(raw, input_path.name)
            output = Path(args.output) if args.output else input_path.with_name(f"{input_path.name}.png")
            output = _write(output, png)
            result = {"ok": True, "operation": "encode", "output": str(output.resolve()), **metadata}
        else:
            decoded = decode_bytes(raw)
            if args.command == "inspect":
                result = {"ok": True, "operation": "inspect", **decoded.metadata()}
            else:
                if args.output:
                    requested = Path(args.output)
                    output = requested / safe_output_name(decoded.filename) if requested.is_dir() else requested
                else:
                    output = input_path.parent / safe_output_name(decoded.filename)
                output = _write(output, decoded.data)
                result = {"ok": True, "operation": "decode", "output": str(output.resolve()), **decoded.metadata()}
        print(json.dumps(result, ensure_ascii=False) if args.json else _human(result))
        return 0
    except FileTransferError as exc:
        value = exc.as_dict()
        print(json.dumps(value, ensure_ascii=False) if getattr(args, "json", False) else f"错误 [{exc.code}]：{exc.message}", file=sys.stderr)
        return 2
    except Exception as exc:
        value = {"ok": False, "code": "INTERNAL_ERROR", "message": str(exc)}
        print(json.dumps(value, ensure_ascii=False) if getattr(args, "json", False) else f"错误 [INTERNAL_ERROR]：{exc}", file=sys.stderr)
        return 3


def _human(result: dict) -> str:
    if result["operation"] == "inspect":
        return f"有效的 File Transfer PNG：{result['filename']}，{result['fileLength']} 字节，SHA-256 {result['sha256']}"
    return f"{result['operation']} 完成：{result['output']}"


if __name__ == "__main__":
    raise SystemExit(main())
