"""Controlled V2 adapter for the recovered LumenParallel frame/scene-linear contract.

This module intentionally does not replace the existing V2 render engine. It exposes
an explicit state-bearing frame boundary so downstream integration can preserve the
sandbox semantics for numerical domain, revision, source fingerprint and color state.
"""
from dataclasses import dataclass, replace
from enum import Enum
import hashlib
from typing import Optional

import numpy as np


class ColorState(str, Enum):
    CAMERA_LINEAR = "camera-linear"
    SCENE_LINEAR = "scene-linear"
    SCENE_LOG = "scene-log"
    DISPLAY_REFERRED = "display-referred"
    DATA = "data"


class PixelFormat(str, Enum):
    F32 = "float32"
    F16 = "float16"
    U16 = "uint16"
    U8 = "uint8"


@dataclass(frozen=True)
class ColorSpace:
    name: str
    state: ColorState
    primaries: str = "unknown"
    white: str = "unknown"
    transfer: str = "linear"
    reference_white_xy: tuple = ()
    role: str = "working"

    @property
    def is_scene_linear(self) -> bool:
        return self.state in (ColorState.CAMERA_LINEAR, ColorState.SCENE_LINEAR) and self.transfer == "linear"


@dataclass(frozen=True)
class FrameMetadata:
    source_fingerprint: str = ""
    path: str = ""
    make: str = ""
    model: str = ""
    profile_id: str = ""


@dataclass(frozen=True)
class V2Frame:
    data: np.ndarray
    color_space: ColorSpace
    pixel_format: PixelFormat = PixelFormat.F32
    metadata: FrameMetadata = FrameMetadata()
    revision: int = 0

    def __post_init__(self):
        a = np.asarray(self.data)
        if a.ndim != 3 or a.shape[2] not in (3, 4):
            raise ValueError("Frame data must be HxWx3 or HxWx4")
        if not np.isfinite(a).all():
            raise ValueError("Frame contains non-finite values")
        object.__setattr__(self, "data", a)

    @property
    def rgb(self):
        return self.data[..., :3]

    def source_fingerprint(self) -> str:
        if self.metadata.source_fingerprint:
            return self.metadata.source_fingerprint
        a = np.ascontiguousarray(self.data)
        return hashlib.sha256(a.view(np.uint8)).hexdigest()

    def next_revision(self, data=None, **changes):
        return replace(self, data=self.data if data is None else data, revision=self.revision + 1, **changes)

    def validate_scene_headroom(self) -> bool:
        if self.color_space.state not in (ColorState.CAMERA_LINEAR, ColorState.SCENE_LINEAR):
            raise ValueError("Scene headroom requires camera-linear or scene-linear data")
        return bool(np.isfinite(self.rgb).all())

    def as_float32(self):
        if self.data.dtype == np.float32:
            return self
        return self.next_revision(data=self.data.astype(np.float32, copy=False), pixel_format=PixelFormat.F32)


def make_camera_linear(data, *, name="camera-linear", metadata: Optional[FrameMetadata] = None):
    return V2Frame(
        data=np.asarray(data, dtype=np.float32),
        color_space=ColorSpace(name, ColorState.CAMERA_LINEAR, transfer="linear", role="input"),
        pixel_format=PixelFormat.F32,
        metadata=metadata or FrameMetadata(),
    )


def make_scene_linear(data, *, name="scene-linear", primaries="unknown", white="unknown", metadata=None):
    return V2Frame(
        data=np.asarray(data, dtype=np.float32),
        color_space=ColorSpace(name, ColorState.SCENE_LINEAR, primaries=primaries, white=white, transfer="linear", role="working"),
        pixel_format=PixelFormat.F32,
        metadata=metadata or FrameMetadata(),
    )
