"""Explicit display-referred ICC conversion boundary."""
import io
import hashlib
import numpy as np


def validate_profile(data):
    data = bytes(data)
    if len(data) < 128:
        raise ValueError("ICC profile is too small to be valid")
    declared = int.from_bytes(data[:4], "big", signed=False)
    if declared not in (0, len(data)):
        raise ValueError(f"ICC profile size mismatch: header={declared}, bytes={len(data)}")
    return data


def profile_sha256(data):
    return hashlib.sha256(validate_profile(data)).hexdigest()


def convert_display_referred_rgb(frame, input_profile, output_profile, *, output_color_space=None, rendering_intent=0):
    from PIL import Image, ImageCms
    state = getattr(getattr(frame, "color_space", None), "state", None)
    state_name = getattr(state, "value", state)
    if state_name != "display-referred":
        raise ValueError("ICC conversion requires display-referred frame input")
    rgb = np.asarray(frame.rgb)
    if rgb.ndim != 3 or rgb.shape[-1] != 3:
        raise ValueError("ICC conversion requires HxWx3 RGB data")
    if not np.isfinite(rgb).all() or np.min(rgb) < 0.0 or np.max(rgb) > 1.0:
        raise ValueError("ICC conversion requires finite display-referred RGB values in [0,1]")
    src = validate_profile(input_profile)
    dst = validate_profile(output_profile)
    image = Image.fromarray(np.rint(rgb * 255.0).astype(np.uint8), mode="RGB")
    src_p = ImageCms.ImageCmsProfile(io.BytesIO(src))
    dst_p = ImageCms.ImageCmsProfile(io.BytesIO(dst))
    converted = ImageCms.profileToProfile(
        image, src_p, dst_p,
        renderingIntent=ImageCms.Intent(int(rendering_intent)),
        outputMode="RGB", inPlace=False, flags=ImageCms.Flags.NONE,
    )
    if converted is None:
        raise RuntimeError("ICC conversion returned no image")
    out = np.asarray(converted, dtype=np.uint8).astype(np.float32) / 255.0
    cs = output_color_space if output_color_space is not None else frame.color_space
    return frame.next_revision(data=out, color_space=cs), {
        "source_profile_sha256": profile_sha256(src),
        "destination_profile_sha256": profile_sha256(dst),
        "source_fingerprint": getattr(getattr(frame, "metadata", None), "source_fingerprint", ""),
        "revision": int(getattr(frame, "revision", 0)) + 1,
    }
