"""Recovered deterministic native/raster export contracts for V2."""
from __future__ import annotations
from pathlib import Path
import hashlib
import numpy as np


def _rgb(frame):
    a = np.asarray(getattr(frame, "rgb", getattr(frame, "data", frame)))
    if a.ndim != 3 or a.shape[-1] != 3:
        raise ValueError("export requires HxWx3 RGB data")
    if not np.isfinite(a).all():
        raise ValueError("export data contains non-finite values")
    return a


def _state(frame):
    return getattr(getattr(frame, "color_space", None), "state", None)


def _state_name(frame):
    s = _state(frame)
    return getattr(s, "value", s)


def require_display_referred(frame):
    if _state_name(frame) != "display-referred":
        raise ValueError("integer raster export requires display-referred data")


def require_scene_linear(frame):
    if _state_name(frame) not in ("scene-linear", "camera-linear"):
        raise ValueError("native EXR export requires scene-linear or camera-linear data")


def load_icc(path_or_bytes):
    data = bytes(path_or_bytes) if isinstance(path_or_bytes, (bytes, bytearray, memoryview)) else Path(path_or_bytes).read_bytes()
    if len(data) < 128:
        raise ValueError("ICC profile is too small to be valid")
    declared = int.from_bytes(data[:4], "big", signed=False)
    if declared not in (0, len(data)):
        raise ValueError(f"ICC profile size mismatch: header={declared}, bytes={len(data)}")
    return data


def sha256_bytes(data):
    return hashlib.sha256(bytes(data)).hexdigest()


def write_tiff(frame, path, *, bits=16, icc_profile=None):
    import tifffile
    require_display_referred(frame) if bits in (8, 16) else None
    a = _rgb(frame)
    if bits == 8:
        out = np.rint(np.clip(a, 0, 1) * 255).astype(np.uint8)
    elif bits == 16:
        out = np.rint(np.clip(a, 0, 1) * 65535).astype(np.uint16)
    elif bits == 32:
        require_scene_linear(frame)
        out = np.ascontiguousarray(a.astype(np.float32, copy=False))
    else:
        raise ValueError("TIFF bits must be 8, 16, or 32")
    profile = None if icc_profile is None else load_icc(icc_profile)
    kwargs = {"photometric": "rgb", "metadata": None, "software": "LumenForge LumenParallel"}
    if profile is not None:
        kwargs["iccprofile"] = profile
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    tifffile.imwrite(path, out, **kwargs)
    return {"format":"TIFF", "bits":bits, "dtype":str(out.dtype), "shape":tuple(out.shape), "icc_profile_bytes":len(profile) if profile else 0, "pixel_sha256":sha256_bytes(np.ascontiguousarray(out).view(np.uint8))}


def inspect_tiff(path):
    import tifffile
    with tifffile.TiffFile(path) as tif:
        page = tif.pages[0]
        arr = page.asarray()
        tag = page.tags.get(34675)
        profile = bytes(tag.value) if tag is not None else b""
        return {"shape":tuple(arr.shape), "dtype":str(arr.dtype), "icc_profile_bytes":len(profile), "icc_profile_sha256":sha256_bytes(profile) if profile else "", "pixel_sha256":sha256_bytes(np.ascontiguousarray(arr).view(np.uint8))}


def write_exr(frame, path, *, compression="zip"):
    import OpenEXR
    require_scene_linear(frame)
    rgb = np.ascontiguousarray(_rgb(frame).astype(np.float32, copy=False))
    cmap = {"none": OpenEXR.NO_COMPRESSION, "zip": OpenEXR.ZIP_COMPRESSION, "piz": OpenEXR.PIZ_COMPRESSION}
    if compression.lower() not in cmap:
        raise ValueError("unsupported EXR compression")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    header = {"compression": cmap[compression.lower()], "type": OpenEXR.scanlineimage}
    with OpenEXR.File(header, {"RGB": rgb}) as f:
        f.write(str(path))
    return {"format":"EXR", "dtype":"float32", "shape":tuple(rgb.shape), "compression":compression.lower(), "pixel_sha256":sha256_bytes(rgb.view(np.uint8))}


def inspect_exr(path):
    import OpenEXR
    with OpenEXR.File(str(path)) as f:
        ch = f.channels()
        arr = np.ascontiguousarray(ch["RGB"].pixels if "RGB" in ch else np.stack([ch[n].pixels for n in ("R","G","B")], axis=-1))
        h = f.header()
        return {"shape":tuple(arr.shape), "dtype":str(arr.dtype), "channels":list(ch.keys()), "compression":str(h.get("compression","")), "pixel_sha256":sha256_bytes(arr.view(np.uint8))}


def write_png(frame, path, *, bits=16, icc_profile=None):
    import importlib.util, struct, zlib
    require_display_referred(frame)
    a = _rgb(frame)
    if bits == 8:
        out = np.rint(np.clip(a,0,1)*255).astype(np.uint8)
        scan = out
    elif bits == 16:
        out = np.rint(np.clip(a,0,1)*65535).astype(np.uint16)
        scan = out.astype(">u2", copy=False)
    else:
        raise ValueError("PNG bits must be 8 or 16")
    rows = b"".join(b"\x00" + row.tobytes(order="C") for row in scan)
    ihdr = struct.pack(">IIBBBBB", out.shape[1], out.shape[0], bits, 2, 0, 0, 0)
    def chunk(kind,payload):
        return struct.pack(">I",len(payload))+kind+payload+struct.pack(">I",zlib.crc32(kind+payload)&0xffffffff)
    chunks=[b"\x89PNG\r\n\x1a\n",chunk(b"IHDR",ihdr)]
    profile=None if icc_profile is None else load_icc(icc_profile)
    if profile is not None: chunks.append(chunk(b"iCCP",b"sRGB\x00\x00"+zlib.compress(profile,9)))
    chunks += [chunk(b"IDAT",zlib.compress(rows,3)),chunk(b"IEND",b"")]
    Path(path).parent.mkdir(parents=True,exist_ok=True); Path(path).write_bytes(b"".join(chunks))
    return {"format":"PNG","bits":bits,"dtype":str(out.dtype),"shape":tuple(out.shape),"icc_profile_bytes":len(profile) if profile else 0,"pixel_sha256":sha256_bytes(out.view(np.uint8))}


def inspect_png(path):
    # Delegate decode/ICC inspection to Pillow when available; fallback is not silently substituted.
    from PIL import Image
    with Image.open(path) as im:
        arr=np.ascontiguousarray(np.asarray(im))
        profile=im.info.get("icc_profile") or b""
    return {"shape":tuple(arr.shape),"dtype":str(arr.dtype),"bits":int(arr.dtype.itemsize*8),"icc_profile_bytes":len(profile),"icc_profile_sha256":sha256_bytes(profile) if profile else "","pixel_sha256":sha256_bytes(arr.view(np.uint8))}


def write_jpeg(frame, path, *, quality=95, icc_profile=None):
    from PIL import Image
    require_display_referred(frame)
    a = _rgb(frame)
    out=np.rint(np.clip(a,0,1)*255).astype(np.uint8)
    profile=None if icc_profile is None else load_icc(icc_profile)
    kwargs={"format":"JPEG","quality":int(quality),"subsampling":0}
    if profile is not None: kwargs["icc_profile"]=profile
    Path(path).parent.mkdir(parents=True,exist_ok=True); Image.fromarray(out).save(path,**kwargs)
    return {"format":"JPEG","bits":8,"dtype":"uint8","shape":tuple(out.shape),"quality":int(quality),"icc_profile_bytes":len(profile) if profile else 0,"pixel_sha256":sha256_bytes(out.view(np.uint8))}


def inspect_jpeg(path):
    from PIL import Image
    with Image.open(path) as im:
        arr=np.ascontiguousarray(np.asarray(im)); profile=im.info.get("icc_profile") or b""
    return {"shape":tuple(arr.shape),"dtype":str(arr.dtype),"channels":int(arr.shape[-1]),"icc_profile_bytes":len(profile),"icc_profile_sha256":sha256_bytes(profile) if profile else "","pixel_sha256":sha256_bytes(arr.view(np.uint8))}
