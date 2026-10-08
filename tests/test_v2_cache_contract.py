import importlib.util
import os
import sys
import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "source", "v2_cache_contract.py")
_SPEC = importlib.util.spec_from_file_location("v2_cache_contract", _SRC)
_M = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _M
_SPEC.loader.exec_module(_M)


def test_parameter_digest_is_order_independent():
    a = {"exposure": 1, "contrast": 2, "mask": {"b": 2, "a": 1}}
    b = {"mask": {"a": 1, "b": 2}, "contrast": 2, "exposure": 1}
    assert _M.parameter_digest(a, ["exposure", "contrast", "mask"]) == _M.parameter_digest(b, ["exposure", "contrast", "mask"])


def test_parameter_digest_changes_when_relevant_value_changes():
    a = {"exposure": 1.0, "contrast": 2.0}
    b = {"exposure": 1.25, "contrast": 2.0}
    assert _M.parameter_digest(a, ["exposure", "contrast"]) != _M.parameter_digest(b, ["exposure", "contrast"])


def test_cache_contract_key_changes_for_revision_source_tile_quality_color_backend():
    kw = dict(source_fingerprint="src", node_id="tone", node_revision=1, upstream_revision=2,
              tile=(0, 0, 16, 16), quality="preview", color_state="scene-linear", backend="cpu")
    base = _M.cache_contract_key(**kw)
    assert base != _M.cache_contract_key(**{**kw, "node_revision": 2})
    assert base != _M.cache_contract_key(**{**kw, "upstream_revision": 3})
    assert base != _M.cache_contract_key(**{**kw, "source_fingerprint": "src2"})
    assert base != _M.cache_contract_key(**{**kw, "tile": (16, 0, 16, 16)})
    assert base != _M.cache_contract_key(**{**kw, "quality": "export"})
    assert base != _M.cache_contract_key(**{**kw, "color_state": "display-referred"})
    assert base != _M.cache_contract_key(**{**kw, "backend": "cuda"})


def test_numpy_scalars_are_canonicalized():
    a = {"x": np.float32(1.5), "y": np.int64(4)}
    b = {"x": 1.5, "y": 4}
    assert _M.parameter_digest(a, ["x", "y"]) == _M.parameter_digest(b, ["x", "y"])
