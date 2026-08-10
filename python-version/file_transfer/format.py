from __future__ import annotations

import hashlib
import math
import os
import re
import struct
import unicodedata
import zlib
from dataclasses import dataclass

from .errors import FileTransferError

MAGIC = b"FTRN"
VERSION_MAJOR = 1
VERSION_MINOR = 0
FIXED_HEADER_SIZE = 60
MAX_FILENAME_BYTES = 1024
MAX_FILE_SIZE = 100 * 1024 * 1024
MAX_HEADER_SIZE = 1024 * 1024


@dataclass(frozen=True)
class DecodedFile:
    filename: str
    data: bytes
    file_length: int
    sha256: str
    version_major: int
    version_minor: int

    def metadata(self) -> dict[str, object]:
        return {
            "filename": self.filename,
            "fileLength": self.file_length,
            "sha256": self.sha256,
            "version": f"{self.version_major}.{self.version_minor}",
        }


def _error(code: str, message: str) -> FileTransferError:
    return FileTransferError(code, message)


def normalize_archive_name(value: str) -> tuple[str, bytes]:
    parts = re.split(r"[\\/]", value)
    name = unicodedata.normalize("NFC", parts[-1] if parts else "")
    if not name or name in {".", ".."} or name.startswith("\ufeff"):
        raise _error("INVALID_FILENAME", "文件名为空或不安全")
    for char in name:
        if char in "/\\" or char == "\x00" or unicodedata.category(char) == "Cc" or ord(char) == 0x7F:
            raise _error("INVALID_FILENAME", "文件名包含不允许的字符")
    encoded = name.encode("utf-8", "strict")
    if not 1 <= len(encoded) <= MAX_FILENAME_BYTES:
        raise _error("INVALID_FILENAME", "UTF-8 文件名长度必须为 1–1024 字节")
    return name, encoded


def safe_output_name(name: str) -> str:
    name, _ = normalize_archive_name(name)
    if os.name == "nt":
        name = re.sub(r'[<>:"/\\|?*]', "_", name).rstrip(" .")
        stem = name.split(".", 1)[0].upper()
        reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
        if stem in reserved:
            name = f"_{name}"
    return name or "recovered_file"


def unique_path(path):
    if not path.exists():
        return path
    suffixes = "".join(path.suffixes)
    base = path.name[:-len(suffixes)] if suffixes else path.name
    for number in range(1, 10000):
        candidate = path.with_name(f"{base} ({number}){suffixes}")
        if not candidate.exists():
            return candidate
    raise _error("OUTPUT_EXISTS", "无法找到可用的输出文件名")


def build_stream(data: bytes, filename: str, max_file_size: int = MAX_FILE_SIZE) -> tuple[int, bytes, dict[str, object]]:
    if len(data) > max_file_size:
        raise _error("LIMIT_EXCEEDED", f"文件超过 {max_file_size} 字节限制")
    normalized, filename_bytes = normalize_archive_name(filename)
    header_length = FIXED_HEADER_SIZE + len(filename_bytes)
    digest = hashlib.sha256(data).digest()
    prefix = b"".join((
        MAGIC,
        bytes((VERSION_MAJOR, VERSION_MINOR)),
        struct.pack(">H", 0),
        struct.pack(">I", header_length),
        struct.pack(">Q", len(data)),
        struct.pack(">I", len(filename_bytes)),
        digest,
    ))
    header_crc = zlib.crc32(prefix + filename_bytes) & 0xFFFFFFFF
    header = prefix + struct.pack(">I", header_crc) + filename_bytes
    total_length = len(header) + len(data)
    pixels = (total_length + 2) // 3
    side = math.isqrt(pixels)
    if side * side < pixels:
        side += 1
    if side > 0x7FFFFFFF:
        raise _error("LIMIT_EXCEEDED", "计算得到的 PNG 尺寸超过格式限制")
    padding = side * side * 3 - total_length
    stream = header + data + bytes(padding)
    metadata = {
        "filename": normalized,
        "fileLength": len(data),
        "sha256": digest.hex(),
        "version": "1.0",
        "width": side,
        "height": side,
        "paddingLength": padding,
    }
    return side, stream, metadata


def parse_stream(rgb: bytes, width: int, height: int, max_file_size: int = MAX_FILE_SIZE) -> DecodedFile:
    if width != height or width <= 0 or len(rgb) != width * height * 3 or len(rgb) < FIXED_HEADER_SIZE:
        raise _error("INVALID_DIMENSIONS", "图片尺寸无效或不足以容纳固定头部")
    if rgb[:4] != MAGIC:
        raise _error("NOT_FILE_TRANSFER", "不是 File Transfer 生成的图片")

    major, minor = rgb[4], rgb[5]
    flags = struct.unpack(">H", rgb[6:8])[0]
    header_length = struct.unpack(">I", rgb[8:12])[0]
    file_length = struct.unpack(">Q", rgb[12:20])[0]
    filename_length = struct.unpack(">I", rgb[20:24])[0]

    if file_length > max_file_size:
        raise _error("LIMIT_EXCEEDED", f"图片声明的文件超过 {max_file_size} 字节限制")
    if major != VERSION_MAJOR:
        raise _error("UNSUPPORTED_VERSION", f"不支持格式版本 {major}.{minor}")
    if flags != 0:
        raise _error("UNSUPPORTED_FLAGS", f"不支持格式标志 0x{flags:04x}")
    if not 1 <= filename_length <= MAX_FILENAME_BYTES:
        raise _error("INVALID_HEADER", "文件名长度字段无效")
    minimum_header = FIXED_HEADER_SIZE + filename_length
    if header_length < minimum_header or header_length > len(rgb) or header_length > MAX_HEADER_SIZE:
        raise _error("INVALID_HEADER", "头部长度字段无效")
    if minor == 0 and header_length != minimum_header:
        raise _error("INVALID_HEADER", "v1.0 不允许扩展头部")
    if file_length > len(rgb) - header_length:
        raise _error("INVALID_HEADER", "文件长度超过图片容量")

    expected_crc = struct.unpack(">I", rgb[56:60])[0]
    actual_crc = zlib.crc32(rgb[:56] + rgb[60:header_length]) & 0xFFFFFFFF
    if expected_crc != actual_crc:
        raise _error("HEADER_CHECKSUM_MISMATCH", "头部 CRC-32 校验失败")

    filename_raw = rgb[60:60 + filename_length]
    try:
        filename = filename_raw.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise _error("INVALID_FILENAME", "文件名不是有效 UTF-8") from exc
    if unicodedata.normalize("NFC", filename) != filename:
        raise _error("INVALID_FILENAME", "文件名不是 NFC 规范形式")
    filename, _ = normalize_archive_name(filename)

    total = header_length + file_length
    pixels = (total + 2) // 3
    expected_side = math.isqrt(pixels)
    if expected_side * expected_side < pixels:
        expected_side += 1
    if width != expected_side:
        raise _error("CAPACITY_MISMATCH", "图片尺寸与声明内容不匹配")
    payload = rgb[header_length:total]
    if any(rgb[total:]):
        raise _error("NONZERO_PADDING", "图片补零区域包含非零数据")
    expected_digest = rgb[24:56]
    actual_digest = hashlib.sha256(payload).digest()
    if actual_digest != expected_digest:
        raise _error("PAYLOAD_CHECKSUM_MISMATCH", "文件 SHA-256 校验失败")
    return DecodedFile(filename, payload, file_length, actual_digest.hex(), major, minor)
