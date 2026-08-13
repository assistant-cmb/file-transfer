# File Transfer JPEG v2 Format Specification

## 1. Status

- Format name: File Transfer JPEG v2
- Logical magic: `F2JR`
- Version byte: `2`
- Profile byte: `1`
- Specification status: **FROZEN**
- Frozen date: 2026-08-13

This document freezes the interoperable format emitted by the Python and
Node.js implementations. It is independent of the lossless PNG v1 format in
[`FORMAT.md`](./FORMAT.md). A v2 decoder must not interpret a v2 carrier as a
v1 RGB byte stream, and a v1 decoder is not expected to understand v2.

The keywords **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY**
describe interoperability requirements.

## 2. Scope and limits

Profile 1 turns one file into a high-contrast monochrome module grid, protects
its logical bytes with Reed-Solomon error correction, and stores that grid in a
grayscale JPEG. It is designed to survive ordinary JPEG recompression and
moderate proportional resizing. It is not designed to survive cropping,
perspective distortion, arbitrary rotation, drawing, filters, or severe
downscaling.

The profile preserves:

- the original safe base filename;
- the exact original file length and bytes;
- a CRC-32 and SHA-256 over the filename and file bytes;
- the format version and profile;
- all parameters required to recover the grid and Reed-Solomon stream.

The maximum original file length is **100 KiB (102,400 bytes)**. The UTF-8
filename is limited separately to 1–1024 bytes. This product limit is part of
profile 1 and not merely a UI recommendation.

The format provides integrity checking and error correction. It does not
provide encryption, secrecy, authenticity, compression, or steganographic
concealment.

## 3. Numeric, text, and checksum conventions

- All multibyte integers are unsigned and big-endian.
- Byte offsets are zero-based; ranges in tables include both endpoints.
- Text is strict UTF-8 in Unicode NFC form, without a byte-order mark.
- CRC-32 means CRC-32/ISO-HDLC, as exposed by Python `zlib.crc32`.
- SHA-256 fields contain 32 raw digest bytes, not hexadecimal text.
- A bitstream visits each byte from bit 7 to bit 0 (most significant bit first).

The archived filename follows the v1 base-filename rules: paths are removed,
both `/` and `\` are treated as separators, and empty names, `.`/`..`, control
characters, NUL, separators, non-NFC text, and invalid UTF-8 are rejected.

## 4. Logical body and Reed-Solomon coding

Let:

- `F` be the normalized UTF-8 filename bytes;
- `P` be the original file bytes;
- `body = F || P`;
- `body_length = len(F) + len(P)`.

Profile 1 uses systematic **RS(255,179)** over GF(256):

- primitive polynomial: `0x11d`;
- primitive element: `2`;
- generator base: `0`;
- generator roots: `alpha^0` through `alpha^75`;
- data bytes per codeword: `179`;
- parity bytes per codeword: `76`;
- codeword bytes: `255`;
- polynomial coefficients are stored in descending-degree order.

Split `body` into consecutive 179-byte blocks. The final block is padded on the
right with zero bytes to 179 bytes. Encode every padded block as its 179 data
bytes followed by 76 parity bytes. A codeword can correct at most 38 unknown
symbol errors; the format makes no stronger promise for a particular damage
pattern.

If there are `B = ceil(body_length / 179)` codewords, interleave them by byte
column:

```text
for column = 0..254:
    for block = 0..B-1:
        output(codeword[block][column])
```

Thus:

```text
encoded_length = B * 255
```

Column interleaving spreads a contiguous damaged region across codewords. A
canonical encoder MUST zero-pad the last data block. A decoder returns only the
first `body_length` decoded bytes and MAY additionally reject nonzero decoded
padding.

## 5. Manifest

The manifest is exactly 88 bytes:

| Offset | Size | Type | Field | Profile-1 rule |
| ---: | ---: | --- | --- | --- |
| 0–3 | 4 | bytes | `magic` | ASCII `F2JR` |
| 4 | 1 | u8 | `version` | `2` |
| 5 | 1 | u8 | `profile` | `1` |
| 6 | 1 | u8 | `module_pixels` | `4` |
| 7 | 1 | u8 | `quiet_modules` | `8` |
| 8–9 | 2 | u16 | `core_modules` | Core-grid side `G` |
| 10–11 | 2 | u16 | `grid_modules` | `G + 16` |
| 12–15 | 4 | u32 | `original_length` | `len(P)`, at most 102,400 |
| 16–19 | 4 | u32 | `filename_length` | `len(F)`, 1–1024 |
| 20–23 | 4 | u32 | `body_length` | `original_length + filename_length` |
| 24–27 | 4 | u32 | `encoded_length` | `codewords * 255` |
| 28–59 | 32 | bytes | `body_sha256` | `SHA256(body)` |
| 60–63 | 4 | u32 | `body_crc32` | `CRC32(body)` |
| 64–67 | 4 | u32 | `data_bits` | `(264 + encoded_length) * 8` |
| 68–71 | 4 | u32 | `codewords` | `ceil(body_length / 179)` |
| 72–83 | 12 | bytes | reserved | All zero |
| 84–87 | 4 | u32 | `manifest_crc32` | `CRC32(manifest[0:84])` |

The logical carrier stream is:

```text
manifest || manifest || manifest || interleaved_rs_bytes
```

The three manifest copies occupy 264 bytes and are not part of the
Reed-Solomon-coded body. Recover them using bitwise two-of-three voting for each
byte:

```text
voted = (copy1 & copy2) | (copy1 & copy3) | (copy2 & copy3)
```

The voted manifest is accepted only if all fields and its CRC are valid. If it
is invalid, a decoder MAY validate the three raw copies separately and accept
them only when the valid copies identify exactly one distinct manifest value.
Ambiguous valid values must be rejected.

Before allocating from manifest fields, a decoder MUST validate all fixed
values, limits, arithmetic relations, reserved zeros, capacity, and the
manifest CRC.

## 6. Module-grid sizing

Let `G = core_modules` and `I = G - 4`. The inner region has `I` columns.
Every tenth inner row is reserved as a synchronization row, so the exact data
capacity is:

```text
sync_rows(G)    = floor((G - 4) / 10)
capacity_bits(G) = (G - 4) * ((G - 4) - sync_rows(G))
```

The canonical encoder MUST choose the smallest integer `G >= 8` for which:

```text
capacity_bits(G) >= data_bits
```

The full grid includes an eight-module quiet zone on every side:

```text
grid_modules = G + 16
canonical_width = canonical_height = grid_modules * 4
```

Any unused data modules after the last stream bit are white.

For reference, using the short filename `payload.bin`:

| Original file | Canonical output |
| ---: | ---: |
| 1 KiB | 584 × 584 |
| 10 KiB | 1544 × 1544 |
| 25 KiB | 2376 × 2376 |
| 50 KiB | 3312 × 3312 |
| 75 KiB | 4032 × 4032 |
| 100 KiB | 4644 × 4644 |

The filename is part of the protected body, so a longer filename can increase
the dimensions. A 100 KiB payload with the maximum 1024-byte filename requires
4664 × 4664 pixels.

JPEG file size on disk is not the capacity of the carrier. It depends on JPEG
entropy coding, metadata, encoder implementation, and later platform
recompression. Capacity is determined only by the formula above.

## 7. Module layout

Coordinates below are module coordinates. `0` means white and `1` means black.
The full `grid_modules × grid_modules` matrix begins white.

### 7.1 Quiet zone

The outer eight modules on all four sides remain white. The core-grid origin is
therefore full-grid coordinate `(8, 8)`.

### 7.2 Core frame and timing tracks

Within the `G × G` core grid:

- row `0`, row `G-1`, column `0`, and column `G-1` are solid black;
- row `1`, row `G-2`, column `1`, and column `G-2` are timing tracks;
- along a timing track, coordinate `c` in `1..G-2` is black when `c` is even
  and white when `c` is odd.

### 7.3 Synchronization rows and data positions

The inner candidate region uses core coordinates:

```text
x = 2..G-3
y = 2..G-3
local_x = x - 2
local_y = y - 2
```

A row is a synchronization row when:

```text
(local_y + 1) mod 10 == 0
```

Its module at `local_x` is black when:

```text
(local_x + floor(local_y / 10)) mod 2 == 0
```

All other inner positions are data positions. Visit them in row-major order,
skipping synchronization rows, and write the logical carrier stream MSB-first.

## 8. JPEG rendering

A canonical encoder renders black modules as luma `0`, white modules as luma
`255`, and expands every module to a 4 × 4 pixel square using nearest-neighbor
sampling. It then emits an 8-bit grayscale JPEG with:

- quality `95`;
- no progressive scans;
- no required EXIF orientation or ICC profile.

JPEG container bytes are not canonical. Huffman tables, entropy optimization,
JFIF details, and encoder-library output may differ. Conformance is defined by
the manifest, logical stream, module raster, and successful recovery—not by a
byte-for-byte comparison of JPEG files.

Because profile 1 is grayscale, chroma subsampling does not carry information.
An implementation that temporarily represents the raster as RGB MUST keep the
three channels equal.

## 9. Decoding and integrity

A decoder performs these logical stages:

1. Decode the image to an 8-bit luma plane with bounded dimensions and memory.
2. Require a complete, approximately square image; cropping is unsupported.
3. Locate a plausible grid using the quiet zone, frame, timing tracks, and
   synchronization rows.
4. Calibrate or choose a black/white threshold and sample the module centers.
5. Recover and validate the repeated manifest.
6. Extract exactly `data_bits`, split off the manifest copies, and deinterleave
   the Reed-Solomon bytes.
7. Correct every codeword and trim the decoded body to `body_length`.
8. Verify `body_crc32` and `body_sha256` before exposing a filename or file.
9. Strictly decode and validate the filename, then return exactly
   `original_length` payload bytes.

The reference implementations search images whose decoded scale is roughly
2.8–5.2 pixels per module, covering moderate proportional resizing around the
canonical 4 pixels per module. Search thresholds, sampling kernels, contrast
heuristics, and acceptance scores are implementation details and may evolve
without changing the frozen binary format. Every implementation must decode
canonical output from both reference encoders; damaged-image acceptance may
vary near the correction boundary.

No decoder may report a successful recovery when CRC-32 or SHA-256 validation
fails. Reed-Solomon correction is not a substitute for the final digest.

## 10. Compatibility and changes

Profile 1 freezes the field offsets, byte order, checksums, RS parameters,
interleaving, manifest repetition, grid-size formula, module layout, bit order,
quiet zone, and canonical module scale. Changing any of those requires a new
profile or version.

Changes to JPEG-library versions, entropy coding, bounded search strategy, or
sampling heuristics do not require a new profile when canonical cross-runtime
interoperability remains intact.
