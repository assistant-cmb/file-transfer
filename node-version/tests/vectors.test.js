const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const { encodeBytes, decodeBytes } = require('../src/codec');
const { buildStream } = require('../src/format');
const { encodeRgbPng } = require('../src/png-codec');

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
