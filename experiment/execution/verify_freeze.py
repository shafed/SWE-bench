#!/usr/bin/env python3
"""Verify the frozen v4 experimental inputs before a main-series run."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "experiment" / "execution" / "FREEZE_V4.json"


def git_blob_sha1(path: Path) -> str:
    data = path.read_bytes()
    header = f"blob {len(data)}\0".encode()
    return hashlib.sha1(header + data).hexdigest()


def main() -> int:
    if not MANIFEST.exists():
        print(f"missing freeze manifest: {MANIFEST}", file=sys.stderr)
        return 1

    try:
        manifest = json.loads(MANIFEST.read_text())
    except Exception as exc:
        print(f"invalid freeze manifest: {exc}", file=sys.stderr)
        return 1

    if manifest.get("version") != "v4":
        print("freeze manifest version is not v4", file=sys.stderr)
        return 1
    if manifest.get("hash_algorithm") != "git-blob-sha1":
        print("unsupported freeze hash algorithm", file=sys.stderr)
        return 1

    entries = manifest.get("files")
    if not isinstance(entries, list) or not entries:
        print("freeze manifest has no files", file=sys.stderr)
        return 1

    errors: list[str] = []
    seen: set[str] = set()
    for entry in entries:
        rel = entry.get("path") if isinstance(entry, dict) else None
        expected = entry.get("git_blob_sha1") if isinstance(entry, dict) else None
        if not isinstance(rel, str) or not isinstance(expected, str):
            errors.append(f"malformed entry: {entry!r}")
            continue
        if rel in seen:
            errors.append(f"duplicate manifest path: {rel}")
            continue
        seen.add(rel)
        path = ROOT / rel
        if not path.is_file():
            errors.append(f"missing: {rel}")
            continue
        actual = git_blob_sha1(path)
        if actual != expected:
            errors.append(f"changed: {rel} expected {expected} got {actual}")

    if errors:
        print("v4 freeze verification FAILED:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(f"v4 freeze manifest OK: {len(entries)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
