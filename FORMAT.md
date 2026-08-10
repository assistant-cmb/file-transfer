# File Transfer PNG Format Specification

## 1. Status

- Format name: File Transfer PNG
- Magic: `FTRN`
- Frozen version: **1.0**
- Specification status: **FROZEN**
- Frozen date: 2026-08-10

This document is the normative interoperability contract for the Python and Node.js implementations. The keywords **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are to be interpreted as requirement levels.

Version 1.0 is frozen. Implementations MUST NOT change field offsets, byte order, checksum calculation, filename encoding, pixel mapping, padding, or validation behavior while continuing to emit version 1.0. An incompatible change requires a new major version. A backward-compatible extension requires a minor-version change and must follow section 12.

## 2. Scope

The format stores one arbitrary file inside the RGB samples of a lossless PNG image. It preserves:

- the original base filename;
- the original byte length;
- the exact file bytes;
- a SHA-256 digest of the file bytes;
- a CRC-32 checksum protecting the header metadata;
- the format version.

The format provides integrity checking, not encryption, secrecy, authenticity, compression, steganographic concealment, or error correction. Anyone can extract or modify the data. A party that modifies data can also recompute the checksums.

## 3. Numeric and text conventions

- All multibyte integers are unsigned and encoded in **big-endian** byte order.
- Byte offsets are zero-based and the end offset in a range is inclusive.
- `u8`, `u16`, `u32`, and `u64` mean unsigned integers of the stated width.
- Text is encoded as strict UTF-8 without a byte-order mark.
- Text normalization is Unicode NFC.
- Hash hex strings shown in this document use lowercase only for presentation; the stored hashes are raw bytes.
- Calculations MUST use integer arithmetic. In particular, image-side calculation MUST NOT depend on floating-point `sqrt` for large inputs.
- A Node.js implementation MUST parse `u64` values as `BigInt` until it has enforced its configured size limits; it MUST NOT first coerce an arbitrary `u64` to `Number`.

## 4. PNG container requirements

### 4.1 Canonical encoder output

An encoder emitting v1.0 MUST create a PNG with:

- the standard 8-byte PNG signature;
- bit depth 8;
- color type 2 (truecolor RGB);
- no alpha channel;
- a square image;
- no interlacing;
- width and height calculated by section 8;
- lossless PNG compression.

PNG filter choice, DEFLATE compression level, IDAT chunk boundaries, timestamps, and optional ancillary chunks are not canonical. Consequently, two conforming encoders are not required to produce byte-identical PNG files. They are required to produce the same decoded RGB logical byte stream.

Encoders SHOULD omit unnecessary metadata chunks and MUST NOT store required recovery metadata only in ancillary chunks or in the PNG filename.

### 4.2 Decoder input

A decoder MUST support canonical v1.0 RGB PNG output.

A decoder MAY additionally accept an 8-bit truecolor RGBA PNG only when every alpha sample is `255`. If it does, it MUST discard alpha and process RGB exactly as specified below. It MUST reject an RGBA image containing any other alpha value.

A decoder MUST reject grayscale, indexed-color, sub-8-bit, and 16-bit inputs as unsupported pixel formats. A decoder MAY support an interlaced RGB/RGBA input if its PNG library reconstructs the exact samples, but encoders MUST remain non-interlaced.

Ancillary PNG chunks do not participate in File Transfer validation and MUST NOT override information stored in the RGB stream.

## 5. Logical byte stream

After the PNG is decoded, visit pixels in row-major order: left to right, then top to bottom. Append the red, green, and blue byte from each pixel:

```text
pixel(0,0).R, pixel(0,0).G, pixel(0,0).B,
pixel(1,0).R, pixel(1,0).G, pixel(1,0).B,
...
```

This produces the logical byte stream:

```text
header || file_payload || zero_padding
```

The first three logical bytes therefore occupy the RGB channels of the first pixel. Alpha, when accepted under section 4.2, never enters this stream.

## 6. v1.0 header layout

The fixed header is 60 bytes. It is followed immediately by the UTF-8 filename and then by zero or more version-extension bytes. A canonical v1.0 encoder emits no extension bytes.

| Offset | Size | Type | Field | v1.0 rule |
| ---: | ---: | --- | --- | --- |
| 0–3 | 4 | bytes | `magic` | ASCII `FTRN`, hex `46 54 52 4e` |
| 4 | 1 | u8 | `version_major` | `1` |
| 5 | 1 | u8 | `version_minor` | `0` for v1.0 encoder output |
| 6–7 | 2 | u16 | `flags` | `0` |
| 8–11 | 4 | u32 | `header_length` | `60 + filename_length` for v1.0 encoder output |
| 12–19 | 8 | u64 | `file_length` | Exact number of payload bytes; zero is valid |
| 20–23 | 4 | u32 | `filename_length` | UTF-8 filename length in bytes, `1..1024` |
| 24–55 | 32 | bytes | `payload_sha256` | Raw SHA-256 of the exact file payload |
| 56–59 | 4 | u32 | `header_crc32` | CRC-32 defined in section 7 |
| 60–`60+n-1` | `n` | bytes | `filename` | Strict UTF-8 NFC filename, where `n = filename_length` |
| `60+n`–`header_length-1` | variable | bytes | `extensions` | Empty in canonical v1.0 output |

The file payload begins at logical byte offset `header_length`.

### 6.1 Flags

All flag bits are reserved in v1.0. A v1.0 encoder MUST write `0`. A decoder MUST reject a stream when `flags` contains any bit it does not understand. This prevents a decoder from silently ignoring a required future transformation.

### 6.2 Header length

For canonical version 1.0:

```text
header_length = 60 + filename_length
```

A same-major future minor version MAY append extension bytes after the filename and increase `header_length`. It MUST NOT move or redefine the v1 fixed fields or filename.

The decoder MUST validate all of the following before allocating payload-sized memory:

```text
filename_length >= 1
filename_length <= 1024
header_length >= 60 + filename_length
header_length <= RGB stream capacity
file_length <= RGB stream capacity - header_length
```

For an image declaring exactly version 1.0, the decoder MUST additionally require `header_length == 60 + filename_length`.

## 7. Integrity fields

### 7.1 Payload SHA-256

`payload_sha256` is the 32-byte SHA-256 digest of the original file bytes only:

```text
payload_sha256 = SHA256(file_payload)
```

The digest of an empty payload is therefore:

```text
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
```

A decoder MUST compute the digest of the extracted `file_length` bytes and compare all 32 bytes. A mismatch is a payload-integrity failure.

### 7.2 Header CRC-32

`header_crc32` uses CRC-32/ISO-HDLC, the algorithm exposed by Python `zlib.crc32` and common Node.js CRC-32 libraries. The check value for ASCII `123456789` is `cbf43926`.

Calculate the checksum over the entire declared header except for the four checksum bytes themselves:

```text
crc_input = header[0:56] || header[60:header_length]
header_crc32 = CRC32(crc_input) & 0xffffffff
```

Slice end indexes in the pseudocode above are exclusive. For canonical v1.0, `header[60:header_length]` is exactly the filename. For a future minor version it also includes extension bytes.

The checksum stored at bytes 56–59 is big-endian. A decoder MUST verify it before trusting the decoded filename for output-path construction.

## 8. Image-size and padding algorithm

Let:

- `H = header_length`;
- `S = file_length`;
- `N = H + S`, the number of non-padding logical bytes.

Calculate:

```text
pixel_count = ceil(N / 3) = (N + 2) // 3
side = smallest integer d such that d * d >= pixel_count
width = side
height = side
capacity = side * side * 3
padding_length = capacity - N
```

Because the v1 header is nonempty, `pixel_count` and `side` are always at least 1.

The encoder MUST append exactly `padding_length` bytes of value `00`. The decoder MUST:

1. recompute `side` after it has safely read `header_length` and `file_length`;
2. require the actual image width and height to equal that `side`;
3. require every logical byte after `header_length + file_length` to be zero.

A non-square image, an image with additional rows or columns, insufficient capacity, or nonzero padding is invalid even if the payload hash matches.

PNG dimensions are limited to `1..2^31-1` by the PNG specification. An encoder MUST reject an input whose computed side exceeds `2^31-1`. Implementations MAY enforce a much smaller product limit, but that is a product/runtime limit rather than a format change.

The initial product limit is 100 MiB per original file unless configured otherwise. Both versions SHOULD apply the same default and report a `LIMIT_EXCEEDED` error before excessive allocation.

## 9. Filename rules

### 9.1 Encoding

The stored filename represents a base filename, never a path. Before encoding, the implementation MUST:

1. remove all path components;
2. treat both `/` and `\` as separators for safety;
3. normalize the remaining name to Unicode NFC;
4. encode it as strict UTF-8;
5. verify the encoded length is `1..1024` bytes.

The stored filename MUST NOT:

- be empty, `.` or `..`;
- contain `/`, `\`, U+0000, other Unicode `Cc` control characters, or U+007F;
- contain invalid UTF-8 or a UTF-8 byte-order mark.

If the source name cannot meet these rules, the encoder MUST fail with `INVALID_FILENAME`; it MUST NOT silently store a path.

### 9.2 Decoding and filesystem output

The decoder MUST validate the header CRC, decode filename bytes as strict UTF-8, require NFC, and apply the archival filename rules above before displaying or using the name.

Some valid archival names are not valid on every target filesystem. When creating a default output file, implementations MUST apply the same platform-safe policy:

- replace characters prohibited by the target platform with `_`;
- on Windows, protect reserved device names such as `CON`, `PRN`, `AUX`, `NUL`, `COM1`–`COM9`, and `LPT1`–`LPT9`, case-insensitively;
- remove or replace trailing spaces and dots where the target platform prohibits them;
- if sanitization produces an empty name, use `recovered_file`;
- never overwrite an existing file by default; append ` (1)`, ` (2)`, and so on before the final extension.

Sanitization affects only the local output path. `inspect` and UI metadata MUST continue to show the archived filename. When the caller provides an explicit output-file path, that caller-selected base name MAY be used, but normal safe-path and no-overwrite rules still apply.

## 10. Encoding procedure

A conforming encoder MUST perform these logical steps:

1. Validate and normalize the base filename under section 9.
2. Determine the exact `file_length` without truncation.
3. Enforce the configured product limit and PNG dimension limit.
4. Compute SHA-256 over the original file bytes.
5. Build bytes 0–55 of the header with major `1`, minor `0`, flags `0`, and the exact lengths.
6. Compute `header_crc32` over bytes 0–55 followed by the filename bytes.
7. Build `header || file_payload`.
8. Calculate the square image dimensions under section 8.
9. Append zero padding.
10. Map each consecutive group of three logical bytes to RGB in row-major order.
11. Save a canonical PNG under section 4.1.

The default output filename SHOULD be `<archived_filename>.png`.

An implementation MAY stream hashing and file reads, but the resulting logical bytes MUST be identical to this procedure.

## 11. Decoding procedure and error order

To keep Python and Node.js behavior aligned, a decoder MUST validate in the following broad order. It MAY combine checks that do not alter the externally visible error category.

1. Verify the input is a structurally valid PNG: `INVALID_PNG`.
2. Verify the supported pixel representation: `UNSUPPORTED_PIXEL_FORMAT`.
3. Verify the image is square and has enough RGB capacity for the 60-byte fixed header: `INVALID_DIMENSIONS`.
4. Read and verify `magic`: `NOT_FILE_TRANSFER`.
5. Read the fixed header fields and enforce implementation limits before large allocation: `INVALID_HEADER` or `LIMIT_EXCEEDED`.
6. Verify major/minor compatibility and flags: `UNSUPPORTED_VERSION` or `UNSUPPORTED_FLAGS`.
7. Validate header/filename lengths against image capacity: `INVALID_HEADER`.
8. Verify header CRC-32: `HEADER_CHECKSUM_MISMATCH`.
9. Decode and validate the archived filename: `INVALID_FILENAME`.
10. Recompute the required side and require exact dimensions/capacity: `CAPACITY_MISMATCH`.
11. Extract exactly `file_length` payload bytes.
12. Require all remaining RGB stream bytes to be zero: `NONZERO_PADDING`.
13. Verify payload SHA-256: `PAYLOAD_CHECKSUM_MISMATCH`.
14. Only after all checks succeed, expose or write the recovered file.

The implementation MUST NOT report success or leave a final output file when any validation fails. If streaming requires a temporary output, it MUST be deleted on failure.

## 12. Versioning and compatibility

### 12.1 Major version

Changing any existing field meaning, offset, byte order, pixel mapping, required checksum, or padding rule is incompatible and requires a new major version. A decoder that does not support the declared major version MUST return `UNSUPPORTED_VERSION`.

### 12.2 Minor version

A future version `1.x` MUST retain the v1 fixed 60-byte header and filename location. It MAY append extension bytes after the filename, increase `header_length`, and define new flags.

An older major-1 decoder:

- MUST reject any unknown required flag with `UNSUPPORTED_FLAGS`;
- MUST verify header CRC across unknown extension bytes;
- MAY skip extension bytes when no unknown required flag is set;
- MUST locate the payload using `header_length`, not `60 + filename_length`.

A v1.0 encoder always writes version `1.0`, flags `0`, and no extensions.

### 12.3 Legacy formats

The reference `0xAF` two-pixel format and the earlier Python format that requires an external size are not part of this specification. A future legacy importer, if added, MUST be explicitly separated from v1 decoding and MUST NOT emit a stream labeled as v1 unless it re-encodes the recovered file using this specification.

## 13. Stable error codes

Both implementations MUST expose these symbolic codes in CLI JSON and local API errors. Human-readable Chinese messages MAY include more detail but should remain behaviorally consistent.

| Code | Meaning |
| --- | --- |
| `INVALID_PNG` | Input is not a structurally valid PNG |
| `UNSUPPORTED_PIXEL_FORMAT` | PNG sample depth or color type is unsupported |
| `INVALID_DIMENSIONS` | Initial dimensions are invalid or fixed header cannot fit |
| `NOT_FILE_TRANSFER` | RGB stream does not begin with `FTRN` |
| `UNSUPPORTED_VERSION` | Major version is unsupported or declared version rules cannot be honored |
| `UNSUPPORTED_FLAGS` | Header contains an unknown required flag |
| `INVALID_HEADER` | Header fields, lengths, or ranges are invalid |
| `HEADER_CHECKSUM_MISMATCH` | Header CRC-32 does not match |
| `INVALID_FILENAME` | Archived filename is invalid |
| `CAPACITY_MISMATCH` | Image dimensions do not exactly match declared content |
| `NONZERO_PADDING` | One or more padding bytes are nonzero |
| `PAYLOAD_CHECKSUM_MISMATCH` | Recovered payload SHA-256 does not match |
| `LIMIT_EXCEEDED` | Input exceeds the configured implementation limit |
| `INPUT_NOT_FOUND` | Requested input path does not exist or is not a regular file |
| `OUTPUT_EXISTS` | Safe no-overwrite policy prevented output creation |
| `IO_ERROR` | A local read, write, temporary-file, or permission operation failed |
| `INTERNAL_ERROR` | Unexpected implementation failure |

## 14. Fixed interoperability test vectors

These vectors freeze the logical format. `stream_hex` is the complete decoded RGB byte stream, including zero padding. It is not the byte representation of a PNG file. Implementations MUST generate this stream for the given input and MUST successfully decode it.

### Vector 1: empty file

```text
filename: empty.bin
filename_utf8_hex: 656d7074792e62696e
payload_hex: <empty>
file_length: 0
header_length: 69
payload_sha256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
header_crc32: 559498bb
width: 5
height: 5
padding_length: 6
header_hex: 4654524e0100000000000045000000000000000000000009e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855559498bb656d7074792e62696e
stream_hex: 4654524e0100000000000045000000000000000000000009e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855559498bb656d7074792e62696e000000000000
```

### Vector 2: binary boundary bytes

```text
filename: a.bin
filename_utf8_hex: 612e62696e
payload_hex: 00010203ff
file_length: 5
header_length: 65
payload_sha256: ff5d8507b6a72bee2debce2c0054798deaccdc5d8a1b945b6280ce8aa9cba52e
header_crc32: d9a73e20
width: 5
height: 5
padding_length: 5
header_hex: 4654524e0100000000000041000000000000000500000005ff5d8507b6a72bee2debce2c0054798deaccdc5d8a1b945b6280ce8aa9cba52ed9a73e20612e62696e
stream_hex: 4654524e0100000000000041000000000000000500000005ff5d8507b6a72bee2debce2c0054798deaccdc5d8a1b945b6280ce8aa9cba52ed9a73e20612e62696e00010203ff0000000000
```

### Vector 3: UTF-8 filename

The payload is ASCII `hello` followed by LF (`0a`).

```text
filename: 测试.txt
filename_utf8_hex: e6b58be8af952e747874
payload_hex: 68656c6c6f0a
file_length: 6
header_length: 70
payload_sha256: 5891b5b522d5df086d0ff0b110fbd9d21bb4fc7163af34d08286a2e846f6be03
header_crc32: 9e3588b5
width: 6
height: 6
padding_length: 32
header_hex: 4654524e010000000000004600000000000000060000000a5891b5b522d5df086d0ff0b110fbd9d21bb4fc7163af34d08286a2e846f6be039e3588b5e6b58be8af952e747874
stream_hex: 4654524e010000000000004600000000000000060000000a5891b5b522d5df086d0ff0b110fbd9d21bb4fc7163af34d08286a2e846f6be039e3588b5e6b58be8af952e74787468656c6c6f0a0000000000000000000000000000000000000000000000000000000000000000
```

## 15. Required conformance tests

Before either implementation is considered compatible, it MUST pass:

1. encode each vector and match every declared metadata value and `stream_hex`;
2. decode each vector from an RGB PNG and recover the exact filename and payload;
3. Python encode → Node.js inspect/decode for every vector;
4. Node.js encode → Python inspect/decode for every vector;
5. empty, 1-byte, 2-byte, and 3-byte payload round trips;
6. rejection after changing one protected header byte;
7. rejection after changing one payload byte;
8. rejection after changing one padding byte to nonzero;
9. rejection for wrong magic, unsupported major version, nonzero unknown flags, unsafe filename, nonsquare dimensions, and excess dimensions;
10. safe handling of declared `u64` lengths above JavaScript's safe-integer range without allocation or precision loss.

## 16. Change control

This v1.0 specification can be changed editorially only when the change does not alter encoded bytes or decoder behavior. Any proposed behavioral change must include:

1. the proposed new version number;
2. updated compatibility rules;
3. new fixed test vectors;
4. Python and Node.js implementation changes;
5. bidirectional interoperability tests;
6. a migration note for existing v1.0 images.

Until those items are reviewed together, both implementations MUST continue to emit exactly version 1.0 as defined here.
