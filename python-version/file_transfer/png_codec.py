from __future__ import annotations

import struct
import zlib

from .errors import FileTransferError
from .format import FIXED_HEADER_SIZE, MAX_FILE_SIZE

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _error(code: str, message: str) -> FileTransferError:
    return FileTransferError(code, message)


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def encode_rgb_png(width: int, height: int, rgb: bytes) -> bytes:
    if width <= 0 or height <= 0 or len(rgb) != width * height * 3:
        raise _error("INVALID_DIMENSIONS", "RGB 数据长度与图片尺寸不匹配")
    stride = width * 3
    raw = b"".join(b"\x00" + rgb[row * stride:(row + 1) * stride] for row in range(height))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return PNG_SIGNATURE + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", zlib.compress(raw, 9)) + _chunk(b"IEND", b"")


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    return a if pa <= pb and pa <= pc else b if pb <= pc else c


def decode_png_to_rgb(png: bytes) -> tuple[int, int, bytes]:
    if not png.startswith(PNG_SIGNATURE):
        raise _error("INVALID_PNG", "输入不是有效 PNG")
    offset = len(PNG_SIGNATURE)
    ihdr = None
    idat = bytearray()
    seen_iend = False
    while offset < len(png):
        if offset + 12 > len(png):
            raise _error("INVALID_PNG", "PNG 数据被截断")
        length = struct.unpack(">I", png[offset:offset + 4])[0]
        kind = png[offset + 4:offset + 8]
        end = offset + 12 + length
        if end > len(png):
            raise _error("INVALID_PNG", "PNG chunk 长度无效")
        data = png[offset + 8:offset + 8 + length]
        expected_crc = struct.unpack(">I", png[offset + 8 + length:end])[0]
        if zlib.crc32(kind + data) & 0xFFFFFFFF != expected_crc:
            raise _error("INVALID_PNG", f"PNG {kind.decode('ascii', 'replace')} chunk CRC 错误")
        if kind == b"IHDR":
            if ihdr is not None or offset != len(PNG_SIGNATURE) or length != 13:
                raise _error("INVALID_PNG", "PNG IHDR 无效")
            ihdr = data
        elif kind == b"IDAT":
            if ihdr is None:
                raise _error("INVALID_PNG", "PNG IDAT 出现在 IHDR 之前")
            idat.extend(data)
        elif kind == b"IEND":
            if length != 0:
                raise _error("INVALID_PNG", "PNG IEND 无效")
            seen_iend = True
            break
        elif kind and 65 <= kind[0] <= 90:
            raise _error("INVALID_PNG", "PNG 包含不支持的关键 chunk")
        offset = end
    if ihdr is None or not idat or not seen_iend:
        raise _error("INVALID_PNG", "PNG 缺少必要 chunk")

    width, height, depth, color_type, compression, filter_method, interlace = struct.unpack(">IIBBBBB", ihdr)
    if width <= 0 or height <= 0:
        raise _error("INVALID_DIMENSIONS", "PNG 尺寸无效")
    if depth != 8 or color_type not in (2, 6) or compression != 0 or filter_method != 0 or interlace != 0:
        raise _error("UNSUPPORTED_PIXEL_FORMAT", "仅支持非交错 8 位 RGB/RGBA PNG")
    bpp = 3 if color_type == 2 else 4
    max_pixels = ((MAX_FILE_SIZE + FIXED_HEADER_SIZE + 1024 + 2) // 3 + 1)
    if width * height > max_pixels:
        raise _error("LIMIT_EXCEEDED", "PNG 解码尺寸超过限制")
    stride = width * bpp
    expected_raw = (stride + 1) * height
    try:
        decompressor = zlib.decompressobj()
        raw = decompressor.decompress(bytes(idat), expected_raw + 1)
    except zlib.error as exc:
        raise _error("INVALID_PNG", "PNG IDAT 解压失败") from exc
    if len(raw) != expected_raw or not decompressor.eof or decompressor.unconsumed_tail or decompressor.unused_data:
        raise _error("INVALID_PNG", "PNG 解压数据长度无效")

    rows = []
    previous = bytearray(stride)
    cursor = 0
    for _ in range(height):
        filter_type = raw[cursor]
        cursor += 1
        filtered = raw[cursor:cursor + stride]
        cursor += stride
        current = bytearray(stride)
        if filter_type > 4:
            raise _error("INVALID_PNG", "PNG 使用了未知过滤器")
        for index, value in enumerate(filtered):
            left = current[index - bpp] if index >= bpp else 0
            up = previous[index]
            upper_left = previous[index - bpp] if index >= bpp else 0
            if filter_type == 0:
                predictor = 0
            elif filter_type == 1:
                predictor = left
            elif filter_type == 2:
                predictor = up
            elif filter_type == 3:
                predictor = (left + up) // 2
            else:
                predictor = _paeth(left, up, upper_left)
            current[index] = (value + predictor) & 0xFF
        rows.append(current)
        previous = current

    if color_type == 2:
        rgb = b"".join(rows)
    else:
        rgb_data = bytearray(width * height * 3)
        target = 0
        for row in rows:
            for index in range(0, len(row), 4):
                if row[index + 3] != 255:
                    raise _error("UNSUPPORTED_PIXEL_FORMAT", "RGBA PNG 包含非不透明 alpha")
                rgb_data[target:target + 3] = row[index:index + 3]
                target += 3
        rgb = bytes(rgb_data)
    return width, height, rgb
