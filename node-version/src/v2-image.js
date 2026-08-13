'use strict';

const { FileTransferError } = require('./errors');
const {
  MODULE_PIXELS,
  QUIET_MODULES,
  MANIFEST_SIZE,
  MANIFEST_COPIES,
  FRAME_RINGS,
  buildV2Stream,
  parseManifest,
  majorityManifest,
  recoverV2Body,
  dataCapacityBits,
  forEachDataPosition,
  syncModuleIsBlack,
} = require('./v2-format');

const MIN_DECODED_MODULE_PIXELS = 2.8;
const MAX_DECODED_MODULE_PIXELS = 5.2;
const MAX_INPUT_PIXELS = 80_000_000;

function fail(code, message) { throw new FileTransferError(code, message); }

function loadSharp() {
  try { return require('sharp'); }
  catch { fail('MISSING_DEPENDENCY', 'JPEG v2 需要 sharp；请先在 node-version 目录运行 npm install'); }
}

function bitAt(bytes, index) {
  return (bytes[index >>> 3] >>> (7 - (index & 7))) & 1;
}

function timingModuleIsBlack(x, y, coreModules) {
  const far = coreModules - 2;
  const horizontal = (y === 1 || y === far) && (x & 1) === 0;
  const vertical = (x === 1 || x === far) && (y & 1) === 0;
  return horizontal || vertical;
}

function buildModuleRaster(built) {
  const { coreModules, dataBits } = built.fields;
  const totalModules = coreModules + QUIET_MODULES * 2;
  const modules = Buffer.alloc(totalModules * totalModules, 255);
  const setBlack = (x, y) => { modules[(y + QUIET_MODULES) * totalModules + x + QUIET_MODULES] = 0; };

  for (let coordinate = 0; coordinate < coreModules; coordinate += 1) {
    setBlack(coordinate, 0);
    setBlack(coordinate, coreModules - 1);
    setBlack(0, coordinate);
    setBlack(coreModules - 1, coordinate);
  }
  for (let coordinate = 1; coordinate < coreModules - 1; coordinate += 1) {
    if (timingModuleIsBlack(coordinate, 1, coreModules)) setBlack(coordinate, 1);
    if (timingModuleIsBlack(coordinate, coreModules - 2, coreModules)) setBlack(coordinate, coreModules - 2);
    if (timingModuleIsBlack(1, coordinate, coreModules)) setBlack(1, coordinate);
    if (timingModuleIsBlack(coreModules - 2, coordinate, coreModules)) setBlack(coreModules - 2, coordinate);
  }

  const grid = coreModules - FRAME_RINGS * 2;
  for (let localY = 0; localY < grid; localY += 1) {
    if ((localY + 1) % 10 !== 0) continue;
    for (let localX = 0; localX < grid; localX += 1) {
      if (syncModuleIsBlack(localX, localY)) setBlack(localX + FRAME_RINGS, localY + FRAME_RINGS);
    }
  }
  forEachDataPosition(coreModules, dataBits, (x, y, index) => {
    if (bitAt(built.stream, index)) setBlack(x, y);
  });
  return { modules, totalModules };
}

async function encodeV2Jpeg(data, filename, options = {}) {
  const sharp = loadSharp();
  const built = buildV2Stream(data, filename);
  const raster = buildModuleRaster(built);
  const side = raster.totalModules * MODULE_PIXELS;
  const quality = options.quality === undefined ? 95 : options.quality;
  if (quality !== 95) fail('INVALID_JPEG_QUALITY', 'v2 profile 1 固定使用 JPEG quality 95');
  let jpg;
  try {
    jpg = await sharp(raster.modules, {
      raw: { width: raster.totalModules, height: raster.totalModules, channels: 1 },
    })
      .resize(side, side, { kernel: sharp.kernel.nearest })
      .jpeg({ quality, chromaSubsampling: '4:4:4', force: true })
      .toBuffer();
  } catch (error) {
    fail('JPEG_ENCODE_FAILED', `v2 JPEG 编码失败：${error.message}`);
  }
  return {
    jpg,
    jpeg: jpg,
    metadata: { ...built.metadata, quality, mimeType: 'image/jpeg' },
  };
}

function sampleModule(pixels, width, height, totalModules, moduleX, moduleY) {
  const pixelX = Math.min(width - 1, Math.max(0, Math.floor((moduleX + 0.5) * width / totalModules)));
  const pixelY = Math.min(height - 1, Math.max(0, Math.floor((moduleY + 0.5) * height / totalModules)));
  return pixels[pixelY * width + pixelX] < 128;
}

function geometryScore(pixels, width, height, totalModules) {
  const coreModules = totalModules - QUIET_MODULES * 2;
  const sample = (coreX, coreY) => sampleModule(pixels, width, height, totalModules, coreX + QUIET_MODULES, coreY + QUIET_MODULES);
  let right = 0;
  let count = 0;
  const judge = (actual, expected) => { count += 1; if (actual === expected) right += 1; };
  const step = Math.max(1, Math.floor(coreModules / 48));

  for (let coordinate = 0; coordinate < coreModules; coordinate += step) {
    judge(sample(coordinate, 0), true);
    judge(sample(coordinate, coreModules - 1), true);
    judge(sample(0, coordinate), true);
    judge(sample(coreModules - 1, coordinate), true);
    if (coordinate >= 1 && coordinate < coreModules - 1) {
      judge(sample(coordinate, 1), timingModuleIsBlack(coordinate, 1, coreModules));
      judge(sample(coordinate, coreModules - 2), timingModuleIsBlack(coordinate, coreModules - 2, coreModules));
      judge(sample(1, coordinate), timingModuleIsBlack(1, coordinate, coreModules));
      judge(sample(coreModules - 2, coordinate), timingModuleIsBlack(coreModules - 2, coordinate, coreModules));
    }
  }
  const quietStep = Math.max(1, Math.floor(totalModules / 24));
  for (let coordinate = 0; coordinate < totalModules; coordinate += quietStep) {
    judge(sampleModule(pixels, width, height, totalModules, coordinate, Math.floor(QUIET_MODULES / 2)), false);
    judge(sampleModule(pixels, width, height, totalModules, coordinate, totalModules - 1 - Math.floor(QUIET_MODULES / 2)), false);
    judge(sampleModule(pixels, width, height, totalModules, Math.floor(QUIET_MODULES / 2), coordinate), false);
    judge(sampleModule(pixels, width, height, totalModules, totalModules - 1 - Math.floor(QUIET_MODULES / 2), coordinate), false);
  }
  return right / count;
}

function extractDataBytes(pixels, width, height, totalModules, coreModules, byteLength) {
  const output = Buffer.alloc(byteLength);
  const bitLength = byteLength * 8;
  const count = forEachDataPosition(coreModules, bitLength, (x, y, index) => {
    const black = sampleModule(pixels, width, height, totalModules, x + QUIET_MODULES, y + QUIET_MODULES);
    if (black) output[index >>> 3] |= 1 << (7 - (index & 7));
  });
  if (count !== bitLength) fail('INVALID_V2_DATA', 'v2 图片数据区容量不足');
  return output;
}

function findManifest(pixels, width, height) {
  const shortest = Math.min(width, height);
  const longest = Math.max(width, height);
  const minimumTotal = Math.max(QUIET_MODULES * 2 + FRAME_RINGS * 2 + 1, Math.ceil(longest / MAX_DECODED_MODULE_PIXELS));
  const maximumTotal = Math.floor(shortest / MIN_DECODED_MODULE_PIXELS);
  const candidates = [];
  for (let totalModules = minimumTotal; totalModules <= maximumTotal; totalModules += 1) {
    const coreModules = totalModules - QUIET_MODULES * 2;
    if (dataCapacityBits(coreModules) < MANIFEST_SIZE * MANIFEST_COPIES * 8) continue;
    const score = geometryScore(pixels, width, height, totalModules);
    if (score >= 0.62) candidates.push({ totalModules, coreModules, score });
  }
  candidates.sort((left, right) => right.score - left.score);

  for (const candidate of candidates.slice(0, 160)) {
    try {
      const copies = extractDataBytes(
        pixels,
        width,
        height,
        candidate.totalModules,
        candidate.coreModules,
        MANIFEST_SIZE * MANIFEST_COPIES,
      );
      const manifest = majorityManifest(copies);
      const fields = parseManifest(manifest);
      if (fields.coreModules !== candidate.coreModules) continue;
      return { ...candidate, manifest, fields };
    } catch (error) {
      if (!(error instanceof FileTransferError)) throw error;
    }
  }
  fail('NOT_FILE_TRANSFER_V2', '无法在图片中定位有效的 File Transfer JPEG v2 manifest');
}

async function decodeV2Image(image) {
  const sharp = loadSharp();
  if (!Buffer.isBuffer(image)) image = Buffer.from(image);
  let decoded;
  try {
    decoded = await sharp(image, { limitInputPixels: MAX_INPUT_PIXELS })
      .rotate()
      .greyscale()
      .raw()
      .toBuffer({ resolveWithObject: true });
  } catch (error) {
    fail('INVALID_IMAGE', `无法读取 v2 JPEG 图片：${error.message}`);
  }
  const { width, height, channels } = decoded.info;
  if (width * height > MAX_INPUT_PIXELS) fail('LIMIT_EXCEEDED', 'v2 输入图片像素过多');
  if (Math.abs(width - height) / Math.max(width, height) > 0.02) fail('INVALID_DIMENSIONS', 'v2 图片必须近似正方形');
  let pixels = decoded.data;
  if (channels !== 1) {
    const gray = Buffer.alloc(width * height);
    for (let source = 0, target = 0; target < gray.length; source += channels, target += 1) gray[target] = pixels[source];
    pixels = gray;
  }

  const located = findManifest(pixels, width, height);
  const byteLength = located.fields.dataBits / 8;
  const stream = extractDataBytes(pixels, width, height, located.totalModules, located.coreModules, byteLength);
  const recoveredManifest = majorityManifest(stream.subarray(0, MANIFEST_SIZE * MANIFEST_COPIES));
  const fields = parseManifest(recoveredManifest);
  const interleaved = stream.subarray(MANIFEST_SIZE * MANIFEST_COPIES);
  const result = recoverV2Body(fields, interleaved);
  result.image = {
    width,
    height,
    totalModules: located.totalModules,
    coreModules: located.coreModules,
    decodedModulePixelsX: width / located.totalModules,
    decodedModulePixelsY: height / located.totalModules,
    geometryScore: located.score,
  };
  return result;
}

module.exports = {
  MIN_DECODED_MODULE_PIXELS,
  MAX_DECODED_MODULE_PIXELS,
  timingModuleIsBlack,
  buildModuleRaster,
  encodeV2Jpeg,
  decodeV2Image,
  encodeV2Bytes: encodeV2Jpeg,
  decodeV2Bytes: decodeV2Image,
};
