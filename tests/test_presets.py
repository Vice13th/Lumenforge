"""Preset library quality gate: python -m unittest discover tests"""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lumenforge import engine
from preset_qa import audit

INTENTIONAL = {"Day-for-Night"}


class PresetQuality(unittest.TestCase):
    def test_library_has_no_defects(self):
        bad = [(n, m) for n, m in audit(engine.PRES) if n not in INTENTIONAL]
        self.assertEqual(bad, [])

    def test_modern_looks_present_and_distinct(self):
        modern = [p for p in engine.PRES if p.get("process") == "Modern Look"]
        self.assertGreaterEqual(len(modern), 30)
        self.assertGreaterEqual(len({p["family"] for p in modern}), 7)


if __name__ == "__main__":
    unittest.main()
