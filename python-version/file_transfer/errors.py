class FileTransferError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def as_dict(self) -> dict[str, str | bool]:
        return {"ok": False, "code": self.code, "message": self.message}
