'use strict';

const crypto = require('node:crypto');
const { crc32 } = require('./crc32');
const { FileTransferError } = require('./errors');
const { normalizeArchiveName } = require('./format');
const rs = require('./rs-codec');

const MAGIC = Buffer.from('F2JR', 'ascii');
const VERSION = 2;
const PROFILE = 1;
const MODULE_PIXELS = 4;
const QUIET_MODULES = 8;
const MANIFEST_SIZE = 88;
const MANIFEST_COPIES = 3;
const FRAME_RINGS = 2;
const SYNC_INTERVAL = 10;
const MAX_FILE_SIZE = 100 * 1024;

function fail(code, message) { throw new FileTransferError(code, message); }

function usableRow(localY) {
  return (localY + 1) % SYNC_INTERVAL !== 0;
}

function syncModuleIsBlack(localX, localY) {
  return ((localX + Math.floor(localY / SYNC_INTERVAL)) & 1) === 0;
}

function dataCapacityBits(coreModules) {
  const grid = coreModules - FRAME_RINGS * 2;
  if (grid <= 0) return 0;
  return grid * (grid - Math.floor(grid / SYNC_INTERVAL));
}

function chooseCoreModules(requiredBits) {
  if (!Number.isSafeInteger(requiredBits) || requiredBits < 0) fail('INVALID_HEADER', 'v2 数据位长度无效');
  let low = 1;
  let high = Math.max(1, Math.ceil(Math.sqrt(requiredBits * SYNC_INTERVAL / (SYNC_INTERVAL - 1))));
  while (high * (high - Math.floor(high / SYNC_INTERVAL)) < requiredBits) high *= 2;
  while (low < high) {
    const middle = Math.floor((low + high) / 2);
    if (middle * (middle - Math.floor(middle / SYNC_INTERVAL)) >= requiredBits) high = middle;
    else low = middle + 1;
  }
  const grid = low;
  const coreModules = grid + FRAME_RINGS * 2;
  if (coreModules > 0xffff) fail('LIMIT_EXCEEDED', 'v2 图片网格超过格式限制');
  return coreModules;
}

function forEachDataPosition(coreModules, limit, callback) {
  const grid = coreModules - FRAME_RINGS * 2;
  let index = 0;
  for (let localY = 0; localY < grid && index < limit; localY += 1) {
    if (!usableRow(localY)) continue;
    for (let localX = 0; localX < grid && index < limit; localX += 1) {
      callback(localX + FRAME_RINGS, localY + FRAME_RINGS, index);
      index += 1;
    }
  }
  return index;
}

function buildManifest(fields) {
  const manifest = Buffer.alloc(MANIFEST_SIZE);
  MAGIC.copy(manifest, 0);
  manifest[4] = VERSION;
  manifest[5] = PROFILE;
  manifest[6] = MODULE_PIXELS;
  manifest[7] = QUIET_MODULES;
  manifest.writeUInt16BE(fields.coreModules, 8);
  manifest.writeUInt16BE(fields.coreModules + QUIET_MODULES * 2, 10);
  manifest.writeUInt32BE(fields.originalLength, 12);
  manifest.writeUInt32BE(fields.filenameLength, 16);
  manifest.writeUInt32BE(fields.bodyLength, 20);
  manifest.writeUInt32BE(fields.encodedLength, 24);
  fields.sha256.copy(manifest, 28);
  manifest.writeUInt32BE(fields.crc32, 60);
  manifest.writeUInt32BE(fields.dataBits, 64);
  manifest.writeUInt32BE(fields.blockCount, 68);
  // Bytes 72..83 are reserved and remain zero.
  manifest.writeUInt32BE(crc32(manifest.subarray(0, 84)), 84);
  return manifest;
}

function parseManifest(input) {
  if (!Buffer.isBuffer(input)) input = Buffer.from(input);
  if (input.length !== MANIFEST_SIZE) fail('INVALID_V2_MANIFEST', 'v2 manifest 长度无效');
  if (!input.subarray(0, 4).equals(MAGIC)) fail('NOT_FILE_TRANSFER_V2', '不是 File Transfer JPEG v2 图片');
  if (input[4] !== VERSION || input[5] !== PROFILE) fail('UNSUPPORTED_VERSION', `不支持 v2 版本或配置 ${input[4]}/${input[5]}`);
  if (input[6] !== MODULE_PIXELS || input[7] !== QUIET_MODULES) fail('UNSUPPORTED_V2_PARAMETERS', '不支持该 v2 模块或静区参数');
  if (input.readUInt32BE(84) !== crc32(input.subarray(0, 84))) fail('V2_MANIFEST_CHECKSUM_MISMATCH', 'v2 manifest CRC-32 校验失败');
  for (const value of input.subarray(72, 84)) if (value !== 0) fail('UNSUPPORTED_V2_PARAMETERS', 'v2 manifest 保留字段非零');

  const coreModules = input.readUInt16BE(8);
  const grid = input.readUInt16BE(10);
  const originalLength = input.readUInt32BE(12);
  const filenameLength = input.readUInt32BE(16);
  const bodyLength = input.readUInt32BE(20);
  const encodedLength = input.readUInt32BE(24);
  const sha256 = Buffer.from(input.subarray(28, 60));
  const bodyCrc32 = input.readUInt32BE(60);
  const dataBits = input.readUInt32BE(64);
  const blockCount = input.readUInt32BE(68);

  if (coreModules <= FRAME_RINGS * 2 || grid !== coreModules + QUIET_MODULES * 2) fail('INVALID_V2_MANIFEST', 'v2 网格参数不一致');
  if (originalLength > MAX_FILE_SIZE) fail('LIMIT_EXCEEDED', `v2 文件超过 ${MAX_FILE_SIZE} 字节限制`);
  if (filenameLength < 1 || filenameLength > 1024 || bodyLength !== filenameLength + originalLength) fail('INVALID_V2_MANIFEST', 'v2 文件名或正文长度无效');
  const expectedBlocks = Math.ceil(bodyLength / rs.DATA_SYMBOLS);
  if (blockCount !== expectedBlocks || encodedLength !== blockCount * rs.FIELD_SIZE) fail('INVALID_V2_MANIFEST', 'v2 RS 长度参数不一致');
  const expectedBits = (MANIFEST_SIZE * MANIFEST_COPIES + encodedLength) * 8;
  if (dataBits !== expectedBits || dataBits > dataCapacityBits(coreModules)) fail('INVALID_V2_MANIFEST', 'v2 数据位容量无效');

  return {
    version: VERSION,
    profile: PROFILE,
    modulePixels: MODULE_PIXELS,
    quietModules: QUIET_MODULES,
    coreModules,
    grid,
    originalLength,
    filenameLength,
    bodyLength,
    encodedLength,
    sha256,
    crc32: bodyCrc32,
    dataBits,
    blockCount,
  };
}

function majorityManifest(copies) {
  if (!Buffer.isBuffer(copies)) copies = Buffer.from(copies);
  if (copies.length < MANIFEST_SIZE * MANIFEST_COPIES) fail('INVALID_V2_MANIFEST', 'v2 manifest 副本不完整');
  const output = Buffer.alloc(MANIFEST_SIZE);
  const second = MANIFEST_SIZE;
  const third = MANIFEST_SIZE * 2;
  for (let index = 0; index < MANIFEST_SIZE; index += 1) {
    const a = copies[index], b = copies[second + index], c = copies[third + index];
    output[index] = (a & b) | (a & c) | (b & c);
  }
  try {
    parseManifest(output);
    return output;
  } catch (majorityError) {
    const valid = new Map();
    for (let index = 0; index < MANIFEST_COPIES; index += 1) {
      const copy = Buffer.from(copies.subarray(index * MANIFEST_SIZE, (index + 1) * MANIFEST_SIZE));
      try { parseManifest(copy); valid.set(copy.toString('hex'), copy); } catch { /* Try the next copy. */ }
    }
    if (valid.size === 1) return valid.values().next().value;
    throw majorityError;
  }
}

function buildV2Stream(data, filename) {
  if (!Buffer.isBuffer(data)) data = Buffer.from(data);
  if (data.length > MAX_FILE_SIZE) fail('LIMIT_EXCEEDED', `v2 文件超过 ${MAX_FILE_SIZE} 字节限制`);
  const normalized = normalizeArchiveName(filename);
  const body = Buffer.concat([normalized.encoded, data]);
  const encoded = rs.encode(body);
  const encodedLength = encoded.interleaved.length;
  const dataBits = (MANIFEST_SIZE * MANIFEST_COPIES + encodedLength) * 8;
  const coreModules = chooseCoreModules(dataBits);
  const digest = crypto.createHash('sha256').update(body).digest();
  const bodyCrc32 = crc32(body);
  const manifest = buildManifest({
    coreModules,
    originalLength: data.length,
    filenameLength: normalized.encoded.length,
    bodyLength: body.length,
    encodedLength,
    sha256: digest,
    crc32: bodyCrc32,
    dataBits,
    blockCount: encoded.blockCount,
  });
  const stream = Buffer.concat([manifest, manifest, manifest, encoded.interleaved]);
  return {
    manifest,
    stream,
    fields: parseManifest(manifest),
    metadata: {
      filename: normalized.name,
      fileLength: data.length,
      sha256: crypto.createHash('sha256').update(data).digest('hex'),
      bodySha256: digest.toString('hex'),
      version: '2.0',
      profile: PROFILE,
      coreModules,
      totalModules: coreModules + QUIET_MODULES * 2,
      width: (coreModules + QUIET_MODULES * 2) * MODULE_PIXELS,
      height: (coreModules + QUIET_MODULES * 2) * MODULE_PIXELS,
      rsBlocks: encoded.blockCount,
    },
  };
}

function recoverV2Body(manifestInput, interleaved) {
  const fields = Buffer.isBuffer(manifestInput) ? parseManifest(manifestInput) : manifestInput;
  if (!Buffer.isBuffer(interleaved)) interleaved = Buffer.from(interleaved);
  if (interleaved.length !== fields.encodedLength) fail('INVALID_V2_DATA', 'v2 RS 数据长度无效');
  let corrected;
  try { corrected = rs.decode(interleaved, fields.blockCount, fields.bodyLength); }
  catch (error) { fail('V2_ECC_UNRECOVERABLE', `v2 Reed–Solomon 纠错失败：${error.message}`); }
  const body = Buffer.from(corrected.data);
  if (crc32(body) !== fields.crc32) fail('V2_BODY_CHECKSUM_MISMATCH', 'v2 正文 CRC-32 校验失败');
  const digest = crypto.createHash('sha256').update(body).digest();
  if (!crypto.timingSafeEqual(digest, fields.sha256)) fail('V2_BODY_CHECKSUM_MISMATCH', 'v2 正文 SHA-256 校验失败');

  const filenameRaw = body.subarray(0, fields.filenameLength);
  let filename;
  try { filename = new TextDecoder('utf-8', { fatal: true }).decode(filenameRaw); }
  catch { fail('INVALID_FILENAME', 'v2 文件名不是有效 UTF-8'); }
  if (filename.normalize('NFC') !== filename) fail('INVALID_FILENAME', 'v2 文件名不是 NFC 规范形式');
  filename = normalizeArchiveName(filename).name;
  const data = Buffer.from(body.subarray(fields.filenameLength));
  return {
    filename,
    data,
    fileLength: data.length,
    sha256: crypto.createHash('sha256').update(data).digest('hex'),
    correctedSymbols: corrected.correctedSymbols,
    versionMajor: VERSION,
    versionMinor: 0,
    fields,
    metadata() {
      return {
        filename,
        fileLength: data.length,
        sha256: crypto.createHash('sha256').update(data).digest('hex'),
        version: '2.0',
        correctedSymbols: corrected.correctedSymbols,
      };
    },
  };
}

module.exports = {
  MAGIC,
  VERSION,
  PROFILE,
  MODULE_PIXELS,
  QUIET_MODULES,
  MANIFEST_SIZE,
  MANIFEST_COPIES,
  FRAME_RINGS,
  SYNC_INTERVAL,
  MAX_FILE_SIZE,
  usableRow,
  syncModuleIsBlack,
  dataCapacityBits,
  chooseCoreModules,
  forEachDataPosition,
  buildManifest,
  parseManifest,
  majorityManifest,
  buildV2Stream,
  recoverV2Body,
};
