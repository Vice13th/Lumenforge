#!/usr/bin/env python3
"""Run offline-friendly LumenForge package, syntax, test, and render smoke gates."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import time
from pathlib import Path


def _run(label: str, command: list[str], cwd: Path, records: list[dict]) -> None:
    started = time.perf_counter()
    completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
    record = {
        "name": label,
        "command": command,
        "exit_code": completed.returncode,
        "duration_seconds": round(time.perf_counter() - started, 3),
        "stdout_tail": completed.stdout[-5000:],
        "stderr_tail": completed.stderr[-5000:],
    }
    records.append(record)
    print(f"[{label}] exit={completed.returncode} duration={record['duration_seconds']}s")
    if completed.stdout.strip():
        print(completed.stdout.strip()[-1600:])
    if completed.stderr.strip():
        print(completed.stderr.strip()[-1600:], file=sys.stderr)
    if completed.returncode:
        raise RuntimeError(f"{label} failed with exit code {completed.returncode}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--receipt-dir", type=Path, default=None)
    parser.add_argument("--skip-built-in-selftest", action="store_true",
                        help="skip the engine's in-app numerical regression suite")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    receipt_dir = (args.receipt_dir or (root / "build" / "smoke-receipt")).resolve()
    receipt_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []
    started_wall = time.time()
    try:
        _run("package-integrity", [sys.executable, "tools/verify_package.py", "--root", str(root)], root, records)
        _run("syntax-compile", [sys.executable, "-m", "compileall", "-q", "lumenforge", "tests", "tools"], root, records)
        _run("unit-tests", [sys.executable, "-m", "unittest", "discover", "tests", "-v"], root, records)

        render_code = r'''
import hashlib, json, numpy as np
from lumenforge import engine
image = np.linspace(0.0, 1.0, 48 * 32 * 3, dtype=np.float32).reshape(32, 48, 3)
result = engine.ENG.render(image, {}, changed_key=None)
arr = np.ascontiguousarray(result, dtype=np.float32)
if arr.shape != image.shape: raise SystemExit(f"shape mismatch: {arr.shape}")
if not np.isfinite(arr).all(): raise SystemExit("render contains non-finite values")
if float(arr.min()) < -1e-5 or float(arr.max()) > 1.00001: raise SystemExit("render outside normalized range")
print(json.dumps({"shape": list(arr.shape), "dtype": str(arr.dtype), "min": float(arr.min()), "max": float(arr.max()), "render_sha256": hashlib.sha256(arr.tobytes()).hexdigest()}, sort_keys=True))
'''
        result = subprocess.run([sys.executable, "-c", render_code], cwd=root, text=True, capture_output=True)
        record = {"name": "deterministic-render", "command": [sys.executable, "-c", "<embedded deterministic render check>"],
                  "exit_code": result.returncode, "stdout_tail": result.stdout[-3000:], "stderr_tail": result.stderr[-3000:]}
        records.append(record)
        if result.returncode:
            raise RuntimeError(f"deterministic-render failed: {result.stderr.strip()}")
        try:
            render_result = json.loads(result.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError) as exc:
            raise RuntimeError(f"deterministic-render produced invalid receipt output: {result.stdout!r}") from exc
        print("[deterministic-render]", json.dumps(render_result, sort_keys=True))

        if not args.skip_built_in_selftest:
            selftest_code = "from lumenforge.selftest import self_tests; failures=self_tests(); print('built-in self-test failures:', len(failures)); [print(f) for f in failures]; raise SystemExit(bool(failures))"
            _run("built-in-selftest", [sys.executable, "-c", selftest_code], root, records)

        receipt = {
            "schema_version": 1,
            "application": "LumenForge",
            "source_archive_sha256": "aa25cd65b6fc6e6aac29a7c59f460f167807f700590724b3357c94a6953cd354",
            "started_at_epoch": started_wall,
            "finished_at_epoch": time.time(),
            "environment": {"python": sys.version, "platform": platform.platform(), "implementation": platform.python_implementation()},
            "gates": records,
            "render": render_result,
            "status": "PASS",
            "limitations": ["This source smoke does not build or launch a Windows executable.",
                            "It does not establish clean-machine portability or exercise optional CUDA/OCIO/rawpy integrations."],
        }
        target = receipt_dir / "lumenforge_smoke_receipt.json"
        target.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"SMOKE PASS: {target}")
        return 0
    except Exception as exc:
        receipt = {
            "schema_version": 1, "application": "LumenForge", "status": "FAIL",
            "source_archive_sha256": "aa25cd65b6fc6e6aac29a7c59f460f167807f700590724b3357c94a6953cd354",
            "environment": {"python": sys.version, "platform": platform.platform()},
            "gates": records, "error": str(exc),
        }
        target = receipt_dir / "lumenforge_smoke_receipt.json"
        target.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"SMOKE FAIL: {exc}\nReceipt: {target}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
