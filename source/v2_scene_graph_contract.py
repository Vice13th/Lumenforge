"""Bridge recovered scene-linear/graph contracts into the existing V2 engine.

The V2 engine already owns execution. This adapter only provides deterministic
state and graph descriptors derived from the recovered LumenParallel contracts.
"""
from dataclasses import dataclass
from enum import Enum
import hashlib
import json

import importlib.util
import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_FRAME_PATH = os.path.join(_HERE, "v2_frame_contract.py")
_FRAME_SPEC = importlib.util.spec_from_file_location("v2_frame_contract", _FRAME_PATH)
_FRAME_MODULE = sys.modules.get("v2_frame_contract")
if _FRAME_MODULE is None:
    _FRAME_MODULE = importlib.util.module_from_spec(_FRAME_SPEC)
    sys.modules[_FRAME_SPEC.name] = _FRAME_MODULE
    _FRAME_SPEC.loader.exec_module(_FRAME_MODULE)
ColorState = _FRAME_MODULE.ColorState
V2Frame = _FRAME_MODULE.V2Frame


@dataclass(frozen=True)
class GraphIdentity:
    node_id: str
    revision: int = 0
    backend: str = "cpu"
    deterministic: bool = True
    tile_safe: bool = True
    neighborhood_radius: int = 0

    def digest(self) -> str:
        payload = json.dumps(self.__dict__, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(payload).hexdigest()


def require_scene_linear(frame: V2Frame) -> V2Frame:
    if frame.color_space.state is not ColorState.SCENE_LINEAR:
        raise ValueError("scene-linear stage requires SCENE_LINEAR frame input")
    frame.validate_scene_headroom()
    return frame


def scene_linear_identity(frame: V2Frame) -> str:
    require_scene_linear(frame)
    cs = frame.color_space
    payload = {
        "state": cs.state.value,
        "name": cs.name,
        "primaries": cs.primaries,
        "white": cs.white,
        "transfer": cs.transfer,
        "reference_white_xy": cs.reference_white_xy,
        "role": cs.role,
        "revision": frame.revision,
        "source_fingerprint": frame.source_fingerprint(),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def graph_contract_key(frame: V2Frame, nodes) -> str:
    require_scene_linear(frame)
    identities = [n.digest() if isinstance(n, GraphIdentity) else str(n) for n in nodes]
    payload = {
        "frame": scene_linear_identity(frame),
        "nodes": identities,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def finite_scene_linear(data, *, primaries="unknown", white="unknown") -> V2Frame:
    a = np.asarray(data, dtype=np.float32)
    if a.ndim != 3 or a.shape[-1] != 3:
        raise ValueError("scene-linear data must be HxWx3")
    if not np.isfinite(a).all():
        raise ValueError("scene-linear data must be finite")
    from v2_frame_contract import make_scene_linear
    return make_scene_linear(a, primaries=primaries, white=white)
