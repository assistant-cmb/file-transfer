'use strict';

// Shortened use of the conventional RS(255, 179) code over GF(2^8).
// Symbols are ordered from the highest to the lowest polynomial power.
const PRIMITIVE = 0x11d;
const FIELD_SIZE = 255;
const DATA_SYMBOLS = 179;
const PARITY_SYMBOLS = FIELD_SIZE - DATA_SYMBOLS;
const GENERATOR_BASE = 0;

const EXP = new Uint8Array(FIELD_SIZE * 2);
const LOG = new Int16Array(256);
LOG.fill(-1);
let value = 1;
for (let exponent = 0; exponent < FIELD_SIZE; exponent += 1) {
  EXP[exponent] = value;
  LOG[value] = exponent;
  value <<= 1;
  if (value & 0x100) value ^= PRIMITIVE;
}
for (let exponent = FIELD_SIZE; exponent < EXP.length; exponent += 1) EXP[exponent] = EXP[exponent - FIELD_SIZE];

function multiply(a, b) {
  if (a === 0 || b === 0) return 0;
  return EXP[LOG[a] + LOG[b]];
}

function divide(a, b) {
  if (b === 0) throw new RangeError('GF division by zero');
  if (a === 0) return 0;
  let exponent = LOG[a] - LOG[b];
  if (exponent < 0) exponent += FIELD_SIZE;
  return EXP[exponent];
}

function polynomialMultiply(left, right) {
  const output = new Uint8Array(left.length + right.length - 1);
  for (let i = 0; i < left.length; i += 1) {
    for (let j = 0; j < right.length; j += 1) output[i + j] ^= multiply(left[i], right[j]);
  }
  return output;
}

let generator = Uint8Array.of(1);
for (let index = 0; index < PARITY_SYMBOLS; index += 1) {
  generator = polynomialMultiply(generator, Uint8Array.of(1, EXP[GENERATOR_BASE + index]));
}

function syndromes(codeword) {
  const output = new Uint8Array(PARITY_SYMBOLS);
  for (let index = 0; index < PARITY_SYMBOLS; index += 1) {
    const point = EXP[GENERATOR_BASE + index];
    let result = 0;
    for (const symbol of codeword) result = multiply(result, point) ^ symbol;
    output[index] = result;
  }
  return output;
}

function encodeBlock(data) {
  if (!(data instanceof Uint8Array) || data.length !== DATA_SYMBOLS) throw new RangeError(`RS data block must contain ${DATA_SYMBOLS} symbols`);
  const work = new Uint8Array(FIELD_SIZE);
  work.set(data);
  for (let index = 0; index < DATA_SYMBOLS; index += 1) {
    const coefficient = work[index];
    if (coefficient === 0) continue;
    for (let term = 1; term < generator.length; term += 1) work[index + term] ^= multiply(generator[term], coefficient);
  }
  const output = new Uint8Array(FIELD_SIZE);
  output.set(data);
  output.set(work.subarray(DATA_SYMBOLS), DATA_SYMBOLS);
  return Buffer.from(output);
}

function evaluateAscending(polynomial, point) {
  let result = 0;
  for (let index = polynomial.length - 1; index >= 0; index -= 1) result = multiply(result, point) ^ polynomial[index];
  return result;
}

function berlekampMassey(sequence) {
  // Locator coefficients are stored in ascending power order.
  let locator = Uint8Array.of(1);
  let previous = Uint8Array.of(1);
  let degree = 0;
  let shift = 1;
  let previousDiscrepancy = 1;

  for (let n = 0; n < sequence.length; n += 1) {
    let discrepancy = sequence[n];
    for (let index = 1; index <= degree; index += 1) {
      if (index < locator.length) discrepancy ^= multiply(locator[index], sequence[n - index]);
    }
    if (discrepancy === 0) {
      shift += 1;
      continue;
    }

    const saved = locator.slice();
    const scale = divide(discrepancy, previousDiscrepancy);
    const needed = previous.length + shift;
    if (locator.length < needed) {
      const expanded = new Uint8Array(needed);
      expanded.set(locator);
      locator = expanded;
    }
    for (let index = 0; index < previous.length; index += 1) locator[index + shift] ^= multiply(scale, previous[index]);

    if (2 * degree <= n) {
      degree = n + 1 - degree;
      previous = saved;
      previousDiscrepancy = discrepancy;
      shift = 1;
    } else {
      shift += 1;
    }
  }
  return { locator, degree };
}

function solveMagnitudes(positions, sequence) {
  const count = positions.length;
  const matrix = Array.from({ length: count }, () => new Uint8Array(count + 1));
  for (let row = 0; row < count; row += 1) {
    for (let column = 0; column < count; column += 1) {
      const power = (FIELD_SIZE - 1 - positions[column]) * row;
      matrix[row][column] = row === 0 ? 1 : EXP[power % FIELD_SIZE];
    }
    matrix[row][count] = sequence[row];
  }

  for (let column = 0; column < count; column += 1) {
    let pivot = column;
    while (pivot < count && matrix[pivot][column] === 0) pivot += 1;
    if (pivot === count) throw new Error('RS error magnitude matrix is singular');
    if (pivot !== column) [matrix[pivot], matrix[column]] = [matrix[column], matrix[pivot]];
    const inverse = divide(1, matrix[column][column]);
    for (let item = column; item <= count; item += 1) matrix[column][item] = multiply(matrix[column][item], inverse);
    for (let row = 0; row < count; row += 1) {
      if (row === column || matrix[row][column] === 0) continue;
      const scale = matrix[row][column];
      for (let item = column; item <= count; item += 1) matrix[row][item] ^= multiply(scale, matrix[column][item]);
    }
  }
  return Uint8Array.from(matrix, (row) => row[count]);
}

function decodeBlock(input) {
  if (!(input instanceof Uint8Array) || input.length !== FIELD_SIZE) throw new RangeError(`RS codeword must contain ${FIELD_SIZE} symbols`);
  const output = Uint8Array.from(input);
  let check = syndromes(output);
  if (check.every((symbol) => symbol === 0)) return { data: Buffer.from(output.subarray(0, DATA_SYMBOLS)), correctedSymbols: 0 };

  const { locator, degree } = berlekampMassey(check);
  if (degree < 1 || degree > PARITY_SYMBOLS / 2) throw new Error('RS codeword has too many errors');
  const positions = [];
  for (let position = 0; position < FIELD_SIZE; position += 1) {
    const symbolPower = FIELD_SIZE - 1 - position;
    const inversePoint = EXP[(FIELD_SIZE - symbolPower) % FIELD_SIZE];
    if (evaluateAscending(locator, inversePoint) === 0) positions.push(position);
  }
  if (positions.length !== degree) throw new Error('RS error locations could not be resolved');
  const magnitudes = solveMagnitudes(positions, check);
  for (let index = 0; index < positions.length; index += 1) output[positions[index]] ^= magnitudes[index];
  check = syndromes(output);
  if (!check.every((symbol) => symbol === 0)) throw new Error('RS correction failed');
  return { data: Buffer.from(output.subarray(0, DATA_SYMBOLS)), correctedSymbols: positions.length };
}

function encode(data) {
  if (!Buffer.isBuffer(data)) data = Buffer.from(data);
  const blockCount = Math.ceil(data.length / DATA_SYMBOLS);
  if (blockCount === 0) return { interleaved: Buffer.alloc(0), blockCount: 0 };
  const codewords = [];
  for (let block = 0; block < blockCount; block += 1) {
    const message = Buffer.alloc(DATA_SYMBOLS);
    data.copy(message, 0, block * DATA_SYMBOLS, Math.min(data.length, (block + 1) * DATA_SYMBOLS));
    codewords.push(encodeBlock(message));
  }
  const interleaved = Buffer.alloc(blockCount * FIELD_SIZE);
  let offset = 0;
  for (let column = 0; column < FIELD_SIZE; column += 1) {
    for (let block = 0; block < blockCount; block += 1) interleaved[offset++] = codewords[block][column];
  }
  return { interleaved, blockCount };
}

function decode(interleaved, blockCount, dataLength) {
  if (!Buffer.isBuffer(interleaved)) interleaved = Buffer.from(interleaved);
  if (!Number.isSafeInteger(blockCount) || blockCount < 0 || interleaved.length !== blockCount * FIELD_SIZE) throw new RangeError('Invalid interleaved RS length');
  if (!Number.isSafeInteger(dataLength) || dataLength < 0 || dataLength > blockCount * DATA_SYMBOLS) throw new RangeError('Invalid decoded RS length');
  const decoded = Buffer.alloc(blockCount * DATA_SYMBOLS);
  let correctedSymbols = 0;
  for (let block = 0; block < blockCount; block += 1) {
    const codeword = Buffer.alloc(FIELD_SIZE);
    for (let column = 0; column < FIELD_SIZE; column += 1) codeword[column] = interleaved[column * blockCount + block];
    const result = decodeBlock(codeword);
    result.data.copy(decoded, block * DATA_SYMBOLS);
    correctedSymbols += result.correctedSymbols;
  }
  for (const value of decoded.subarray(dataLength)) if (value !== 0) throw new Error('RS padding is not zero');
  return { data: decoded.subarray(0, dataLength), correctedSymbols };
}

module.exports = {
  PRIMITIVE,
  FIELD_SIZE,
  DATA_SYMBOLS,
  PARITY_SYMBOLS,
  GENERATOR_BASE,
  encodeBlock,
  decodeBlock,
  encode,
  decode,
};
