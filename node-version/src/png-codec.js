const zlib = require('node:zlib');
const { crc32 } = require('./crc32');
const { FileTransferError } = require('./errors');
const { FIXED_HEADER_SIZE, MAX_FILE_SIZE } = require('./format');

const SIGNATURE = Buffer.from('89504e470d0a1a0a', 'hex');
function fail(code, message) { throw new FileTransferError(code, message); }

function chunk(kind, data) {
  const type = Buffer.from(kind, 'ascii');
  const output = Buffer.alloc(12 + data.length);
  output.writeUInt32BE(data.length, 0);
  type.copy(output, 4);
  data.copy(output, 8);
  output.writeUInt32BE(crc32(type, data), 8 + data.length);
  return output;
}

function encodeRgbPng(width, height, rgb) {
  if (width <= 0 || height <= 0 || rgb.length !== width * height * 3) fail('INVALID_DIMENSIONS', 'RGB 数据长度与图片尺寸不匹配');
  const stride = width * 3;
  const raw = Buffer.alloc((stride + 1) * height);
  for (let row = 0; row < height; row += 1) rgb.copy(raw, row * (stride + 1) + 1, row * stride, (row + 1) * stride);
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8;
  ihdr[9] = 2;
  return Buffer.concat([SIGNATURE, chunk('IHDR', ihdr), chunk('IDAT', zlib.deflateSync(raw, { level: 9 })), chunk('IEND', Buffer.alloc(0))]);
}

function paeth(a, b, c) {
  const p = a + b - c;
  const pa = Math.abs(p - a), pb = Math.abs(p - b), pc = Math.abs(p - c);
  return pa <= pb && pa <= pc ? a : pb <= pc ? b : c;
}

function decodePngToRgb(png) {
  if (!png.subarray(0, 8).equals(SIGNATURE)) fail('INVALID_PNG', '输入不是有效 PNG');
  let offset = 8;
  let ihdr = null;
  const idat = [];
  let seenIend = false;
  while (offset < png.length) {
    if (offset + 12 > png.length) fail('INVALID_PNG', 'PNG 数据被截断');
    const length = png.readUInt32BE(offset);
    const kind = png.subarray(offset + 4, offset + 8);
    const end = offset + 12 + length;
    if (end > png.length) fail('INVALID_PNG', 'PNG chunk 长度无效');
    const data = png.subarray(offset + 8, offset + 8 + length);
    if (png.readUInt32BE(offset + 8 + length) !== crc32(kind, data)) fail('INVALID_PNG', `PNG ${kind.toString('ascii')} chunk CRC 错误`);
    const name = kind.toString('ascii');
    if (name === 'IHDR') {
      if (ihdr || offset !== 8 || length !== 13) fail('INVALID_PNG', 'PNG IHDR 无效');
      ihdr = Buffer.from(data);
    } else if (name === 'IDAT') {
      if (!ihdr) fail('INVALID_PNG', 'PNG IDAT 出现在 IHDR 之前');
      idat.push(data);
    } else if (name === 'IEND') {
      if (length !== 0) fail('INVALID_PNG', 'PNG IEND 无效');
      seenIend = true;
      break;
    } else if (kind[0] >= 65 && kind[0] <= 90) fail('INVALID_PNG', 'PNG 包含不支持的关键 chunk');
    offset = end;
  }
  if (!ihdr || !idat.length || !seenIend) fail('INVALID_PNG', 'PNG 缺少必要 chunk');
  const width = ihdr.readUInt32BE(0), height = ihdr.readUInt32BE(4);
  const depth = ihdr[8], colorType = ihdr[9], compression = ihdr[10], filterMethod = ihdr[11], interlace = ihdr[12];
  if (!width || !height) fail('INVALID_DIMENSIONS', 'PNG 尺寸无效');
  if (depth !== 8 || ![2, 6].includes(colorType) || compression !== 0 || filterMethod !== 0 || interlace !== 0) fail('UNSUPPORTED_PIXEL_FORMAT', '仅支持非交错 8 位 RGB/RGBA PNG');
  const bpp = colorType === 2 ? 3 : 4;
  const maxPixels = Math.floor((MAX_FILE_SIZE + FIXED_HEADER_SIZE + 1024 + 2) / 3) + 1;
  if (width * height > maxPixels) fail('LIMIT_EXCEEDED', 'PNG 解码尺寸超过限制');
  const stride = width * bpp;
  const expectedRaw = (stride + 1) * height;
  let raw;
  try { raw = zlib.inflateSync(Buffer.concat(idat), { maxOutputLength: expectedRaw + 1 }); }
  catch { fail('INVALID_PNG', 'PNG IDAT 解压失败'); }
  if (raw.length !== expectedRaw) fail('INVALID_PNG', 'PNG 解压数据长度无效');
  const samples = Buffer.alloc(stride * height);
  let source = 0;
  for (let row = 0; row < height; row += 1) {
    const filterType = raw[source++];
    if (filterType > 4) fail('INVALID_PNG', 'PNG 使用了未知过滤器');
    const rowStart = row * stride;
    const previousStart = (row - 1) * stride;
    for (let column = 0; column < stride; column += 1) {
      const value = raw[source++];
      const left = column >= bpp ? samples[rowStart + column - bpp] : 0;
      const up = row > 0 ? samples[previousStart + column] : 0;
      const upperLeft = row > 0 && column >= bpp ? samples[previousStart + column - bpp] : 0;
      let predictor = 0;
      if (filterType === 1) predictor = left;
      else if (filterType === 2) predictor = up;
      else if (filterType === 3) predictor = Math.floor((left + up) / 2);
      else if (filterType === 4) predictor = paeth(left, up, upperLeft);
      samples[rowStart + column] = (value + predictor) & 0xff;
    }
  }
  if (colorType === 2) return { width, height, rgb: samples };
  const rgb = Buffer.alloc(width * height * 3);
  let target = 0;
  for (let index = 0; index < samples.length; index += 4) {
    if (samples[index + 3] !== 255) fail('UNSUPPORTED_PIXEL_FORMAT', 'RGBA PNG 包含非不透明 alpha');
    rgb[target++] = samples[index]; rgb[target++] = samples[index + 1]; rgb[target++] = samples[index + 2];
  }
  return { width, height, rgb };
}

module.exports = { encodeRgbPng, decodePngToRgb };
