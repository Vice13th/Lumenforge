#!/usr/bin/env python3
"""Verify LumenForge's SHA256SUMS.txt as an exact package inventory.

The manifest excludes itself and common generated/cache directories. All other
regular files must be listed exactly once and must match their recorded SHA256.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath

MANIFEST_NAME = "SHA256SUMS.txt"
_DIGEST_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_EXCLUDED_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", ".tox", ".venv", "venv", "build", "dist", ".nox",
}
_EXCLUDED_SUFFIXES = {".pyc", ".pyo"}


def _is_excluded(relative_path: str) -> bool:
    path = PurePosixPath(relative_path)
    return any(part in _EXCLUDED_DIRS for part in path.parts) or path.suffix.lower() in _EXCLUDED_SUFFIXES


def _safe_relative_path(raw: str) -> str:
    if not raw or "\\" in raw or "\x00" in raw:
        raise ValueError(f"unsafe manifest path: {raw!r}")
    posix = PurePosixPath(raw)
    windows = PureWindowsPath(raw)
    if posix.is_absolute() or windows.is_absolute() or windows.drive:
        raise ValueError(f"absolute/drive-qualified manifest path: {raw!r}")
    if any(part in ("", ".", "..") for part in raw.split("/")):
        raise ValueError(f"unsafe path traversal or non-canonical path: {raw!r}")
    if posix.as_posix() != raw:
        raise ValueError(f"non-canonical manifest path: {raw!r}")
    return raw


def parse_manifest(text: str) -> dict[str, str]:
    """Parse strict ``<sha256><two spaces><relative path>`` manifest rows."""
    rows: dict[str, str] = {}
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        if len(line) < 67 or line[64:66] != "  ":
            raise ValueError(f"line {line_number}: expected 64-hex digest, two spaces, path")
        digest, raw_path = line[:64], line[66:]
        if not _DIGEST_RE.fullmatch(digest):
            raise ValueError(f"line {line_number}: invalid SHA256 digest")
        relative = _safe_relative_path(raw_path)
        if relative == MANIFEST_NAME:
            raise ValueError(f"line {line_number}: manifest must not list itself")
        if relative in rows:
            raise ValueError(f"line {line_number}: duplicate path {relative!r}")
        rows[relative] = digest.lower()
    if not rows:
        raise ValueError("manifest has no entries")
    return rows


def collect_inventory(root: Path, manifest_path: Path | None = None) -> dict[str, str]:
    """Return SHA256 values for all package files except the manifest and caches."""
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"package root is not a directory: {root}")
    inventory: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            relative = path.relative_to(root).as_posix()
            raise ValueError(f"symbolic links are not allowed in package inventory: {relative}")
        if path.is_dir():
            continue
        relative = path.relative_to(root).as_posix()
        if _is_excluded(relative):
            continue
        if manifest_path is not None and path.resolve() == manifest_path.resolve():
            continue
        _safe_relative_path(relative)
        inventory[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return inventory


def write_manifest(root: Path, manifest_path: Path | None = None) -> Path:
    root = root.resolve()
    target = (manifest_path or (root / MANIFEST_NAME)).resolve()
    if not target.is_relative_to(root):
        raise ValueError("manifest path must be inside the package root")
    inventory = collect_inventory(root, target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "".join(f"{digest.upper()}  {path}\n" for path, digest in sorted(inventory.items())),
        encoding="utf-8",
        newline="\n",
    )
    return target


def verify(root: Path, manifest_path: Path | None = None) -> list[str]:
    root = root.resolve()
    manifest = (manifest_path or (root / MANIFEST_NAME)).resolve()
    if not manifest.is_file():
        return [f"manifest is missing: {manifest}"]
    try:
        expected = parse_manifest(manifest.read_text(encoding="utf-8"))
        actual = collect_inventory(root, manifest)
    except (OSError, UnicodeError, ValueError) as exc:
        return [str(exc)]

    errors: list[str] = []
    for path in sorted(expected.keys() - actual.keys()):
        errors.append(f"missing file: {path}")
    for path in sorted(actual.keys() - expected.keys()):
        errors.append(f"unmanifested file: {path}")
    for path in sorted(expected.keys() & actual.keys()):
        if expected[path] != actual[path]:
            errors.append(f"SHA256 mismatch: {path} (expected {expected[path]}, actual {actual[path]})")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1],
                        help="package root directory (default: project root)")
    parser.add_argument("--manifest", type=Path, default=None,
                        help="manifest path; absolute or relative to --root")
    parser.add_argument("--write-manifest", action="store_true",
                        help="regenerate SHA256SUMS.txt instead of verifying it")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    manifest = args.manifest
    if manifest is not None and not manifest.is_absolute():
        manifest = root / manifest
    try:
        if args.write_manifest:
            target = write_manifest(root, manifest)
            count = len(parse_manifest(target.read_text(encoding="utf-8")))
            print(f"OK: wrote {count} SHA256 entries to {target}")
            return 0
        errors = verify(root, manifest)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        print(f"Package verification failed ({len(errors)} issue(s)).", file=sys.stderr)
        return 1
    count = len(parse_manifest((manifest or root / MANIFEST_NAME).read_text(encoding="utf-8")))
    print(f"OK: exact package inventory verified ({count} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
