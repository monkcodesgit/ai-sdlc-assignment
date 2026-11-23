#!/usr/bin/env python3
"""Freeze src/, prompts/ and Spec Kit artifacts as evidence.

Usage:
    python .harness/snapshot.py initial   # right after /speckit.implement, BEFORE any repair
    python .harness/snapshot.py final     # after the harness is green
    python .harness/snapshot.py final --force   # overwrite an existing final snapshot

The 'initial' snapshot can never be overwritten: that is the point of it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COPY_DIRS = ["src", "prompts", "specs"]


def _git_commit() -> str | None:
    try:
        proc = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                              capture_output=True, text=True, check=False, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout.strip() if proc.returncode == 0 and proc.stdout.strip() else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("label", choices=["initial", "final"])
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    target = ROOT / "evidence" / f"{args.label}-generation"
    already = target.exists() and any(p.name != ".gitkeep" for p in target.iterdir())
    if already and (args.label == "initial" or not args.force):
        print(f"REFUSING: {target.relative_to(ROOT)} already has content "
              f"({'initial snapshots are immutable' if args.label == 'initial' else 'use --force'}).")
        return 1
    target.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, str] = {}
    for name in COPY_DIRS:
        source = ROOT / name
        if not source.exists():
            print(f"warning: {name}/ not found, skipped")
            continue
        dest = target / name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(source, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        for path in sorted(dest.rglob("*")):
            if path.is_file():
                manifest[path.relative_to(target).as_posix()] = hashlib.sha256(
                    path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()

    (target / "MANIFEST.json").write_text(json.dumps({
        "label": args.label,
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_commit": _git_commit(),
        "files": manifest,
    }, indent=2) + "\n", encoding="utf-8")
    print(f"Snapshot '{args.label}' written: {len(manifest)} files -> {target.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
