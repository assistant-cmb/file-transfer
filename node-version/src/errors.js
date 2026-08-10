class FileTransferError extends Error {
  constructor(code, message) {
    super(message);
    this.name = 'FileTransferError';
    this.code = code;
  }

  asObject() {
    return { ok: false, code: this.code, message: this.message };
  }
}

module.exports = { FileTransferError };
