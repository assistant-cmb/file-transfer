import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class InteroperabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("node"):
            raise unittest.SkipTest("Node.js is not installed")

    def run_json(self, command, cwd):
        result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=True)
        return json.loads(result.stdout)

    def test_bidirectional_cli_compatibility(self):
        with tempfile.TemporaryDirectory(prefix="file-transfer-") as temp:
            temp = Path(temp)
            source = temp / "跨语言 sample.bin"
            payload = bytes(range(256)) * 17 + "文件互操作\n".encode()
            source.write_bytes(payload)

            python_png = temp / "python.png"
            node_output = temp / "node-recovered.bin"
            self.run_json(
                [sys.executable, "-m", "file_transfer", "encode", str(source), "-o", str(python_png), "--json"],
                ROOT / "python-version",
            )
            inspected_by_node = self.run_json(
                ["node", "src/cli.js", "inspect", str(python_png), "--json"],
                ROOT / "node-version",
            )
            self.run_json(
                ["node", "src/cli.js", "decode", str(python_png), "-o", str(node_output), "--json"],
                ROOT / "node-version",
            )
            self.assertEqual(source.name, inspected_by_node["filename"])
            self.assertEqual(payload, node_output.read_bytes())

            node_png = temp / "node.png"
            python_output = temp / "python-recovered.bin"
            self.run_json(
                ["node", "src/cli.js", "encode", str(source), "-o", str(node_png), "--json"],
                ROOT / "node-version",
            )
            inspected_by_python = self.run_json(
                [sys.executable, "-m", "file_transfer", "inspect", str(node_png), "--json"],
                ROOT / "python-version",
            )
            self.run_json(
                [sys.executable, "-m", "file_transfer", "decode", str(node_png), "-o", str(python_output), "--json"],
                ROOT / "python-version",
            )
            self.assertEqual(source.name, inspected_by_python["filename"])
            self.assertEqual(payload, python_output.read_bytes())
            self.assertEqual(inspected_by_node["sha256"], inspected_by_python["sha256"])

    def test_bidirectional_jpeg_v2_compatibility(self):
        try:
            from PIL import Image
        except ImportError:
            raise unittest.SkipTest("Pillow is not installed")
        node_probe = subprocess.run(
            ["node", "-e", "require('sharp')"],
            cwd=ROOT / "node-version",
            capture_output=True,
        )
        if node_probe.returncode:
            raise unittest.SkipTest("sharp is not installed")

        with tempfile.TemporaryDirectory(prefix="file-transfer-v2-") as temp:
            temp = Path(temp)
            source = temp / "跨语言-v2.zip"
            payload = bytes((index * 37 + 17) & 0xFF for index in range(4096))
            source.write_bytes(payload)

            python_jpg = temp / "python.jpg"
            node_output = temp / "node-v2.zip"
            self.run_json(
                [sys.executable, "-m", "file_transfer", "encode", str(source), "--format", "jpeg", "-o", str(python_jpg), "--json"],
                ROOT / "python-version",
            )
            python_transferred = temp / "python-transferred.jpg"
            subprocess.run(
                [
                    "node", "-e",
                    "const s=require('sharp');const [i,o]=process.argv.slice(1);s(i).metadata().then(m=>s(i).resize(Math.round(m.width*.82),Math.round(m.height*.82)).jpeg({quality:82}).toFile(o));",
                    str(python_jpg), str(python_transferred),
                ],
                cwd=ROOT / "node-version",
                check=True,
            )
            inspected_by_node = self.run_json(
                ["node", "src/cli.js", "inspect", str(python_transferred), "--json"],
                ROOT / "node-version",
            )
            self.run_json(
                ["node", "src/cli.js", "decode", str(python_transferred), "-o", str(node_output), "--json"],
                ROOT / "node-version",
            )
            self.assertEqual(payload, node_output.read_bytes())

            node_jpg = temp / "node.jpg"
            python_output = temp / "python-v2.zip"
            self.run_json(
                ["node", "src/cli.js", "encode", str(source), "--format", "jpeg", "-o", str(node_jpg), "--json"],
                ROOT / "node-version",
            )
            node_transferred = temp / "node-transferred.jpg"
            with Image.open(node_jpg) as image:
                side = round(image.width * 0.82)
                image.resize((side, side), Image.Resampling.BILINEAR).save(node_transferred, "JPEG", quality=82)
            inspected_by_python = self.run_json(
                [sys.executable, "-m", "file_transfer", "inspect", str(node_transferred), "--json"],
                ROOT / "python-version",
            )
            self.run_json(
                [sys.executable, "-m", "file_transfer", "decode", str(node_transferred), "-o", str(python_output), "--json"],
                ROOT / "python-version",
            )
            self.assertEqual(payload, python_output.read_bytes())
            self.assertEqual(inspected_by_node["sha256"], inspected_by_python["sha256"])


if __name__ == "__main__":
    unittest.main()
