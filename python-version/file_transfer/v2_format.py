"""Binary format for the JPEG-resilient File Transfer v2 profile."""

from __future__ import annotations

import hashlib
import hmac
import struct
import zlib
from dataclasses import dataclass

from .errors import FileTransferError
from .format import normalize_archive_name
from .rs_codec import (
    CODEWORD_BYTES,
    DATA_BYTES,
    ReedSolomonError,
    decode_interleaved,
    encode_interleaved,
)


MAGIC = b"F2JR"
VERSION = 2
PROFILE = 1
MODULE_PIXELS = 4
QUIET_MODULES = 8
MANIFEST_BYTES = 88
MANIFEST_COPIES = 3
MANIFEST_STREAM_BYTES = MANIFEST_BYTES * MANIFEST_COPIES
MAX_ORIGINAL_BYTES = 100 * 1024
MAX_FILENAME_BYTES = 1024


def _fail(code: str, message: str) -> None:
    raise FileTransferError(code, message)


@dataclass(frozen=True)
class V2Manifest:
    core_modules: int
    grid_modules: int
    original_length: int
    filename_length: int
    body_length: int
    encoded_length: int
    body_sha256: bytes
    body_crc32: int
    data_bits: int
    codewords: int

    def to_bytes(self) -> bytes:
        if not 0 <= self.core_modules <= 0xFFFF:
            raise ValueError("core module count does not fit u16")
        if self.grid_modules != self.core_modules + 2 * QUIET_MODULES:
            raise ValueError("grid module count is inconsistent")
        values = (
            self.original_length,
            self.filename_length,
            self.body_length,
            self.encoded_length,
            self.body_crc32,
            self.data_bits,
            self.codewords,
        )
        if any(value < 0 or value > 0xFFFFFFFF for value in values):
            raise ValueError("manifest integer does not fit u32")
        if len(self.body_sha256) != 32:
            raise ValueError("manifest SHA-256 must contain 32 bytes")
        output = bytearray(MANIFEST_BYTES)
        output[0:4] = MAGIC
        output[4] = VERSION
        output[5] = PROFILE
        output[6] = MODULE_PIXELS
        output[7] = QUIET_MODULES
        struct.pack_into(">HHIIII", output, 8, self.core_modules, self.grid_modules,
                         self.original_length, self.filename_length,
                         self.body_length, self.encoded_length)
        output[28:60] = self.body_sha256
        struct.pack_into(">III", output, 60, self.body_crc32,
                         self.data_bits, self.codewords)
        # Bytes 72..83 are frozen zero-reserved bytes.
        struct.pack_into(">I", output, 84, zlib.crc32(output[:84]) & 0xFFFFFFFF)
        return bytes(output)

    @classmethod
    def from_bytes(cls, raw: bytes) -> "V2Manifest":
        if len(raw) != MANIFEST_BYTES:
            _fail("V2_INVALID_MANIFEST", "v2 manifest 长度无效")
        if raw[:4] != MAGIC:
            _fail("NOT_FILE_TRANSFER", "不是 File Transfer v2 图片")
        if raw[4] != VERSION or raw[5] != PROFILE:
            _fail("UNSUPPORTED_VERSION", f"不支持 v2 profile {raw[4]}.{raw[5]}")
        if raw[6] != MODULE_PIXELS or raw[7] != QUIET_MODULES:
            _fail("V2_UNSUPPORTED_PROFILE", "v2 模块或 quiet zone 参数不受支持")
        if any(raw[72:84]):
            _fail("V2_INVALID_MANIFEST", "v2 manifest 保留字段非零")
        expected_crc = struct.unpack_from(">I", raw, 84)[0]
        actual_crc = zlib.crc32(raw[:84]) & 0xFFFFFFFF
        if expected_crc != actual_crc:
            _fail("V2_MANIFEST_CHECKSUM_MISMATCH", "v2 manifest CRC-32 校验失败")
        core_modules, grid_modules = struct.unpack_from(">HH", raw, 8)
        original_length, filename_length, body_length, encoded_length = struct.unpack_from(
            ">IIII", raw, 12
        )
        body_crc32, data_bits, codewords = struct.unpack_from(">III", raw, 60)
        if core_modules < 8 or grid_modules != core_modules + 2 * QUIET_MODULES:
            _fail("V2_INVALID_MANIFEST", "v2 网格尺寸无效")
        if original_length > MAX_ORIGINAL_BYTES:
            _fail("LIMIT_EXCEEDED", "v2 原文件超过 100 KiB 限制")
        if not 1 <= filename_length <= MAX_FILENAME_BYTES:
            _fail("V2_INVALID_MANIFEST", "v2 文件名长度无效")
        if body_length != original_length + filename_length:
            _fail("V2_INVALID_MANIFEST", "v2 body 长度字段不一致")
        expected_codewords = (body_length + DATA_BYTES - 1) // DATA_BYTES
        if codewords != expected_codewords:
            _fail("V2_INVALID_MANIFEST", "v2 RS codeword 数量无效")
        if encoded_length != codewords * CODEWORD_BYTES:
            _fail("V2_INVALID_MANIFEST", "v2 RS 编码长度无效")
        if data_bits != (MANIFEST_STREAM_BYTES + encoded_length) * 8:
            _fail("V2_INVALID_MANIFEST", "v2 dataBits 字段无效")
        return cls(
            core_modules=core_modules,
            grid_modules=grid_modules,
            original_length=original_length,
            filename_length=filename_length,
            body_length=body_length,
            encoded_length=encoded_length,
            body_sha256=bytes(raw[28:60]),
            body_crc32=body_crc32,
            data_bits=data_bits,
            codewords=codewords,
        )


@dataclass(frozen=True)
class V2EncodedBody:
    filename: str
    body: bytes
    encoded: bytes
    codewords: int
    body_sha256: bytes
    body_crc32: int
    original_length: int
    filename_length: int


@dataclass(frozen=True)
class V2DecodedFile:
    filename: str
    data: bytes
    file_length: int
    sha256: str
    manifest: V2Manifest

    def metadata(self) -> dict[str, object]:
        return {
            "filename": self.filename,
            "fileLength": self.file_length,
            "sha256": self.sha256,
            "version": "2.0",
            "coreModules": self.manifest.core_modules,
            "gridModules": self.manifest.grid_modules,
            "codewords": self.manifest.codewords,
        }


def prepare_body(data: bytes, filename: str) -> V2EncodedBody:
    if len(data) > MAX_ORIGINAL_BYTES:
        _fail("LIMIT_EXCEEDED", "v2 原文件超过 100 KiB 限制")
    normalized, filename_bytes = normalize_archive_name(filename)
    if len(filename_bytes) > MAX_FILENAME_BYTES:
        _fail("INVALID_FILENAME", "v2 UTF-8 文件名超过 1024 字节")
    body = filename_bytes + bytes(data)
    encoded, codewords = encode_interleaved(body)
    return V2EncodedBody(
        filename=normalized,
        body=body,
        encoded=encoded,
        codewords=codewords,
        body_sha256=hashlib.sha256(body).digest(),
        body_crc32=zlib.crc32(body) & 0xFFFFFFFF,
        original_length=len(data),
        filename_length=len(filename_bytes),
    )


def make_manifest(prepared: V2EncodedBody, core_modules: int) -> V2Manifest:
    return V2Manifest(
        core_modules=core_modules,
        grid_modules=core_modules + 2 * QUIET_MODULES,
        original_length=prepared.original_length,
        filename_length=prepared.filename_length,
        body_length=len(prepared.body),
        encoded_length=len(prepared.encoded),
        body_sha256=prepared.body_sha256,
        body_crc32=prepared.body_crc32,
        data_bits=(MANIFEST_STREAM_BYTES + len(prepared.encoded)) * 8,
        codewords=prepared.codewords,
    )


def repeated_manifest_bytes(manifest: V2Manifest) -> bytes:
    raw = manifest.to_bytes()
    return raw * MANIFEST_COPIES


def recover_manifest(raw: bytes) -> V2Manifest:
    """Recover three manifest copies using bitwise 2-of-3 majority voting."""

    if len(raw) != MANIFEST_STREAM_BYTES:
        _fail("V2_INVALID_MANIFEST", "v2 manifest 副本区域长度无效")
    first = raw[0:MANIFEST_BYTES]
    second = raw[MANIFEST_BYTES : 2 * MANIFEST_BYTES]
    third = raw[2 * MANIFEST_BYTES : 3 * MANIFEST_BYTES]
    voted = bytes(
        (a & b) | (a & c) | (b & c)
        for a, b, c in zip(first, second, third)
    )
    try:
        return V2Manifest.from_bytes(voted)
    except FileTransferError as majority_error:
        # A whole-copy burst can defeat byte-wise majority even while one copy
        # remains pristine. Accept exactly one unambiguous, CRC-valid value.
        valid: dict[bytes, V2Manifest] = {}
        for copy in (first, second, third):
            try:
                valid[copy] = V2Manifest.from_bytes(copy)
            except FileTransferError:
                pass
        if len(valid) == 1:
            return next(iter(valid.values()))
        raise majority_error


def decode_body(manifest: V2Manifest, encoded: bytes) -> V2DecodedFile:
    if len(encoded) != manifest.encoded_length:
        _fail("V2_TRUNCATED_DATA", "v2 RS 数据长度不足")
    try:
        body = decode_interleaved(encoded, manifest.body_length, manifest.codewords)
    except (ReedSolomonError, ValueError) as exc:
        _fail("V2_RS_UNCORRECTABLE", f"v2 Reed-Solomon 无法纠正：{exc}")
    if zlib.crc32(body) & 0xFFFFFFFF != manifest.body_crc32:
        _fail("V2_BODY_CHECKSUM_MISMATCH", "v2 body CRC-32 校验失败")
    digest = hashlib.sha256(body).digest()
    if not hmac.compare_digest(digest, manifest.body_sha256):
        _fail("V2_BODY_CHECKSUM_MISMATCH", "v2 body SHA-256 校验失败")
    filename_raw = body[: manifest.filename_length]
    payload = body[manifest.filename_length :]
    try:
        filename = filename_raw.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise FileTransferError("INVALID_FILENAME", "v2 文件名不是有效 UTF-8") from exc
    filename, normalized = normalize_archive_name(filename)
    if normalized != filename_raw:
        _fail("INVALID_FILENAME", "v2 文件名不是 NFC 规范形式")
    if len(payload) != manifest.original_length:
        _fail("V2_INVALID_MANIFEST", "v2 原文件长度字段不一致")
    return V2DecodedFile(
        filename=filename,
        data=payload,
        file_length=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
        manifest=manifest,
    )


__all__ = [
    "MAGIC",
    "VERSION",
    "PROFILE",
    "MODULE_PIXELS",
    "QUIET_MODULES",
    "MANIFEST_BYTES",
    "MANIFEST_COPIES",
    "MANIFEST_STREAM_BYTES",
    "MAX_ORIGINAL_BYTES",
    "V2Manifest",
    "V2EncodedBody",
    "V2DecodedFile",
    "prepare_body",
    "make_manifest",
    "repeated_manifest_bytes",
    "recover_manifest",
    "decode_body",
]
