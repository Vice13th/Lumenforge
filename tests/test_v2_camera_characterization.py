import importlib.util
import os
import sys

import numpy as np
import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "source", "v2_camera_characterization.py")
_SPEC = importlib.util.spec_from_file_location("v2_camera_characterization", _SRC)
_M = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _M
_SPEC.loader.exec_module(_M)


def test_ciede2000_reference_identity_and_known_zero():
    lab = np.array([[50.0, 0.0, 0.0]], dtype=np.float64)
    d = _M.ciede2000(lab, lab)
    assert d.shape == (1,)
    assert float(d[0]) == pytest.approx(0.0, abs=1e-12)


def test_matrix_fit_holdout_receipt_preserves_infrastructure_only_status():
    rng = np.random.default_rng(20261008)
    rgb = rng.uniform(0.01, 1.0, size=(24, 3))
    truth = np.array([[0.9, 0.05, 0.02], [0.03, 0.8, 0.06], [0.01, 0.04, 0.95]], dtype=np.float64)
    xyz = rgb @ truth
    receipt = _M.fit_and_evaluate(rgb, xyz, model="matrix3", holdout_indices_=np.arange(18, 24))
    assert receipt.train_count == 18
    assert receipt.holdout_count == 6
    assert receipt.scientific_gate_status == "infrastructure_only"
    assert receipt.train_metrics["all_finite"] is True
    assert receipt.holdout_metrics["all_finite"] is True
    assert len(receipt.matrix_sha256) == 64


def test_root_polynomial_basis_shape_and_deterministic_hash():
    rgb = np.array([[0.1, 0.2, 0.3], [0.7, 0.5, 0.2], [0.9, 0.1, 0.4], [0.2, 0.8, 0.6], [0.4, 0.3, 0.9], [0.6, 0.7, 0.1], [0.35, 0.55, 0.45]], dtype=np.float64)
    xyz = np.stack([rgb[:, 0] + 0.1 * rgb[:, 1], rgb[:, 1] + 0.1 * rgb[:, 2], rgb[:, 2] + 0.1 * rgb[:, 0]], axis=1)
    basis = _M.root_polynomial_degree2(rgb)
    assert basis.shape == (7, 6)
    r1 = _M.fit_and_evaluate(rgb, xyz, model="root_poly2", holdout_indices_=np.array([5]))
    r2 = _M.fit_and_evaluate(rgb, xyz, model="root_poly2", holdout_indices_=np.array([5]))
    assert r1.matrix_sha256 == r2.matrix_sha256


def test_negative_root_polynomial_input_is_rejected():
    with pytest.raises(ValueError, match="non-negative"):
        _M.root_polynomial_degree2(np.array([[0.1, -0.1, 0.2]], dtype=np.float64))
