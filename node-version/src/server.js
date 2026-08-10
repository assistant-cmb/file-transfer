const childProcess = require('node:child_process');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const { URL } = require('node:url');
const { encodeBytes, decodeBytes } = require('./codec');
const { FileTransferError } = require('./errors');
const { MAX_FILE_SIZE, safeOutputName } = require('./format');

const SHARED_DIR = path.resolve(__dirname, '..', '..', 'shared');
const MAX_REQUEST_SIZE = 140 * 1024 * 1024;

function json(response, status, value) {
  send(response, status, Buffer.from(JSON.stringify(value)), 'application/json; charset=utf-8');
}

function send(response, status, body, contentType, headers = {}) {
  response.writeHead(status, {
    'Content-Type': contentType,
    'Content-Length': body.length,
    'X-Content-Type-Options': 'nosniff',
    'Cache-Control': 'no-store',
    ...headers,
  });
  response.end(body);
}

function rfc5987(value) {
  return encodeURIComponent(value).replace(/['()*]/g, (character) => `%${character.charCodeAt(0).toString(16).toUpperCase()}`);
}

function readBody(request) {
  return new Promise((resolve, reject) => {
    const declared = Number(request.headers['content-length']);
    if (!Number.isInteger(declared) || declared < 0 || declared > MAX_REQUEST_SIZE) {
      reject(new FileTransferError('LIMIT_EXCEEDED', '请求体大小超过限制'));
      request.resume();
      return;
    }
    const chunks = [];
    let size = 0;
    request.on('data', (chunk) => {
      size += chunk.length;
      if (size > declared || size > MAX_REQUEST_SIZE) request.destroy(new FileTransferError('LIMIT_EXCEEDED', '请求体大小超过限制'));
      else chunks.push(chunk);
    });
    request.on('end', () => size === declared ? resolve(Buffer.concat(chunks)) : reject(new FileTransferError('IO_ERROR', '请求体读取不完整')));
    request.on('error', reject);
  });
}

function openBrowser(url) {
  let command, args;
  if (process.platform === 'darwin') { command = 'open'; args = [url]; }
  else if (process.platform === 'win32') { command = 'cmd'; args = ['/c', 'start', '', url]; }
  else { command = 'xdg-open'; args = [url]; }
  try { childProcess.spawn(command, args, { detached: true, stdio: 'ignore' }).unref(); } catch { /* URL remains visible in terminal. */ }
}

async function handle(request, response) {
  const url = new URL(request.url, 'http://127.0.0.1');
  if (request.method === 'GET') {
    if (url.pathname === '/api/health') { json(response, 200, { ok: true, runtime: 'Node.js', format: '1.0' }); return; }
    const files = { '/': 'index.html', '/index.html': 'index.html', '/app.js': 'app.js', '/styles.css': 'styles.css' };
    const name = files[url.pathname];
    if (!name) { json(response, 404, { ok: false, code: 'NOT_FOUND', message: '资源不存在' }); return; }
    const types = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8' };
    send(response, 200, fs.readFileSync(path.join(SHARED_DIR, name)), types[path.extname(name)]);
    return;
  }
  if (request.method !== 'POST') { json(response, 405, { ok: false, code: 'METHOD_NOT_ALLOWED', message: '请求方法不支持' }); return; }
  const body = await readBody(request);
  if (url.pathname === '/api/encode') {
    if (body.length > MAX_FILE_SIZE) throw new FileTransferError('LIMIT_EXCEEDED', '文件超过 100 MiB 限制');
    const { png, metadata } = encodeBytes(body, url.searchParams.get('filename') || '');
    send(response, 200, png, 'image/png', {
      'Content-Disposition': `attachment; filename*=UTF-8''${rfc5987(`${safeOutputName(metadata.filename)}.png`)}`,
      'X-Image-Dimensions': `${metadata.width}×${metadata.height}`,
    });
  } else if (url.pathname === '/api/decode') {
    const decoded = decodeBytes(body);
    send(response, 200, decoded.data, 'application/octet-stream', { 'Content-Disposition': `attachment; filename*=UTF-8''${rfc5987(safeOutputName(decoded.filename))}` });
  } else if (url.pathname === '/api/inspect') {
    const decoded = decodeBytes(body);
    json(response, 200, { ok: true, ...decoded.metadata() });
  } else json(response, 404, { ok: false, code: 'NOT_FOUND', message: '接口不存在' });
}

function serve({ host = '127.0.0.1', port = 0, open = true } = {}) {
  const server = http.createServer((request, response) => {
    handle(request, response).catch((error) => {
      if (response.headersSent) { response.destroy(); return; }
      if (error instanceof FileTransferError) json(response, error.code === 'LIMIT_EXCEEDED' ? 413 : 400, error.asObject());
      else json(response, 500, { ok: false, code: 'INTERNAL_ERROR', message: error.message });
    });
  });
  server.listen(port, host, () => {
    const actualPort = server.address().port;
    const url = `http://${host}:${actualPort}/`;
    console.log(`File Transfer Node.js 已启动：${url}`);
    console.log('按 Ctrl+C 退出。');
    if (open) setTimeout(() => openBrowser(url), 400);
  });
  return server;
}

module.exports = { serve };
