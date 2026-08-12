from __future__ import annotations

import io
import zipfile


def create_zip(data: bytes, entry_name: str) -> bytes:
    """Return a ZIP archive containing one deflated file."""
    output = io.BytesIO()
    info = zipfile.ZipInfo(entry_name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o600 << 16
    info.flag_bits |= 0x800
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return output.getvalue()
