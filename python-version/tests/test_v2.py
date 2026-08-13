import io
import struct
import sys
import unittest
import zlib
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python-version"))

from file_transfer.rs_codec import decode_block, encode_block
from file_transfer.v2_format import (
    MANIFEST_STREAM_BYTES,
    V2Manifest,
    make_manifest,
    prepare_body,
    recover_manifest,
)
from file_transfer.v2_image import (
    decode_v2_image,
    encode_v2_jpeg,
    minimum_core_modules,
)


class ReedSolomonV2Tests(unittest.TestCase):
    def test_corrects_38_symbol_errors(self):
        data = bytes(index % 251 for index in range(179))
        codeword = bytearray(encode_block(data))
        positions = list(range(0, 228, 6))
        self.assertEqual(38, len(positions))
        for index, position in enumerate(positions):
            codeword[position] ^= index + 1
        self.assertEqual(data, decode_block(bytes(codeword)))


class FormatV2Tests(unittest.TestCase):
    def test_frozen_manifest_vector_and_offsets(self):
        prepared = prepare_body(b"abc", "x.bin")
        data_bits = (MANIFEST_STREAM_BYTES + len(prepared.encoded)) * 8
        manifest = make_manifest(prepared, minimum_core_modules(data_bits))
        raw = manifest.to_bytes()
        expected_hex = (
            "46324a520201040800480058000000030000000500000008000000ff"
            "4e18d605cb8b066f68e985ab488441c61c1d1bfe9b190cf387d06608"
            "ad9666b44597b4000000103800000001000000000000000000000000821d0d38"
        )
        self.assertEqual(expected_hex, raw.hex())
        self.assertEqual(b"F2JR", raw[0:4])
        self.assertEqual((2, 1, 4, 8), tuple(raw[4:8]))
        self.assertEqual((72, 88), struct.unpack(">HH", raw[8:12]))
        self.assertEqual((3, 5, 8, 255), struct.unpack(">IIII", raw[12:28]))
        self.assertEqual((4152, 1), struct.unpack(">II", raw[64:72]))
        self.assertEqual(bytes(12), raw[72:84])
        self.assertEqual(zlib.crc32(raw[:84]) & 0xFFFFFFFF,
                         struct.unpack(">I", raw[84:88])[0])
        self.assertEqual(manifest, V2Manifest.from_bytes(raw))

        corrupt = bytearray(raw * 3)
        corrupt[0] ^= 0x01
        corrupt[88 + 1] ^= 0x02
        corrupt[176 + 2] ^= 0x04
        self.assertEqual(manifest, recover_manifest(bytes(corrupt)))


class ImageV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = bytes(index % 251 for index in range(1024))
        cls.jpeg, cls.metadata = encode_v2_jpeg(cls.payload, "样例.bin")

    def test_one_kibibyte_jpeg_roundtrip(self):
        recovered = decode_v2_image(self.jpeg)
        self.assertEqual("样例.bin", recovered.filename)
        self.assertEqual(self.payload, recovered.data)
        self.assertEqual("2.0", recovered.metadata()["version"])

    def test_resize_and_quality_82_roundtrip(self):
        with Image.open(io.BytesIO(self.jpeg)) as source:
            side = round(source.width * 0.82)
            resized = source.resize((side, side), Image.Resampling.BILINEAR)
            output = io.BytesIO()
            resized.save(output, "JPEG", quality=82)
        recovered = decode_v2_image(output.getvalue())
        self.assertEqual(self.payload, recovered.data)

    def test_100_kibibyte_exact_dimensions(self):
        jpeg, metadata = encode_v2_jpeg(bytes(100 * 1024), "limit.bin")
        self.assertTrue(jpeg.startswith(b"\xff\xd8"))
        self.assertEqual(4644, metadata["width"])
        self.assertEqual(4644, metadata["height"])
        self.assertEqual(1145, metadata["coreModules"])
        self.assertEqual(1161, metadata["gridModules"])


if __name__ == "__main__":
    unittest.main()
