#!/usr/bin/env python3
"""IT Guardian host CLI. Only operates on its own /opt/it-guardian Compose project."""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

APP = Path("/opt/it-guardian")
CONFIG = Path("/etc/it-guardian")
ENV = CONFIG / "guardian.env"
BUNDLE = Path("/usr/share/it-guardian/source.tar.gz")
PROJECT = "it-guardian"

def execute(cmd, *, capture=False):
    return subprocess.run(cmd, check=True, text=True, capture_output=capture)

def require_root():
    if os.geteuid() != 0:
        raise SystemExit("This operation requires root (sudo).")

def compose(*args):
    if not APP.joinpath("compose.yaml").is_file():
        raise RuntimeError("Not installed: /opt/it-guardian/compose.yaml")
    if not ENV.is_file():
        raise RuntimeError("Missing /etc/it-guardian/guardian.env; configure secrets first")
    return execute(["docker", "compose", "-p", PROJECT, "--project-directory", str(APP),
                    "--env-file", str(ENV), "-f", str(APP / "compose.yaml"), *args])

def doctor():
    checks = {"docker": bool(shutil.which("docker")),
              "compose_file": (APP / "compose.yaml").is_file(),
              "config_exists": ENV.is_file(),
              "config_mode_private": ENV.is_file() and ENV.stat().st_mode & 0o077 == 0,
              "payload": BUNDLE.is_file()}
    if checks["docker"]:
        try:
            execute(["docker", "compose", "version"], capture=True)
            checks["compose_v2"] = True
        except (OSError, subprocess.CalledProcessError):
            checks["compose_v2"] = False
    print(json.dumps(checks, indent=2, sort_keys=True))
    return all(checks.values())

def safe_extract(bundle, dest):
    # Never extract paths outside destination or follow archive links.
    with tarfile.open(bundle, "r:gz") as archive:
        members = archive.getmembers()
        if len(members) > 100000:
            raise ValueError("Archive contains too many entries")
        for member in members:
            path = Path(member.name)
            if path.is_absolute() or ".." in path.parts or not (member.isfile() or member.isdir()):
                raise ValueError("Unsafe archive entry: " + member.name)
        archive.extractall(dest, members=members, filter="data")

def install():
    require_root()
    if not BUNDLE.is_file():
        raise RuntimeError("Debian source payload missing")
    CONFIG.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not ENV.exists():
        raise RuntimeError("Create /etc/it-guardian/guardian.env with production secrets; no default credentials are allowed")
    if ENV.stat().st_mode & 0o077:
        raise RuntimeError("guardian.env must be private (chmod 600)")
    env_text = ENV.read_text(encoding="utf-8")
    if "replace-with-" in env_text or "ci-password" in env_text:
        raise RuntimeError("Refusing example/CI credentials in guardian.env")
    if not shutil.which("docker"):
        raise RuntimeError("Docker Engine and Compose v2 required; no global Docker changes made")
    execute(["docker", "compose", "version"], capture=True)
    # Copy in a fresh staging directory, preserving previous deployment on failure.
    APP.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".guardian-stage-", dir=str(APP.parent)) as stage:
        staged = Path(stage)
        safe_extract(BUNDLE, staged)
        if not (staged / "compose.yaml").is_file():
            raise RuntimeError("Missing Compose model in package")
        execute(["docker", "compose", "-p", PROJECT, "--project-directory", str(staged),
                 "--env-file", str(ENV), "-f", str(staged / "compose.yaml"), "config"], capture=True)
        if APP.exists():
            backup = APP.with_name(APP.name + ".previous")
            if backup.exists():
                raise RuntimeError("Previous deployment backup exists: " + str(backup) + "; resolve before reinstall")
            APP.rename(backup)
        staged.rename(APP)
    print("Source deployed. Start explicitly with: sudo it-guardian up")
    print("Previous deployment, if any: /opt/it-guardian.previous")

def backup(destination):
    require_root()
    # Host config only. Database backup requires a separate verified PostgreSQL dump workflow.
    target = Path(destination).resolve()
    if target.exists():
        raise RuntimeError("Backup destination already exists")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(target, "w:gz") as archive:
        if ENV.exists():
            archive.add(ENV, arcname="guardian.env", recursive=False)
    os.chmod(target, 0o600)
    print("Configuration backup saved (NOT a PostgreSQL data backup):", target)

def main():
    parser = argparse.ArgumentParser(prog="it-guardian")
    sub = parser.add_subparsers(dest="action", required=True)
    for name in ("doctor", "install", "up", "down", "status", "verify", "logs", "config"):
        sub.add_parser(name)
    sub.add_parser("backup-config").add_argument("destination")
    args = parser.parse_args()
    try:
        if args.action == "doctor":
            sys.exit(0 if doctor() else 1)
        if args.action == "install":
            install()
        elif args.action == "backup-config":
            backup(args.destination)
        else:
            require_root()
            if args.action == "up":
                compose("up", "-d", "--build")
            elif args.action == "down":
                compose("down") # Never deletes volumes
            elif args.action == "status":
                compose("ps")
            elif args.action == "verify":
                compose("config", "--quiet")
                compose("ps")
            elif args.action == "logs":
                compose("logs", "--tail", "100", "--no-color")
            elif args.action == "config":
                compose("config", "--quiet")
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"it-guardian: {exc}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
