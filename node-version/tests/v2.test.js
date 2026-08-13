'use strict';

const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const test = require('node:test');
const sharp = require('sharp');
const rs = require('../src/rs-codec');
const { buildV2Stream } = require('../src/v2-format');
const { encodeV2Jpeg, decodeV2Image } = require('../src/v2-image');

function deterministicBytes(length) {
  const output = Buffer.alloc(length);
  for (let index = 0; index < length; index += 1) output[index] = (index * 37 + Math.floor(index / 251) + 17) & 0xff;
  return output;
}

test('RS(255,179) corrects 38 symbol errors', () => {
  const data = deterministicBytes(rs.DATA_SYMBOLS);
  const damaged = rs.encodeBlock(data);
  for (let index = 0; index < 38; index += 1) damaged[(index * 47) % rs.FIELD_SIZE] ^= index * 19 + 1;
  const decoded = rs.decodeBlock(damaged);
  assert.equal(decoded.correctedSymbols, 38);
  assert.deepEqual(decoded.data, data);
});

test('v2 quality-95 JPEG round trips a 1 KiB payload', async () => {
  const payload = deterministicBytes(1024);
  const encoded = await encodeV2Jpeg(payload, '中文样例.zip');
  assert.equal(encoded.metadata.quality, 95);
  assert.equal(encoded.jpg.subarray(0, 2).toString('hex'), 'ffd8');
  const decoded = await decodeV2Image(encoded.jpg);
  assert.equal(decoded.filename, '中文样例.zip');
  assert.deepEqual(decoded.data, payload);
  assert.equal(decoded.sha256, crypto.createHash('sha256').update(payload).digest('hex'));
});

test('v2 survives proportional resize and JPEG re-encoding', async () => {
  const payload = deterministicBytes(1024);
  const encoded = await encodeV2Jpeg(payload, 'resized.bin');
  const side = Math.round(encoded.metadata.width * 0.82);
  const transferred = await sharp(encoded.jpg).resize(side, side).jpeg({ quality: 82 }).toBuffer();
  const decoded = await decodeV2Image(transferred);
  assert.deepEqual(decoded.data, payload);
  assert.ok(decoded.image.decodedModulePixelsX >= 2.8);
  assert.ok(decoded.image.decodedModulePixelsX <= 5.2);
});

test('v2 maximum payload uses the recommended 4644px square', () => {
  const built = buildV2Stream(Buffer.alloc(100 * 1024), 'maximum.zip');
  assert.equal(built.metadata.width, 4644);
  assert.equal(built.metadata.height, 4644);
  assert.equal(built.metadata.coreModules, 1145);
});

test('v2 grid selection is minimal at capacity discontinuities', () => {
  assert.equal(buildV2Stream(Buffer.alloc(1024), 'x.zip').metadata.coreModules, 130);
  assert.equal(buildV2Stream(Buffer.alloc(50 * 1024), 'x.zip').metadata.coreModules, 812);
});

test('v2 profile fixes JPEG quality at 95', async () => {
  await assert.rejects(encodeV2Jpeg(Buffer.alloc(1), 'quality.bin', { quality: 94 }), { code: 'INVALID_JPEG_QUALITY' });
});
