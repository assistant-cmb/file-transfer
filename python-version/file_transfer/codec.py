from __future__ import annotations

from .format import DecodedFile, build_stream, parse_stream
from .png_codec import decode_png_to_rgb, encode_rgb_png


def encode_bytes(data: bytes, filename: str) -> tuple[bytes, dict[str, object]]:
    side, stream, metadata = build_stream(data, filename)
    return encode_rgb_png(side, side, stream), metadata


def decode_bytes(png: bytes) -> DecodedFile:
    width, height, rgb = decode_png_to_rgb(png)
    return parse_stream(rgb, width, height)


def inspect_bytes(png: bytes) -> dict[str, object]:
    decoded = decode_bytes(png)
    return decoded.metadata()
