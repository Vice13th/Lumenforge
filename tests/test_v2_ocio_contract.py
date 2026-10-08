import importlib.util
import os
import sys

import numpy as np
import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "source", "v2_ocio_contract.py")
_SPEC = importlib.util.spec_from_file_location("v2_ocio_contract", _SRC)
_M = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _M
_SPEC.loader.exec_module(_M)


_CONFIG_URI = "ocio://cg-config-latest"


def test_capabilities_report_explicit_unavailability_or_real_processors():
    caps = _M.processor_capabilities(
        src="ACEScg",
        display="sRGB - Display",
        view="ACES 2.0 - SDR 100 nits (Rec.709)",
        config_path=_CONFIG_URI,
    )
    assert isinstance(caps, dict)
    assert set(("available", "cpu", "gpu")) <= set(caps)
    if not caps["available"]:
        assert "unavailable" in caps["reason"].lower()
    else:
        assert caps["cpu"] is True


def test_describe_returns_real_display_view_catalog_when_available():
    desc = _M.describe(_CONFIG_URI)
    assert desc["available"] in (True, False)
    assert "displays" in desc
    if desc["available"]:
        assert "sRGB - Display" in desc["displays"]
        assert "ACES 2.0 - SDR 100 nits (Rec.709)" in desc["displays"]["sRGB - Display"]


def test_processor_rejects_unknown_display_or_view_when_ocio_available():
    if _M.load_ocio() is None:
        pytest.skip("PyOpenColorIO unavailable")
    with pytest.raises(ValueError):
        _M.build_processor(src="ACEScg", display="__missing__", view="__missing__", config_path=_CONFIG_URI)


def test_cpu_apply_rgb_has_expected_shape_and_finite_output_when_available():
    if _M.load_ocio() is None:
        pytest.skip("PyOpenColorIO unavailable")
    x = np.array([[[1.0, 0.18, 0.18]]], dtype=np.float32)
    y = _M.cpu_apply_rgb(
        x,
        src="ACEScg",
        display="sRGB - Display",
        view="ACES 2.0 - SDR 100 nits (Rec.709)",
        config_path=_CONFIG_URI,
    )
    assert y.shape == x.shape
    assert y.dtype == np.float32
    assert np.isfinite(y).all()
    expected = np.array([0.93178785, 0.2745979, 0.35344562], dtype=np.float32)
    assert np.max(np.abs(y[0, 0] - expected)) < 2e-5
