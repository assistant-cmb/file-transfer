#!/usr/bin/env node
const fs = require('node:fs');
const path = require('node:path');
const { encodeBytes, decodeBytes } = require('./codec');
const { FileTransferError } = require('./errors');
const { safeOutputName, uniquePath } = require('./format');

function usage() {
  console.log(`File Transfer PNG v1.0

用法:
  node src/cli.js encode <input> [-o output.png] [--json]
  node src/cli.js decode <input.png> [-o output-or-directory] [--json]
  node src/cli.js inspect <input.png> [--json]
  node src/cli.js serve [--host 127.0.0.1] [--port 0] [--no-browser]`);
}

function parse(argv) {
  const args = { command: argv[0], input: null, output: null, json: false, host: '127.0.0.1', port: 0, noBrowser: false };
  for (let index = 1; index < argv.length; index += 1) {
    const value = argv[index];
    if (value === '--json') args.json = true;
    else if (value === '--no-browser') args.noBrowser = true;
    else if (value === '-o' || value === '--output') args.output = argv[++index];
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
  if (result.operation === 'inspect') return `有效的 File Transfer PNG：${result.filename}，${result.fileLength} 字节，SHA-256 ${result.sha256}`;
  return `${result.operation} 完成：${result.output}`;
}

function main(argv = process.argv.slice(2)) {
  if (!argv.length || argv[0] === '-h' || argv[0] === '--help') { usage(); return 0; }
  let args;
  try {
    args = parse(argv);
    if (args.command === 'serve') {
      require('./server').serve({ host: args.host, port: args.port, open: !args.noBrowser });
      return 0;
    }
    if (!['encode', 'decode', 'inspect'].includes(args.command) || !args.input) throw new FileTransferError('INVALID_HEADER', '命令或输入参数无效');
    const input = readFile(args.input);
    let result;
    if (args.command === 'encode') {
      const encoded = encodeBytes(input, path.basename(args.input));
      const output = writeFile(args.output || `${args.input}.png`, encoded.png);
      result = { ok: true, operation: 'encode', output, ...encoded.metadata };
    } else {
      const decoded = decodeBytes(input);
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

if (require.main === module) process.exitCode = main();
module.exports = { main };
