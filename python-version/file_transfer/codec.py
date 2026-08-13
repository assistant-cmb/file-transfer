from __future__ import annotations

from .errors import FileTransferError
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


def encode_v2_bytes(data: bytes, filename: str) -> tuple[bytes, dict[str, object]]:
    try:
        from .v2_image import encode_v2_jpeg
    except ModuleNotFoundError as exc:
        if exc.name == "PIL":
            raise FileTransferError("MISSING_DEPENDENCY", "JPEG v2 需要 Pillow；请先运行 setup 安装依赖") from exc
        raise

    return encode_v2_jpeg(data, filename)


def decode_v2_bytes(image: bytes):
    try:
        from .v2_image import decode_v2_image
    except ModuleNotFoundError as exc:
        if exc.name == "PIL":
            raise FileTransferError("MISSING_DEPENDENCY", "JPEG v2 需要 Pillow；请先运行 setup 安装依赖") from exc
        raise

    return decode_v2_image(image)


def inspect_v2_bytes(image: bytes) -> dict[str, object]:
    return decode_v2_bytes(image).metadata()
