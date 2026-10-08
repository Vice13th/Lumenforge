import importlib.util
import os
import sys

import numpy as np
import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "source", "v2_frame_contract.py")
_SPEC = importlib.util.spec_from_file_location("v2_frame_contract", _SRC)
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)

ColorState = _MODULE.ColorState
FrameMetadata = _MODULE.FrameMetadata
PixelFormat = _MODULE.PixelFormat
make_camera_linear = _MODULE.make_camera_linear
make_scene_linear = _MODULE.make_scene_linear


def test_camera_linear_contract_and_headroom():
    rgb = np.array([[[2.0, 0.25, 0.5]]], dtype=np.float32)
    f = make_camera_linear(rgb, metadata=FrameMetadata(path="fixture.raf"))
    assert f.color_space.state is ColorState.CAMERA_LINEAR
    assert f.color_space.is_scene_linear
    assert f.validate_scene_headroom()
    assert f.pixel_format is PixelFormat.F32
    assert f.metadata.path == "fixture.raf"


def test_scene_linear_contract_allows_values_above_one_without_clipping():
    rgb = np.array([[[3.0, 1.5, 0.0]]], dtype=np.float32)
    f = make_scene_linear(rgb, primaries="AP1", white="ACES 0.32168/0.33767")
    assert f.color_space.state is ColorState.SCENE_LINEAR
    assert f.color_space.primaries == "AP1"
    assert float(f.rgb.max()) == pytest.approx(3.0)
    assert f.validate_scene_headroom()


def test_revision_and_fingerprint_are_stable():
    rgb = np.ones((2, 2, 3), dtype=np.float32)
    f = make_camera_linear(rgb)
    fp1 = f.source_fingerprint()
    f2 = f.next_revision(data=rgb * 2.0)
    assert f.revision == 0
    assert f2.revision == 1
    assert fp1 != f2.source_fingerprint()


def test_nonfinite_and_wrong_shape_are_rejected():
    with pytest.raises(ValueError, match="non-finite"):
        make_camera_linear(np.array([[[np.nan, 0.0, 0.0]]], dtype=np.float32))
    with pytest.raises(ValueError, match="HxWx3 or HxWx4"):
        make_camera_linear(np.zeros((3, 3), dtype=np.float32))


def test_display_referred_is_not_accepted_as_scene_headroom():
    f = make_camera_linear(np.zeros((1, 1, 3), dtype=np.float32))
    display = f.next_revision(color_space=f.color_space.__class__(
        "sRGB display", ColorState.DISPLAY_REFERRED, primaries="sRGB", white="D65", transfer="sRGB", role="display"
    ))
    with pytest.raises(ValueError, match="Scene headroom"):
        display.validate_scene_headroom()
