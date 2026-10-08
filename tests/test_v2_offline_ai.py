import importlib.util
import os
import sys
import time
from pathlib import Path

import numpy as np
import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "source", "v2_offline_ai.py")
_SPEC = importlib.util.spec_from_file_location("v2_offline_ai", _SRC)
_M = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _M
_SPEC.loader.exec_module(_M)

MODEL_DIR = Path(r"C:\Users\Amirs\.cache\huggingface\hub\models--sentence-transformers--all-MiniLM-L6-v2\snapshots\1110a243fdf4706b3f48f1d95db1a4f5529b4d41")
MODEL_SHA = "6fd5d72fe4589f189f8ebc006442dbb529bb7ce38f8082112682524616046452"
TOKENIZER_SHA = "be50c3628f2bf5bb5e3a7f17b1f74611b2561a3a27eeab05e5aa30f411572037"


def test_local_model_identity_and_determinism():
    if not MODEL_DIR.exists():
        pytest.skip("authoritative local model cache unavailable on this runtime")
    enc = _M.LocalSentenceEncoder(MODEL_DIR)
    t0 = time.perf_counter()
    a = enc.encode(["LumenForge offline inference", "scene linear color", "deterministic test"], max_length=128)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    b = enc.encode(["LumenForge offline inference", "scene linear color", "deterministic test"], max_length=128)
    assert enc.provider == "CPUExecutionProvider"
    assert enc._sha256(enc.model_path) == MODEL_SHA
    assert enc._sha256(enc.tokenizer_path) == TOKENIZER_SHA
    assert a.shape == (3, 384)
    assert np.isfinite(a).all()
    assert np.allclose(np.linalg.norm(a, axis=1), 1.0, atol=1e-6)
    assert np.array_equal(a, b)
    receipt = enc.receipt(3, 128, a.shape[1], elapsed_ms)
    assert receipt.local_only is True
    assert receipt.network_required is False
