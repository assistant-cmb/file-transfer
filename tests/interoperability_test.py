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


if __name__ == "__main__":
    unittest.main()
