"""Reed-Solomon support for the File Transfer JPEG v2 profile.

The profile uses systematic RS(255, 179) over GF(256), primitive polynomial
0x11d, primitive element 2, and generator roots alpha**0 .. alpha**75.
Codeword bytes are polynomial coefficients in descending degree order.
"""

from __future__ import annotations


PRIMITIVE_POLYNOMIAL = 0x11D
GENERATOR_BASE = 0
DATA_BYTES = 179
PARITY_BYTES = 76
CODEWORD_BYTES = DATA_BYTES + PARITY_BYTES
MAX_CORRECTABLE_ERRORS = PARITY_BYTES // 2


class ReedSolomonError(ValueError):
    """Raised when a codeword cannot be corrected."""


_EXP = [0] * 512
_LOG = [0] * 256
_value = 1
for _index in range(255):
    _EXP[_index] = _value
    _LOG[_value] = _index
    _value <<= 1
    if _value & 0x100:
        _value ^= PRIMITIVE_POLYNOMIAL
for _index in range(255, 512):
    _EXP[_index] = _EXP[_index - 255]


def _mul(left: int, right: int) -> int:
    if left == 0 or right == 0:
        return 0
    return _EXP[_LOG[left] + _LOG[right]]


def _div(left: int, right: int) -> int:
    if right == 0:
        raise ZeroDivisionError("GF(256) division by zero")
    if left == 0:
        return 0
    return _EXP[(_LOG[left] - _LOG[right]) % 255]


def _pow_alpha(power: int) -> int:
    return _EXP[power % 255]


def _poly_mul(left: list[int], right: list[int]) -> list[int]:
    result = [0] * (len(left) + len(right) - 1)
    for i, a in enumerate(left):
        if a:
            for j, b in enumerate(right):
                if b:
                    result[i + j] ^= _mul(a, b)
    return result


def _poly_eval_desc(poly: bytes | bytearray | list[int], value: int) -> int:
    result = 0
    for coefficient in poly:
        result = _mul(result, value) ^ coefficient
    return result


def _poly_eval_asc(poly: list[int], value: int) -> int:
    result = 0
    for coefficient in reversed(poly):
        result = _mul(result, value) ^ coefficient
    return result


def _generator() -> list[int]:
    result = [1]
    for index in range(PARITY_BYTES):
        result = _poly_mul(result, [1, _pow_alpha(GENERATOR_BASE + index)])
    return result


_GENERATOR = _generator()


def encode_block(data: bytes) -> bytes:
    """Encode at most 179 bytes, padding the final data block with zeroes."""

    if len(data) > DATA_BYTES:
        raise ValueError(f"RS block exceeds {DATA_BYTES} data bytes")
    message = bytes(data).ljust(DATA_BYTES, b"\0")
    work = bytearray(message + bytes(PARITY_BYTES))
    for index in range(DATA_BYTES):
        coefficient = work[index]
        if coefficient:
            for generator_index in range(1, len(_GENERATOR)):
                work[index + generator_index] ^= _mul(
                    _GENERATOR[generator_index], coefficient
                )
    return message + bytes(work[-PARITY_BYTES:])


def _syndromes(codeword: bytes | bytearray) -> list[int]:
    return [
        _poly_eval_desc(codeword, _pow_alpha(GENERATOR_BASE + index))
        for index in range(PARITY_BYTES)
    ]


def _error_locator(syndromes: list[int]) -> list[int]:
    # Berlekamp-Massey. Coefficients are returned in ascending degree order.
    locator = [1] + [0] * PARITY_BYTES
    previous = [1] + [0] * PARITY_BYTES
    degree = 0
    shift = 1
    previous_discrepancy = 1

    for index in range(PARITY_BYTES):
        discrepancy = syndromes[index]
        for offset in range(1, degree + 1):
            discrepancy ^= _mul(locator[offset], syndromes[index - offset])
        if discrepancy == 0:
            shift += 1
            continue

        saved = locator.copy()
        scale = _div(discrepancy, previous_discrepancy)
        for coefficient_index in range(PARITY_BYTES + 1 - shift):
            if previous[coefficient_index]:
                locator[coefficient_index + shift] ^= _mul(
                    scale, previous[coefficient_index]
                )
        if 2 * degree <= index:
            degree = index + 1 - degree
            previous = saved
            previous_discrepancy = discrepancy
            shift = 1
        else:
            shift += 1

    if degree > MAX_CORRECTABLE_ERRORS:
        raise ReedSolomonError("too many RS symbol errors")
    return locator[: degree + 1]


def _find_error_positions(locator: list[int], length: int) -> list[int]:
    positions: list[int] = []
    for position in range(length):
        degree = length - 1 - position
        inverse_location = _pow_alpha(-degree)
        if _poly_eval_asc(locator, inverse_location) == 0:
            positions.append(position)
    if len(positions) != len(locator) - 1:
        raise ReedSolomonError("RS error locator roots are incomplete")
    return positions


def _solve_magnitudes(
    syndromes: list[int], positions: list[int], length: int
) -> list[int]:
    count = len(positions)
    if count == 0:
        return []
    # Solve the first `count` syndrome equations over GF(256). For root base
    # zero, S_i = sum(error_j * X_j**i).
    matrix: list[list[int]] = []
    locations = [_pow_alpha(length - 1 - position) for position in positions]
    for row_index in range(count):
        row = []
        for location in locations:
            row.append(1 if row_index == 0 else _EXP[(_LOG[location] * row_index) % 255])
        row.append(syndromes[row_index])
        matrix.append(row)

    for column in range(count):
        pivot = next(
            (row for row in range(column, count) if matrix[row][column]), None
        )
        if pivot is None:
            raise ReedSolomonError("singular RS magnitude system")
        matrix[column], matrix[pivot] = matrix[pivot], matrix[column]
        inverse = _div(1, matrix[column][column])
        for item in range(column, count + 1):
            matrix[column][item] = _mul(matrix[column][item], inverse)
        for row in range(count):
            if row == column or matrix[row][column] == 0:
                continue
            scale = matrix[row][column]
            for item in range(column, count + 1):
                matrix[row][item] ^= _mul(scale, matrix[column][item])
    return [matrix[index][count] for index in range(count)]


def decode_block(codeword: bytes) -> bytes:
    """Correct one 255-byte codeword and return its 179 data bytes."""

    if len(codeword) != CODEWORD_BYTES:
        raise ValueError(f"RS codeword must be {CODEWORD_BYTES} bytes")
    corrected = bytearray(codeword)
    syndromes = _syndromes(corrected)
    if not any(syndromes):
        return bytes(corrected[:DATA_BYTES])
    locator = _error_locator(syndromes)
    positions = _find_error_positions(locator, len(corrected))
    magnitudes = _solve_magnitudes(syndromes, positions, len(corrected))
    for position, magnitude in zip(positions, magnitudes):
        corrected[position] ^= magnitude
    if any(_syndromes(corrected)):
        raise ReedSolomonError("RS correction did not produce a valid codeword")
    return bytes(corrected[:DATA_BYTES])


def encode_interleaved(data: bytes) -> tuple[bytes, int]:
    """RS-encode data and interleave complete codewords by byte column."""

    if not data:
        return b"", 0
    blocks = [
        encode_block(data[offset : offset + DATA_BYTES])
        for offset in range(0, len(data), DATA_BYTES)
    ]
    output = bytearray(len(blocks) * CODEWORD_BYTES)
    cursor = 0
    for column in range(CODEWORD_BYTES):
        for block in blocks:
            output[cursor] = block[column]
            cursor += 1
    return bytes(output), len(blocks)


def decode_interleaved(data: bytes, body_length: int, codewords: int) -> bytes:
    """Undo column interleaving, correct each codeword, and trim padding."""

    if body_length < 0 or codewords < 0:
        raise ValueError("negative RS length")
    expected_codewords = (body_length + DATA_BYTES - 1) // DATA_BYTES
    if codewords != expected_codewords:
        raise ValueError("RS codeword count does not match body length")
    if len(data) != codewords * CODEWORD_BYTES:
        raise ValueError("interleaved RS length mismatch")
    if codewords == 0:
        return b""
    blocks = [bytearray(CODEWORD_BYTES) for _ in range(codewords)]
    cursor = 0
    for column in range(CODEWORD_BYTES):
        for block in blocks:
            block[column] = data[cursor]
            cursor += 1
    decoded = b"".join(decode_block(bytes(block)) for block in blocks)
    return decoded[:body_length]


__all__ = [
    "PRIMITIVE_POLYNOMIAL",
    "GENERATOR_BASE",
    "DATA_BYTES",
    "PARITY_BYTES",
    "CODEWORD_BYTES",
    "MAX_CORRECTABLE_ERRORS",
    "ReedSolomonError",
    "encode_block",
    "decode_block",
    "encode_interleaved",
    "decode_interleaved",
]
