#!/usr/bin/env node
const fs = require('node:fs');
const path = require('node:path');
const { encodeBytes, decodeBytes, encodeV2Bytes, decodeV2Bytes } = require('./codec');
const { FileTransferError } = require('./errors');
const { safeOutputName, uniquePath } = require('./format');
const { createZip } = require('./zip-archive');

function usage() {
  console.log(`File Transfer PNG v1 / JPEG v2

用法:
  node src/cli.js encode <input> [-o output] [--format png|jpeg] [--zip] [--json]
  node src/cli.js decode <input.png|jpg> [-o output-or-directory] [--json]
  node src/cli.js inspect <input.png|jpg> [--json]
  node src/cli.js serve [--host 127.0.0.1] [--port 0] [--no-browser]`);
}

function parse(argv) {
  const args = { command: argv[0], input: null, output: null, json: false, zip: false, format: 'png', formatSet: false, host: '127.0.0.1', port: 0, noBrowser: false };
  for (let index = 1; index < argv.length; index += 1) {
    const value = argv[index];
    if (value === '--json') args.json = true;
    else if (value === '--zip') args.zip = true;
    else if (value === '--no-browser') args.noBrowser = true;
    else if (value === '-o' || value === '--output') args.output = argv[++index];
    else if (value === '--format') { args.format = argv[++index]; args.formatSet = true; }
    else if (value === '--host') args.host = argv[++index];
    else if (value === '--port') args.port = Number(argv[++index]);
    else if (!args.input) args.input = value;
    else throw new FileTransferError('INVALID_HEADER', `未知参数：${value}`);
  }
  return args;
}

function readFile(filename) {
  try {
    if (!filename || !fs.statSync(filename).isFile()) throw new Error('not file');
    return fs.readFileSync(filename);
  } catch { throw new FileTransferError('INPUT_NOT_FOUND', `输入文件不存在：${filename || ''}`); }
}

function writeFile(filename, data) {
  const output = uniquePath(filename);
  try { fs.mkdirSync(path.dirname(path.resolve(output)), { recursive: true }); fs.writeFileSync(output, data); }
  catch (error) { throw new FileTransferError('IO_ERROR', `无法写入输出文件：${error.message}`); }
  return path.resolve(output);
}

function human(result) {
  if (result.operation === 'inspect') return `有效的 File Transfer v${result.version} 图片：${result.filename}，${result.fileLength} 字节，SHA-256 ${result.sha256}`;
  return `${result.operation} 完成：${result.output}`;
}

async function main(argv = process.argv.slice(2)) {
  if (!argv.length || argv[0] === '-h' || argv[0] === '--help') { usage(); return 0; }
  let args;
  try {
    args = parse(argv);
    if (args.command === 'serve') {
      require('./server').serve({ host: args.host, port: args.port, open: !args.noBrowser });
      return 0;
    }
    if (!['encode', 'decode', 'inspect'].includes(args.command) || !args.input) throw new FileTransferError('INVALID_HEADER', '命令或输入参数无效');
    if (args.zip && args.command !== 'encode') throw new FileTransferError('INVALID_HEADER', '--zip 只能用于 encode 命令');
    if (args.formatSet && args.command !== 'encode') throw new FileTransferError('INVALID_HEADER', '--format 只能用于 encode 命令');
    if (!['png', 'jpeg', 'jpg'].includes(args.format)) throw new FileTransferError('INVALID_HEADER', '--format 只支持 png 或 jpeg');
    const input = readFile(args.input);
    let result;
    if (args.command === 'encode') {
      const outputFormat = ['jpeg', 'jpg'].includes(args.format) ? 'jpeg' : 'png';
      if (outputFormat === 'jpeg' && args.zip) throw new FileTransferError('INVALID_HEADER', 'JPEG v2 不能与 --zip 同时使用；请直接编码原 ZIP 文件');
      if (outputFormat === 'jpeg') {
        const encoded = await encodeV2Bytes(input, path.basename(args.input));
        const output = writeFile(args.output || `${args.input}.jpg`, encoded.jpg);
        result = { ok: true, operation: 'encode', format: outputFormat, output, ...encoded.metadata };
      } else {
        const encoded = encodeBytes(input, path.basename(args.input));
        const pngName = `${safeOutputName(path.basename(args.input))}.png`;
        const data = args.zip ? createZip(encoded.png, pngName) : encoded.png;
        const output = writeFile(args.output || `${args.input}.png${args.zip ? '.zip' : ''}`, data);
        result = { ok: true, operation: 'encode', format: outputFormat, output, ...encoded.metadata };
        if (args.zip) Object.assign(result, { archive: 'zip', archiveEntry: pngName });
      }
    } else {
      const decoded = input.length >= 3 && input[0] === 0xff && input[1] === 0xd8 && input[2] === 0xff
        ? await decodeV2Bytes(input)
        : decodeBytes(input);
      if (args.command === 'inspect') result = { ok: true, operation: 'inspect', ...decoded.metadata() };
      else {
        let target;
        if (!args.output) target = path.join(path.dirname(args.input), safeOutputName(decoded.filename));
        else if (fs.existsSync(args.output) && fs.statSync(args.output).isDirectory()) target = path.join(args.output, safeOutputName(decoded.filename));
        else target = args.output;
        result = { ok: true, operation: 'decode', output: writeFile(target, decoded.data), ...decoded.metadata() };
      }
    }
    console.log(args.json ? JSON.stringify(result) : human(result));
    return 0;
  } catch (error) {
    const known = error instanceof FileTransferError ? error : new FileTransferError('INTERNAL_ERROR', error.message);
    console.error(args?.json ? JSON.stringify(known.asObject()) : `错误 [${known.code}]：${known.message}`);
    return known.code === 'INTERNAL_ERROR' ? 3 : 2;
  }
}

if (require.main === module) main().then(
  (code) => { process.exitCode = code; },
  (error) => { console.error(`错误 [INTERNAL_ERROR]：${error.message}`); process.exitCode = 3; },
);
module.exports = { main };
