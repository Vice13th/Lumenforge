import importlib.util
import os
import sys

import numpy as np
import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "source", "v2_cuda_lut.py")
_SPEC = importlib.util.spec_from_file_location("v2_cuda_lut", _SRC)
_M = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _M
_SPEC.loader.exec_module(_M)


def cpu_tetrahedral(rgb, lut3d):
    x = np.asarray(rgb, np.float32)
    tbl, dmin, dmax = lut3d
    out = np.empty_like(x)
    n = tbl.shape[0]
    span = np.maximum(np.asarray(dmax, np.float32) - np.asarray(dmin, np.float32), 1e-12)
    flat = x.reshape(-1, 3)
    dst = out.reshape(-1, 3)
    for p, v in enumerate(flat):
        q = np.clip((v - dmin) / span, 0.0, 1.0) * (n - 1)
        i = np.floor(q).astype(int)
        f = q - i
        i = np.minimum(i, n - 2)
        r, g, b = f
        ir, ig, ib = i
        base = ((ir*n + ig)*n + ib)
        def V(a, c): return tbl[a][c]
        v000=tbl[ir,ig,ib]; v100=tbl[ir+1,ig,ib]; v010=tbl[ir,ig+1,ib]; v001=tbl[ir,ig,ib+1]
        v110=tbl[ir+1,ig+1,ib]; v101=tbl[ir+1,ig,ib+1]; v011=tbl[ir,ig+1,ib+1]; v111=tbl[ir+1,ig+1,ib+1]
        if r >= g and g >= b:
            y=v000+r*(v100-v000)+g*(v110-v100)+b*(v111-v110)
        elif r >= b and b >= g:
            y=v000+r*(v100-v000)+b*(v101-v100)+g*(v111-v101)
        elif g >= r and r >= b:
            y=v000+g*(v010-v000)+r*(v110-v010)+b*(v111-v110)
        elif g >= b and b >= r:
            y=v000+g*(v010-v000)+b*(v011-v010)+r*(v111-v011)
        elif b >= r and r >= g:
            y=v000+b*(v001-v000)+r*(v101-v001)+g*(v111-v101)
        else:
            y=v000+b*(v001-v000)+g*(v011-v001)+r*(v111-v011)
        dst[p]=y
    return out


def test_backend_exposes_explicit_availability():
    assert isinstance(_M.available(), bool)
    assert isinstance(_M.device_info(), dict)


def test_cuda_matches_reference_on_measured_runtime():
    if not _M.available():
        pytest.skip("CUDA runtime unavailable")
    rng = np.random.default_rng(20261008)
    n = 17
    lut = rng.random((n, n, n, 3), dtype=np.float32)
    probe = rng.uniform(-0.5, 1.5, size=(96, 113, 3)).astype(np.float32)
    dmin = np.array([-0.25, -0.25, -0.25], dtype=np.float32)
    dmax = np.array([1.25, 1.25, 1.25], dtype=np.float32)
    expected = cpu_tetrahedral(probe, (lut, dmin, dmax))
    actual = _M.tetrahedral_cuda(probe, (lut, dmin, dmax))
    err = float(np.max(np.abs(actual - expected)))
    rms = float(np.sqrt(np.mean((actual - expected) ** 2)))
    assert np.isfinite(actual).all()
    assert err <= 2e-5
    assert rms <= 2e-5
