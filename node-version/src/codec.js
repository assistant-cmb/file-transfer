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

module.exports = { encodeBytes, decodeBytes, inspectBytes };
