const { buildStream, parseStream } = require('./format');
const { decodePngToRgb, encodeRgbPng } = require('./png-codec');

function encodeBytes(data, filename) {
  const { side, stream, metadata } = buildStream(data, filename);
  return { png: encodeRgbPng(side, side, stream), metadata };
}

function decodeBytes(png) {
  const { width, height, rgb } = decodePngToRgb(png);
  return parseStream(rgb, width, height);
}

function inspectBytes(png) { return decodeBytes(png).metadata(); }

async function encodeV2Bytes(data, filename) {
  return require('./v2-image').encodeV2Jpeg(data, filename);
}

async function decodeV2Bytes(image) {
  return require('./v2-image').decodeV2Image(image);
}

async function inspectV2Bytes(image) {
  return (await decodeV2Bytes(image)).metadata();
}

module.exports = { encodeBytes, decodeBytes, inspectBytes, encodeV2Bytes, decodeV2Bytes, inspectV2Bytes };
