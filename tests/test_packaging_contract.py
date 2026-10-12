"""Regression tests for exact inventory verification and unsafe manifest paths."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.verify_package import parse_manifest, verify, write_manifest


class PackageContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "lumenforge").mkdir()
        (self.root / "lumenforge" / "__init__.py").write_text('"""fixture"""\n', encoding="utf-8")
        (self.root / "pyproject.toml").write_text("[project]\nname='fixture'\n", encoding="utf-8")
        write_manifest(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_exact_inventory_passes(self):
        self.assertEqual(verify(self.root), [])

    def test_changed_file_fails(self):
        (self.root / "pyproject.toml").write_text("changed\n", encoding="utf-8")
        self.assertTrue(any("SHA256 mismatch: pyproject.toml" in e for e in verify(self.root)))

    def test_unmanifested_file_fails(self):
        (self.root / "unexpected.txt").write_text("extra\n", encoding="utf-8")
        self.assertTrue(any("unmanifested file: unexpected.txt" == e for e in verify(self.root)))

    def test_missing_file_fails(self):
        (self.root / "lumenforge" / "__init__.py").unlink()
        self.assertTrue(any("missing file: lumenforge/__init__.py" == e for e in verify(self.root)))

    def test_duplicate_paths_are_rejected(self):
        digest = "0" * 64
        with self.assertRaisesRegex(ValueError, "duplicate path"):
            parse_manifest(f"{digest}  alpha\n{digest}  alpha\n")

    def test_windows_and_traversal_paths_are_rejected(self):
        for path in ("../escape", "C:/escape", "folder\\escape", "/absolute/path"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                parse_manifest(f"{'0' * 64}  {path}\n")

    def test_manifest_cannot_hash_itself(self):
        with self.assertRaisesRegex(ValueError, "must not list itself"):
            parse_manifest(f"{'0' * 64}  SHA256SUMS.txt\n")


if __name__ == "__main__":
    unittest.main()
