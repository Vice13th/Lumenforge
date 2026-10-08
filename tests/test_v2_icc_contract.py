import importlib.util
import os
import sys

import numpy as np
import pytest
from PIL import ImageCms

_HERE = os.path.dirname(os.path.abspath(__file__))
_FRAME = os.path.join(os.path.dirname(_HERE), "source", "v2_frame_contract.py")
_ICC = os.path.join(os.path.dirname(_HERE), "source", "v2_icc_contract.py")
for name, path in (("v2_frame_contract", _FRAME), ("v2_icc_contract", _ICC)):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
frame = sys.modules["v2_frame_contract"]
icc = sys.modules["v2_icc_contract"]


def profile():
    return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


def display_frame():
    return frame.V2Frame(
        np.array([[[0.0, 0.25, 1.0], [0.5, 0.75, 1.0]], [[0.1, 0.2, 0.3], [1.0, 0.0, 0.5]]], dtype=np.float32),
        frame.ColorSpace("sRGB display", frame.ColorState.DISPLAY_REFERRED,
                         primaries="sRGB", white="D65", transfer="sRGB", role="display"),
        metadata=frame.FrameMetadata(source_fingerprint="abc123", path="fixture.jpg"),
        revision=4,
    )


def test_explicit_display_referred_icc_roundtrip_preserves_contract():
    p = profile()
    out, receipt = icc.convert_display_referred_rgb(display_frame(), p, p)
    assert out.revision == 5
    assert out.metadata.source_fingerprint == "abc123"
    assert out.color_space.state is frame.ColorState.DISPLAY_REFERRED
    assert np.max(np.abs(out.rgb - display_frame().rgb)) <= 1.0 / 255.0
    assert receipt["source_fingerprint"] == "abc123"
    assert receipt["revision"] == 5
    assert receipt["source_profile_sha256"] == icc.profile_sha256(p)
    assert receipt["destination_profile_sha256"] == icc.profile_sha256(p)


def test_invalid_profile_is_rejected():
    with pytest.raises(ValueError, match="too small"):
        icc.validate_profile(b"invalid")


def test_scene_linear_input_is_rejected():
    f = frame.make_scene_linear(np.ones((1, 1, 3), dtype=np.float32), primaries="AP1")
    p = profile()
    with pytest.raises(ValueError, match="display-referred"):
        icc.convert_display_referred_rgb(f, p, p)
