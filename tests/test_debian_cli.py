"""Safe, dependency-free tests for the Debian deploy helper."""
import importlib.util
import io
import tarfile
import tempfile
import unittest
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "packaging/debian/it_guardian_cli.py"
spec = importlib.util.spec_from_file_location("guardian_cli", PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class SafeArchiveTests(unittest.TestCase):
    def test_safe_bundle(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            bundle = root / "ok.tar.gz"
            with tarfile.open(bundle, "w:gz") as t:
                item = tarfile.TarInfo("compose.yaml")
                data = b"name: it-guardian\nservices: {}\n"
                item.size = len(data)
                t.addfile(item, io.BytesIO(data))
            dest = root / "dest"
            dest.mkdir()
            module.safe_extract(bundle, dest)
            self.assertTrue((dest / "compose.yaml").exists())

    def test_reject_traversal(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            bundle = root / "bad.tar.gz"
            with tarfile.open(bundle, "w:gz") as t:
                item = tarfile.TarInfo("../outside")
                item.size = 1
                t.addfile(item, io.BytesIO(b"x"))
            dest = root / "dest"
            dest.mkdir()
            with self.assertRaises(ValueError):
                module.safe_extract(bundle, dest)
            self.assertFalse((root / "outside").exists())

    def test_reject_symlink(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            bundle = root / "link.tar.gz"
            with tarfile.open(bundle, "w:gz") as t:
                item = tarfile.TarInfo("escape")
                item.type = tarfile.SYMTYPE
                item.linkname = "/etc/passwd"
                t.addfile(item)
            dest = root / "dest"
            dest.mkdir()
            with self.assertRaises(ValueError):
                module.safe_extract(bundle, dest)

if __name__ == "__main__":
    unittest.main()
