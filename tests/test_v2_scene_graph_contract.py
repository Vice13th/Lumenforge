import importlib.util
import os
import sys

import numpy as np
import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_FRAME = os.path.join(os.path.dirname(_HERE), "source", "v2_frame_contract.py")
_BRIDGE = os.path.join(os.path.dirname(_HERE), "source", "v2_scene_graph_contract.py")
for name, path in (("v2_frame_contract", _FRAME), ("v2_scene_graph_contract", _BRIDGE)):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
frame = sys.modules["v2_frame_contract"]
bridge = sys.modules["v2_scene_graph_contract"]


def test_scene_linear_required_and_identity_is_deterministic():
    f = frame.make_scene_linear(
        np.array([[[2.0, 0.1, 0.5]]], dtype=np.float32),
        primaries="AP1",
        white="ACES 0.32168/0.33767",
    )
    a = bridge.scene_linear_identity(f)
    b = bridge.scene_linear_identity(f)
    assert a == b
    assert len(a) == 64


def test_scene_identity_changes_when_frame_revision_changes():
    f = frame.make_scene_linear(np.ones((1, 1, 3), np.float32), primaries="AP1")
    f2 = f.next_revision(data=f.data + 0.25)
    assert bridge.scene_linear_identity(f) != bridge.scene_linear_identity(f2)


def test_graph_revision_and_backend_change_contract_key():
    f = frame.make_scene_linear(np.ones((1, 1, 3), np.float32), primaries="AP1")
    a = bridge.GraphIdentity("grade", revision=1, backend="cpu")
    b = bridge.GraphIdentity("grade", revision=2, backend="cpu")
    c = bridge.GraphIdentity("grade", revision=1, backend="cuda")
    assert bridge.graph_contract_key(f, [a]) != bridge.graph_contract_key(f, [b])
    assert bridge.graph_contract_key(f, [a]) != bridge.graph_contract_key(f, [c])


def test_display_referred_input_is_rejected():
    f = frame.make_camera_linear(np.zeros((1, 1, 3), np.float32))
    display = f.next_revision(color_space=frame.ColorSpace(
        "display", frame.ColorState.DISPLAY_REFERRED,
        primaries="sRGB", white="D65", transfer="sRGB", role="display"
    ))
    with pytest.raises(ValueError, match="SCENE_LINEAR"):
        bridge.require_scene_linear(display)


def test_finite_scene_linear_helper_rejects_invalid_data():
    with pytest.raises(ValueError, match="finite"):
        bridge.finite_scene_linear(np.array([[[np.nan, 0, 1]]], dtype=np.float32))
    with pytest.raises(ValueError, match="HxWx3"):
        bridge.finite_scene_linear(np.zeros((2, 2), dtype=np.float32))
