const state = { mode: 'encode', file: null, downloadUrl: null };
const $ = (id) => document.getElementById(id);
const input = $('file-input');
const zone = $('drop-zone');
const action = $('action-button');
const status = $('status');
const download = $('download');

function humanSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KiB`;
  return `${(bytes / 1024 ** 2).toFixed(2)} MiB`;
}

function clearResult() {
  if (state.downloadUrl) URL.revokeObjectURL(state.downloadUrl);
  state.downloadUrl = null;
  download.classList.add('hidden');
  status.classList.add('hidden');
  status.classList.remove('error');
}

function selectFile(file) {
  clearResult();
  state.file = file || null;
  $('file-info').classList.toggle('hidden', !file);
  action.disabled = !file;
  if (file) {
    $('file-name').textContent = file.name;
    $('file-size').textContent = humanSize(file.size);
  }
}

function setMode(mode) {
  state.mode = mode;
  document.querySelectorAll('.tab').forEach((tab) => tab.classList.toggle('active', tab.dataset.mode === mode));
  $('drop-title').textContent = mode === 'encode' ? '选择或拖入任意文件' : '选择或拖入 File Transfer PNG';
  $('drop-subtitle').textContent = mode === 'encode' ? '单个文件，最大 100 MiB' : '只接受未被修改的无损 PNG';
  action.textContent = mode === 'encode' ? '转换为 PNG' : '还原原文件';
  input.accept = mode === 'decode' ? 'image/png,.png' : '';
  input.value = '';
  selectFile(null);
}

function showStatus(message, error = false) {
  status.textContent = message;
  status.classList.remove('hidden');
  status.classList.toggle('error', error);
}

function filenameFromDisposition(value, fallback) {
  const match = value?.match(/filename\*=UTF-8''([^;]+)/i);
  if (!match) return fallback;
  try { return decodeURIComponent(match[1]); } catch { return fallback; }
}

async function run() {
  if (!state.file) return;
  clearResult();
  action.disabled = true;
  showStatus(state.mode === 'encode' ? '正在编码，请稍候…' : '正在校验并还原，请稍候…');
  try {
    const query = state.mode === 'encode' ? `?filename=${encodeURIComponent(state.file.name)}` : '';
    const response = await fetch(`/api/${state.mode}${query}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/octet-stream' },
      body: state.file,
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.message || `${body.code || 'HTTP_ERROR'} (${response.status})`);
    }
    const blob = await response.blob();
    const fallback = state.mode === 'encode' ? `${state.file.name}.png` : 'recovered_file';
    const filename = filenameFromDisposition(response.headers.get('Content-Disposition'), fallback);
    state.downloadUrl = URL.createObjectURL(blob);
    download.href = state.downloadUrl;
    download.download = filename;
    download.textContent = `下载 ${filename}`;
    download.classList.remove('hidden');
    const dimensions = response.headers.get('X-Image-Dimensions');
    showStatus(state.mode === 'encode'
      ? `转换完成：${humanSize(state.file.size)} → ${humanSize(blob.size)}${dimensions ? ` · ${dimensions}` : ''}`
      : `校验通过，已恢复 ${filename}（${humanSize(blob.size)}）`);
  } catch (error) {
    showStatus(`处理失败：${error.message}`, true);
  } finally {
    action.disabled = !state.file;
  }
}

document.querySelectorAll('.tab').forEach((tab) => tab.addEventListener('click', () => setMode(tab.dataset.mode)));
zone.addEventListener('click', () => input.click());
zone.addEventListener('keydown', (event) => { if (event.key === 'Enter' || event.key === ' ') input.click(); });
input.addEventListener('change', () => selectFile(input.files[0]));
['dragenter', 'dragover'].forEach((name) => zone.addEventListener(name, (event) => { event.preventDefault(); zone.classList.add('dragging'); }));
['dragleave', 'drop'].forEach((name) => zone.addEventListener(name, (event) => { event.preventDefault(); zone.classList.remove('dragging'); }));
zone.addEventListener('drop', (event) => selectFile(event.dataTransfer.files[0]));
action.addEventListener('click', run);

fetch('/api/health').then((r) => r.json()).then((data) => { $('runtime').textContent = `${data.runtime} · Format v${data.format}`; }).catch(() => {});
