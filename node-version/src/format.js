const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const { crc32 } = require('./crc32');
const { FileTransferError } = require('./errors');

const MAGIC = Buffer.from('FTRN', 'ascii');
const VERSION_MAJOR = 1;
const VERSION_MINOR = 0;
const FIXED_HEADER_SIZE = 60;
const MAX_FILENAME_BYTES = 1024;
const MAX_FILE_SIZE = 100 * 1024 * 1024;
const MAX_HEADER_SIZE = 1024 * 1024;

function fail(code, message) { throw new FileTransferError(code, message); }

function normalizeArchiveName(value) {
  const pieces = String(value).split(/[\\/]/);
  const name = (pieces.at(-1) || '').normalize('NFC');
  if (!name || name === '.' || name === '..' || name.startsWith('\ufeff')) fail('INVALID_FILENAME', '文件名为空或不安全');
  if (/[\\/\0\u007f]|\p{Cc}/u.test(name)) fail('INVALID_FILENAME', '文件名包含不允许的字符');
  const encoded = Buffer.from(name, 'utf8');
  if (encoded.length < 1 || encoded.length > MAX_FILENAME_BYTES) fail('INVALID_FILENAME', 'UTF-8 文件名长度必须为 1–1024 字节');
  return { name, encoded };
}

function safeOutputName(value) {
  let { name } = normalizeArchiveName(value);
  if (process.platform === 'win32') {
    name = name.replace(/[<>:"/\\|?*]/g, '_').replace(/[ .]+$/g, '');
    const stem = name.split('.', 1)[0].toUpperCase();
    if (/^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$/.test(stem)) name = `_${name}`;
  }
  return name || 'recovered_file';
}

function uniquePath(candidate) {
  if (!fs.existsSync(candidate)) return candidate;
  const parsed = path.parse(candidate);
  let extensions = '';
  let base = parsed.base;
  while (path.extname(base)) {
    const extension = path.extname(base);
    extensions = extension + extensions;
    base = base.slice(0, -extension.length);
  }
  for (let number = 1; number < 10000; number += 1) {
    const next = path.join(parsed.dir, `${base} (${number})${extensions}`);
    if (!fs.existsSync(next)) return next;
  }
  fail('OUTPUT_EXISTS', '无法找到可用的输出文件名');
}

function integerSqrtCeil(value) {
  if (value < 0n) fail('INVALID_HEADER', '负数不能计算平方根');
  if (value < 2n) return value;
  let low = 1n;
  let high = value;
  while (low < high) {
    const middle = (low + high) >> 1n;
    if (middle * middle >= value) high = middle;
    else low = middle + 1n;
  }
  return low;
}

function buildStream(data, filename, maxFileSize = MAX_FILE_SIZE) {
  if (!Buffer.isBuffer(data)) data = Buffer.from(data);
  if (data.length > maxFileSize) fail('LIMIT_EXCEEDED', `文件超过 ${maxFileSize} 字节限制`);
  const normalized = normalizeArchiveName(filename);
  const headerLength = FIXED_HEADER_SIZE + normalized.encoded.length;
  const digest = crypto.createHash('sha256').update(data).digest();
  const prefix = Buffer.alloc(56);
  MAGIC.copy(prefix, 0);
  prefix[4] = VERSION_MAJOR;
  prefix[5] = VERSION_MINOR;
  prefix.writeUInt16BE(0, 6);
  prefix.writeUInt32BE(headerLength, 8);
  prefix.writeBigUInt64BE(BigInt(data.length), 12);
  prefix.writeUInt32BE(normalized.encoded.length, 20);
  digest.copy(prefix, 24);
  const crc = crc32(prefix, normalized.encoded);
  const header = Buffer.alloc(headerLength);
  prefix.copy(header, 0);
  header.writeUInt32BE(crc, 56);
  normalized.encoded.copy(header, 60);
  const nonPadding = BigInt(header.length + data.length);
  const pixelCount = (nonPadding + 2n) / 3n;
  const sideBig = integerSqrtCeil(pixelCount);
  if (sideBig > 0x7fffffffn) fail('LIMIT_EXCEEDED', '计算得到的 PNG 尺寸超过格式限制');
  const side = Number(sideBig);
  const capacity = side * side * 3;
  const paddingLength = capacity - header.length - data.length;
  const stream = Buffer.concat([header, data, Buffer.alloc(paddingLength)]);
  return {
    side,
    stream,
    metadata: {
      filename: normalized.name,
      fileLength: data.length,
      sha256: digest.toString('hex'),
      version: '1.0',
      width: side,
      height: side,
      paddingLength,
    },
  };
}

function parseStream(rgb, width, height, maxFileSize = MAX_FILE_SIZE) {
  if (width !== height || width <= 0 || rgb.length !== width * height * 3 || rgb.length < FIXED_HEADER_SIZE) fail('INVALID_DIMENSIONS', '图片尺寸无效或不足以容纳固定头部');
  if (!rgb.subarray(0, 4).equals(MAGIC)) fail('NOT_FILE_TRANSFER', '不是 File Transfer 生成的图片');
  const major = rgb[4];
  const minor = rgb[5];
  const flags = rgb.readUInt16BE(6);
  const headerLength = rgb.readUInt32BE(8);
  const fileLengthBig = rgb.readBigUInt64BE(12);
  const filenameLength = rgb.readUInt32BE(20);
  if (fileLengthBig > BigInt(maxFileSize)) fail('LIMIT_EXCEEDED', `图片声明的文件超过 ${maxFileSize} 字节限制`);
  const fileLength = Number(fileLengthBig);
  if (major !== VERSION_MAJOR) fail('UNSUPPORTED_VERSION', `不支持格式版本 ${major}.${minor}`);
  if (flags !== 0) fail('UNSUPPORTED_FLAGS', `不支持格式标志 0x${flags.toString(16).padStart(4, '0')}`);
  if (filenameLength < 1 || filenameLength > MAX_FILENAME_BYTES) fail('INVALID_HEADER', '文件名长度字段无效');
  const minimumHeader = FIXED_HEADER_SIZE + filenameLength;
  if (headerLength < minimumHeader || headerLength > rgb.length || headerLength > MAX_HEADER_SIZE) fail('INVALID_HEADER', '头部长度字段无效');
  if (minor === 0 && headerLength !== minimumHeader) fail('INVALID_HEADER', 'v1.0 不允许扩展头部');
  if (fileLength > rgb.length - headerLength) fail('INVALID_HEADER', '文件长度超过图片容量');
  const expectedCrc = rgb.readUInt32BE(56);
  const actualCrc = crc32(rgb.subarray(0, 56), rgb.subarray(60, headerLength));
  if (expectedCrc !== actualCrc) fail('HEADER_CHECKSUM_MISMATCH', '头部 CRC-32 校验失败');
  const filenameRaw = rgb.subarray(60, 60 + filenameLength);
  const decoder = new TextDecoder('utf-8', { fatal: true });
  let filename;
  try { filename = decoder.decode(filenameRaw); } catch { fail('INVALID_FILENAME', '文件名不是有效 UTF-8'); }
  if (filename.normalize('NFC') !== filename) fail('INVALID_FILENAME', '文件名不是 NFC 规范形式');
  filename = normalizeArchiveName(filename).name;
  const total = headerLength + fileLength;
  const expectedSide = Number(integerSqrtCeil((BigInt(total) + 2n) / 3n));
  if (width !== expectedSide) fail('CAPACITY_MISMATCH', '图片尺寸与声明内容不匹配');
  const payload = Buffer.from(rgb.subarray(headerLength, total));
  for (const value of rgb.subarray(total)) if (value !== 0) fail('NONZERO_PADDING', '图片补零区域包含非零数据');
  const actualDigest = crypto.createHash('sha256').update(payload).digest();
  if (!crypto.timingSafeEqual(actualDigest, rgb.subarray(24, 56))) fail('PAYLOAD_CHECKSUM_MISMATCH', '文件 SHA-256 校验失败');
  return {
    filename,
    data: payload,
    fileLength,
    sha256: actualDigest.toString('hex'),
    versionMajor: major,
    versionMinor: minor,
    metadata() {
      return { filename, fileLength, sha256: actualDigest.toString('hex'), version: `${major}.${minor}` };
    },
  };
}

module.exports = {
  FIXED_HEADER_SIZE,
  MAX_FILE_SIZE,
  buildStream,
  parseStream,
  normalizeArchiveName,
  safeOutputName,
  uniquePath,
};
