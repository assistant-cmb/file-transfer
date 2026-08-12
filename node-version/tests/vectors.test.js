const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const zlib = require('node:zlib');
const { encodeBytes, decodeBytes } = require('../src/codec');
const { buildStream } = require('../src/format');
const { encodeRgbPng } = require('../src/png-codec');
const { createZip } = require('../src/zip-archive');

const root = path.resolve(__dirname, '..', '..');
const vectors = JSON.parse(fs.readFileSync(path.join(root, 'shared', 'fixtures', 'vectors.json'), 'utf8'));

test('matches frozen logical streams', () => {
  for (const vector of vectors) {
    const result = buildStream(Buffer.from(vector.payloadHex, 'hex'), vector.name);
    assert.equal(result.side, vector.side, vector.name);
    assert.equal(result.stream.toString('hex'), vector.streamHex, vector.name);
  }
});

test('round trips canonical PNGs', () => {
  for (const vector of vectors) {
    const payload = Buffer.from(vector.payloadHex, 'hex');
    const encoded = encodeBytes(payload, vector.name);
    const decoded = decodeBytes(encoded.png);
    assert.equal(decoded.filename, vector.name);
    assert.deepEqual(decoded.data, payload);
    assert.equal(encoded.metadata.width, vector.side);
  }
});

test('round trips boundary lengths', () => {
  for (const length of [0, 1, 2, 3, 4, 255, 1024, 4097]) {
    const payload = Buffer.from(Array.from({ length }, (_, index) => index % 251));
    const encoded = encodeBytes(payload, `length-${length}.bin`);
    assert.deepEqual(decodeBytes(encoded.png).data, payload, String(length));
  }
});

test('detects payload and padding corruption', () => {
  const built = buildStream(Buffer.from('payload'), 'sample.bin');
  const headerLength = built.stream.readUInt32BE(8);
  const payloadCorrupt = Buffer.from(built.stream);
  payloadCorrupt[headerLength] ^= 1;
  assert.throws(() => decodeBytes(encodeRgbPng(built.side, built.side, payloadCorrupt)), { code: 'PAYLOAD_CHECKSUM_MISMATCH' });

  const paddingCorrupt = Buffer.from(built.stream);
  paddingCorrupt[paddingCorrupt.length - 1] = 1;
  assert.throws(() => decodeBytes(encodeRgbPng(built.side, built.side, paddingCorrupt)), { code: 'NONZERO_PADDING' });
});

test('creates a standard single-entry ZIP archive', () => {
  const png = encodeBytes(Buffer.from('zip payload'), 'archive.txt').png;
  const entryName = '压缩样例.txt.png';
  const archive = createZip(png, entryName);
  assert.equal(archive.readUInt32LE(0), 0x04034b50);
  assert.equal(archive.readUInt32LE(archive.length - 22), 0x06054b50);
  assert.equal(archive.readUInt16LE(6) & 0x0800, 0x0800);
  const compressedSize = archive.readUInt32LE(18);
  const nameLength = archive.readUInt16LE(26);
  const extraLength = archive.readUInt16LE(28);
  assert.equal(archive.subarray(30, 30 + nameLength).toString('utf8'), entryName);
  const compressed = archive.subarray(30 + nameLength + extraLength, 30 + nameLength + extraLength + compressedSize);
  assert.deepEqual(zlib.inflateRawSync(compressed), png);
});
