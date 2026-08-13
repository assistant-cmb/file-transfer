"""4x4 monochrome module image codec for File Transfer JPEG v2 profile 1."""

from __future__ import annotations

import io
import hashlib
import math
import statistics
from collections.abc import Iterator

from PIL import Image, UnidentifiedImageError

from .errors import FileTransferError
from .format import normalize_archive_name
from .v2_format import (
    MANIFEST_STREAM_BYTES,
    MODULE_PIXELS,
    QUIET_MODULES,
    V2DecodedFile,
    V2Manifest,
    decode_body,
    make_manifest,
    prepare_body,
    recover_manifest,
    repeated_manifest_bytes,
)


MIN_SAMPLED_MODULE_PIXELS = 2.8
MAX_SAMPLED_MODULE_PIXELS = 5.2
MAX_IMAGE_SIDE = 8192
MIN_CONTRAST = 36.0


def _fail(code: str, message: str) -> None:
    raise FileTransferError(code, message)


def _is_sync_row(core_y: int) -> bool:
    """Every tenth candidate data row, counted from core y=2, is sync."""

    return core_y >= 2 and (core_y - 2) % 10 == 9


def data_module_count(core_modules: int) -> int:
    inner = core_modules - 4
    if inner <= 0:
        return 0
    sync_rows = inner // 10
    return inner * (inner - sync_rows)


def minimum_core_modules(data_bits: int) -> int:
    if data_bits < 0:
        raise ValueError("negative bit count")
    # Binary search the exact monotonic capacity function.
    low, high = 8, 8
    while data_module_count(high) < data_bits:
        high *= 2
        if high + 2 * QUIET_MODULES > 0xFFFF:
            _fail("LIMIT_EXCEEDED", "v2 模块网格超过 u16 限制")
    while low < high:
        middle = (low + high) // 2
        if data_module_count(middle) >= data_bits:
            high = middle
        else:
            low = middle + 1
    return low


def _data_coordinates(core_modules: int) -> Iterator[tuple[int, int]]:
    for y in range(2, core_modules - 2):
        if _is_sync_row(y):
            continue
        for x in range(2, core_modules - 2):
            yield x, y


def _bytes_to_bits(data: bytes) -> Iterator[int]:
    for value in data:
        for shift in range(7, -1, -1):
            yield (value >> shift) & 1


def _bits_to_bytes(bits: list[int]) -> bytes:
    if len(bits) % 8:
        raise ValueError("bit count is not byte-aligned")
    output = bytearray(len(bits) // 8)
    for index, bit in enumerate(bits):
        output[index // 8] |= (bit & 1) << (7 - index % 8)
    return bytes(output)


def _set_core_patterns(modules: list[bytearray], core_modules: int) -> None:
    q = QUIET_MODULES
    g = core_modules
    # Outer core frame. True/1 is rendered black.
    for coordinate in range(g):
        modules[q][q + coordinate] = 1
        modules[q + g - 1][q + coordinate] = 1
        modules[q + coordinate][q] = 1
        modules[q + coordinate][q + g - 1] = 1

    # Four inner timing tracks. Even module coordinates are black.
    for coordinate in range(1, g - 1):
        value = 1 if coordinate % 2 == 0 else 0
        modules[q + 1][q + coordinate] = value
        modules[q + g - 2][q + coordinate] = value
        modules[q + coordinate][q + 1] = value
        modules[q + coordinate][q + g - 2] = value

    # Horizontal sync rows use alternating phase so a one-row slip is visible.
    for y in range(2, g - 2):
        if not _is_sync_row(y):
            continue
        phase = (y - 2) // 10
        for x in range(2, g - 2):
            modules[q + y][q + x] = 1 if (x + phase) % 2 == 0 else 0


def build_module_grid(data: bytes, filename: str) -> tuple[list[bytearray], V2Manifest]:
    prepared = prepare_body(data, filename)
    data_bits = (MANIFEST_STREAM_BYTES + len(prepared.encoded)) * 8
    core_modules = minimum_core_modules(data_bits)
    manifest = make_manifest(prepared, core_modules)
    bitstream = repeated_manifest_bytes(manifest) + prepared.encoded
    grid_modules = manifest.grid_modules
    modules = [bytearray(grid_modules) for _ in range(grid_modules)]
    _set_core_patterns(modules, core_modules)
    coordinates = _data_coordinates(core_modules)
    for bit, (x, y) in zip(_bytes_to_bits(bitstream), coordinates):
        modules[QUIET_MODULES + y][QUIET_MODULES + x] = bit
    return modules, manifest


def encode_v2_jpeg(
    data: bytes,
    filename: str,
    *,
    quality: int = 95,
) -> tuple[bytes, dict[str, object]]:
    """Encode a file as a profile-1 grayscale JPEG and return bytes/metadata."""

    if quality != 95:
        # The profile freezes canonical encoder output at q95. Decode remains
        # independent of this encoder-side check.
        raise ValueError("v2 profile 1 JPEG quality is fixed at 95")
    modules, manifest = build_module_grid(data, filename)
    normalized_filename, _ = normalize_archive_name(filename)
    grid_modules = manifest.grid_modules
    module_image = Image.new("L", (grid_modules, grid_modules), 255)
    module_image.putdata(
        [0 if modules[y][x] else 255 for y in range(grid_modules) for x in range(grid_modules)]
    )
    side = grid_modules * MODULE_PIXELS
    image = module_image.resize((side, side), resample=Image.Resampling.NEAREST)
    output = io.BytesIO()
    image.save(output, "JPEG", quality=95, optimize=False, progressive=False)
    metadata = {
        "filename": normalized_filename,
        "fileLength": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "version": "2.0",
        "width": side,
        "height": side,
        "coreModules": manifest.core_modules,
        "gridModules": manifest.grid_modules,
        "modulePixels": MODULE_PIXELS,
        "codewords": manifest.codewords,
        "encodedLength": manifest.encoded_length,
    }
    return output.getvalue(), metadata


class _Sampler:
    def __init__(self, image: Image.Image, grid_modules: int):
        self.image = image
        self.pixels = image.load()
        self.grid_modules = grid_modules
        self.scale_x = image.width / grid_modules
        self.scale_y = image.height / grid_modules

    def value(self, module_x: int, module_y: int) -> float:
        # Average a compact cross around the module center. It stays away from
        # boundaries after ordinary bilinear resizing but damps JPEG ringing.
        center_x = (module_x + 0.5) * self.scale_x
        center_y = (module_y + 0.5) * self.scale_y
        offset_x = self.scale_x * 0.16
        offset_y = self.scale_y * 0.16
        points = (
            (center_x, center_y),
            (center_x - offset_x, center_y),
            (center_x + offset_x, center_y),
            (center_x, center_y - offset_y),
            (center_x, center_y + offset_y),
        )
        total = 0
        for x, y in points:
            px = min(self.image.width - 1, max(0, int(x)))
            py = min(self.image.height - 1, max(0, int(y)))
            total += self.pixels[px, py]
        return total / len(points)


def _distributed(limit: int, count: int = 24) -> list[int]:
    if limit <= count:
        return list(range(limit))
    return sorted({round(index * (limit - 1) / (count - 1)) for index in range(count)})


def _calibrate(sampler: _Sampler, core_modules: int) -> tuple[float, float]:
    q = QUIET_MODULES
    g = core_modules
    coordinates = _distributed(g)
    black_values: list[float] = []
    for coordinate in coordinates:
        black_values.extend(
            (
                sampler.value(q + coordinate, q),
                sampler.value(q + coordinate, q + g - 1),
                sampler.value(q, q + coordinate),
                sampler.value(q + g - 1, q + coordinate),
            )
        )
    white_values: list[float] = []
    quiet_coordinates = _distributed(q, 8)
    for coordinate in quiet_coordinates:
        white_values.extend(
            (
                sampler.value(coordinate, coordinate),
                sampler.value(sampler.grid_modules - 1 - coordinate, coordinate),
                sampler.value(coordinate, sampler.grid_modules - 1 - coordinate),
                sampler.value(
                    sampler.grid_modules - 1 - coordinate,
                    sampler.grid_modules - 1 - coordinate,
                ),
            )
        )
    black = statistics.median(black_values)
    white = statistics.median(white_values)
    if white - black < MIN_CONTRAST:
        raise ValueError("insufficient black/white contrast")
    return (black + white) / 2.0, white - black


def _geometry_score(
    sampler: _Sampler, core_modules: int, threshold: float
) -> float:
    q = QUIET_MODULES
    g = core_modules
    correct = 0
    total = 0
    for coordinate in _distributed(max(0, g - 2), 32):
        x = coordinate + 1
        expected_black = x % 2 == 0
        for module_x, module_y in (
            (q + x, q + 1),
            (q + x, q + g - 2),
            (q + 1, q + x),
            (q + g - 2, q + x),
        ):
            actual_black = sampler.value(module_x, module_y) < threshold
            correct += actual_black == expected_black
            total += 1
    return correct / total if total else 0.0


def _read_bits(
    sampler: _Sampler,
    core_modules: int,
    threshold: float,
    bit_count: int,
) -> list[int]:
    if bit_count > data_module_count(core_modules):
        _fail("V2_TRUNCATED_DATA", "v2 数据位超过模块容量")
    result: list[int] = []
    q = QUIET_MODULES
    for x, y in _data_coordinates(core_modules):
        result.append(1 if sampler.value(q + x, q + y) < threshold else 0)
        if len(result) == bit_count:
            break
    return result


def _candidate_grid_modules(image: Image.Image) -> list[int]:
    average_side = (image.width + image.height) / 2.0
    minimum = max(24, math.ceil(average_side / MAX_SAMPLED_MODULE_PIXELS))
    maximum = min(0xFFFF, math.floor(average_side / MIN_SAMPLED_MODULE_PIXELS))
    candidates = list(range(minimum, maximum + 1))
    # Canonical 4 px modules are most likely, but every allowed scale is tried.
    candidates.sort(key=lambda grid: abs(average_side / grid - MODULE_PIXELS))
    return candidates


def _find_manifest(image: Image.Image) -> tuple[V2Manifest, _Sampler, float]:
    manifest_bits = MANIFEST_STREAM_BYTES * 8
    for grid_modules in _candidate_grid_modules(image):
        core_modules = grid_modules - 2 * QUIET_MODULES
        if core_modules < 8 or data_module_count(core_modules) < manifest_bits:
            continue
        sampler = _Sampler(image, grid_modules)
        try:
            threshold, _contrast = _calibrate(sampler, core_modules)
        except ValueError:
            continue
        if _geometry_score(sampler, core_modules, threshold) < 0.82:
            continue
        raw = _bits_to_bytes(
            _read_bits(sampler, core_modules, threshold, manifest_bits)
        )
        try:
            manifest = recover_manifest(raw)
        except FileTransferError:
            continue
        if (
            manifest.grid_modules != grid_modules
            or manifest.core_modules != core_modules
            or manifest.data_bits > data_module_count(core_modules)
        ):
            continue
        return manifest, sampler, threshold
    _fail("V2_GEOMETRY_NOT_FOUND", "无法定位有效的 File Transfer v2 模块网格")


def decode_v2_image(image_bytes: bytes) -> V2DecodedFile:
    """Decode a v2 JPEG, including an image resized to 2.8..5.2 px/module."""

    try:
        with Image.open(io.BytesIO(image_bytes)) as source:
            if source.width <= 0 or source.height <= 0:
                _fail("V2_INVALID_IMAGE", "图片尺寸无效")
            if max(source.width, source.height) > MAX_IMAGE_SIDE:
                _fail("LIMIT_EXCEEDED", "v2 图片尺寸超过解码限制")
            if abs(source.width - source.height) > max(2, round(max(source.size) * 0.01)):
                _fail("V2_INVALID_IMAGE", "v2 图片必须近似正方形")
            source.load()
            image = source.convert("L")
    except FileTransferError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise FileTransferError("V2_INVALID_IMAGE", "输入不是可解码图片") from exc

    manifest, sampler, threshold = _find_manifest(image)
    all_bits = _read_bits(
        sampler, manifest.core_modules, threshold, manifest.data_bits
    )
    stream = _bits_to_bytes(all_bits)
    # Re-run manifest voting on the final extraction to keep the data and its
    # declared lengths from exactly the same sampling pass.
    final_manifest = recover_manifest(stream[:MANIFEST_STREAM_BYTES])
    if final_manifest != manifest:
        _fail("V2_INVALID_MANIFEST", "v2 manifest 候选结果不一致")
    encoded = stream[
        MANIFEST_STREAM_BYTES : MANIFEST_STREAM_BYTES + manifest.encoded_length
    ]
    return decode_body(manifest, encoded)


def inspect_v2_image(image_bytes: bytes) -> dict[str, object]:
    return decode_v2_image(image_bytes).metadata()


# Short aliases are retained for direct library callers. Product entry points
# use the explicit v2 names so v1 and v2 dispatch remains obvious.
encode_jpeg = encode_v2_jpeg
decode_jpeg = decode_v2_image
inspect_jpeg = inspect_v2_image


__all__ = [
    "MIN_SAMPLED_MODULE_PIXELS",
    "MAX_SAMPLED_MODULE_PIXELS",
    "data_module_count",
    "minimum_core_modules",
    "build_module_grid",
    "encode_v2_jpeg",
    "decode_v2_image",
    "inspect_v2_image",
    "encode_jpeg",
    "decode_jpeg",
    "inspect_jpeg",
]
