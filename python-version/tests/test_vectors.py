import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python-version"))

from file_transfer.codec import decode_bytes, encode_bytes
from file_transfer.errors import FileTransferError
from file_transfer.format import build_stream
from file_transfer.png_codec import encode_rgb_png


class VectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vectors = json.loads((ROOT / "shared/fixtures/vectors.json").read_text())

    def test_frozen_streams(self):
        for vector in self.vectors:
            with self.subTest(vector["name"]):
                side, stream, _ = build_stream(bytes.fromhex(vector["payloadHex"]), vector["name"])
                self.assertEqual(vector["side"], side)
                self.assertEqual(vector["streamHex"], stream.hex())

    def test_png_roundtrip(self):
        for vector in self.vectors:
            with self.subTest(vector["name"]):
                payload = bytes.fromhex(vector["payloadHex"])
                png, metadata = encode_bytes(payload, vector["name"])
                recovered = decode_bytes(png)
                self.assertEqual(vector["name"], recovered.filename)
                self.assertEqual(payload, recovered.data)
                self.assertEqual(vector["side"], metadata["width"])

    def test_boundary_length_roundtrips(self):
        for length in (0, 1, 2, 3, 4, 255, 1024, 4097):
            with self.subTest(length=length):
                payload = bytes(index % 251 for index in range(length))
                png, _ = encode_bytes(payload, f"length-{length}.bin")
                self.assertEqual(payload, decode_bytes(png).data)

    def test_detects_payload_and_padding_corruption(self):
        side, stream, _ = build_stream(b"payload", "sample.bin")
        header_length = int.from_bytes(stream[8:12], "big")
        payload_corrupt = bytearray(stream)
        payload_corrupt[header_length] ^= 1
        with self.assertRaisesRegex(FileTransferError, "SHA-256") as payload_error:
            decode_bytes(encode_rgb_png(side, side, payload_corrupt))
        self.assertEqual("PAYLOAD_CHECKSUM_MISMATCH", payload_error.exception.code)

        padding_corrupt = bytearray(stream)
        padding_corrupt[-1] = 1
        with self.assertRaises(FileTransferError) as padding_error:
            decode_bytes(encode_rgb_png(side, side, padding_corrupt))
        self.assertEqual("NONZERO_PADDING", padding_error.exception.code)


if __name__ == "__main__":
    unittest.main()
