#!/usr/bin/env python3
"""Build an architecture-independent Debian package with audited repository source."""
import argparse
import os
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXCLUDED = {".git", ".env", "node_modules", ".venv", "__pycache__", "dist", "build", "coverage", ".pytest_cache", ".next", "artifacts", "downloads", "playwright-report", "test-results"}
VERSION = "0.8.1"

def include(path):
    rel = path.relative_to(ROOT)
    return not any(part in EXCLUDED or part.startswith(".env.") for part in rel.parts)

def build(output):
    if not shutil.which("dpkg-deb"):
        raise SystemExit("dpkg-deb required; run this builder on Debian/Ubuntu")
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="guardian-deb-") as temp:
        stage = Path(temp) / "it-guardian"
        (stage / "DEBIAN").mkdir(parents=True)
        (stage / "usr/bin").mkdir(parents=True)
        (stage / "usr/share/it-guardian").mkdir(parents=True)
        (stage / "etc/it-guardian").mkdir(parents=True)
        control = ("Package: it-guardian\nVersion: " + VERSION +
                   "\nSection: admin\nPriority: optional\nArchitecture: all\n"
                   "Maintainer: IT Guardian maintainers\nDepends: python3 (>= 3.11), tar\n"
                   "Description: Self-hosted IT Guardian administration and deployment CLI\n")
        (stage / "DEBIAN/control").write_text(control)
        shutil.copy2(ROOT / "packaging/debian/it_guardian_cli.py", stage / "usr/bin/it-guardian")
        (stage / "usr/bin/it-guardian").chmod(0o755)
        (stage / "etc/it-guardian/README").write_text(
            "Create guardian.env from source .env.example with strong unique secrets.\n"
            "Set owner root and chmod 600 before sudo it-guardian install.\n")
        with tarfile.open(stage / "usr/share/it-guardian/source.tar.gz", "w:gz", format=tarfile.PAX_FORMAT) as archive:
            for path in sorted(ROOT.rglob("*")):
                if path.is_file() and not path.is_symlink() and include(path):
                    arcname = path.relative_to(ROOT).as_posix()
                    info = archive.gettarinfo(str(path), arcname=arcname)
                    info.uid = info.gid = 0
                    info.uname = info.gname = "root"
                    info.mtime = 0
                    with open(path, "rb") as source:
                        archive.addfile(info, source)
        dest = output / f"it-guardian_{VERSION}_all.deb"
        subprocess.run(["dpkg-deb", "--build", "--root-owner-group", str(stage), str(dest)], check=True)
        subprocess.run(["dpkg-deb", "--info", str(dest)], check=True)
        print(dest)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="artifacts")
    build(Path(parser.parse_args().output_dir).resolve())
