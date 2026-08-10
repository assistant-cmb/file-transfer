from __future__ import annotations

import json
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .codec import decode_bytes, encode_bytes
from .errors import FileTransferError
from .format import MAX_FILE_SIZE, safe_output_name

SHARED_DIR = Path(__file__).resolve().parents[2] / "shared"
MAX_REQUEST_SIZE = 140 * 1024 * 1024


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class Handler(BaseHTTPRequestHandler):
    server_version = "FileTransferPython/1.0"

    def log_message(self, fmt, *args):
        print(f"[{self.log_date_time_string()}] {fmt % args}")

    def _send(self, status: int, body: bytes, content_type: str, headers: dict[str, str] | None = None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, value: dict):
        self._send(status, json.dumps(value, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _read_body(self) -> bytes:
        try:
            length = int(self.headers.get("Content-Length", "-1"))
        except ValueError as exc:
            raise FileTransferError("INVALID_HEADER", "HTTP Content-Length 无效") from exc
        if length < 0 or length > MAX_REQUEST_SIZE:
            raise FileTransferError("LIMIT_EXCEEDED", "请求体大小超过限制")
        data = self.rfile.read(length)
        if len(data) != length:
            raise FileTransferError("IO_ERROR", "请求体读取不完整")
        return data

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/health":
            self._json(200, {"ok": True, "runtime": "Python", "format": "1.0"})
            return
        files = {"/": "index.html", "/index.html": "index.html", "/app.js": "app.js", "/styles.css": "styles.css"}
        name = files.get(path)
        if not name:
            self._json(404, {"ok": False, "code": "NOT_FOUND", "message": "资源不存在"})
            return
        body = (SHARED_DIR / name).read_bytes()
        content_type = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8"}[Path(name).suffix]
        self._send(200, body, content_type)

    def do_POST(self):
        try:
            parsed = urllib.parse.urlparse(self.path)
            body = self._read_body()
            if parsed.path == "/api/encode":
                if len(body) > MAX_FILE_SIZE:
                    raise FileTransferError("LIMIT_EXCEEDED", "文件超过 100 MiB 限制")
                filename = urllib.parse.parse_qs(parsed.query).get("filename", [""])[0]
                png, metadata = encode_bytes(body, filename)
                output_name = f"{safe_output_name(str(metadata['filename']))}.png"
                self._send(200, png, "image/png", {
                    "Content-Disposition": f"attachment; filename*=UTF-8''{urllib.parse.quote(output_name)}",
                    "X-Image-Dimensions": f"{metadata['width']}×{metadata['height']}",
                })
            elif parsed.path == "/api/decode":
                decoded = decode_bytes(body)
                self._send(200, decoded.data, "application/octet-stream", {
                    "Content-Disposition": f"attachment; filename*=UTF-8''{urllib.parse.quote(safe_output_name(decoded.filename))}",
                })
            elif parsed.path == "/api/inspect":
                decoded = decode_bytes(body)
                self._json(200, {"ok": True, **decoded.metadata()})
            else:
                self._json(404, {"ok": False, "code": "NOT_FOUND", "message": "接口不存在"})
        except FileTransferError as exc:
            self._json(400 if exc.code != "LIMIT_EXCEEDED" else 413, exc.as_dict())
        except Exception as exc:
            self._json(500, {"ok": False, "code": "INTERNAL_ERROR", "message": str(exc)})


def serve(host: str = "127.0.0.1", port: int = 0, open_browser: bool = True):
    server = Server((host, port), Handler)
    actual_port = server.server_address[1]
    url = f"http://{host}:{actual_port}/"
    print(f"File Transfer Python 已启动：{url}")
    print("按 Ctrl+C 退出。")
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n正在退出…")
    finally:
        server.server_close()
