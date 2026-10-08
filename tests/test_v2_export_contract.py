import importlib.util
import os
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageCms

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "source", "v2_export_contract.py")
_SPEC = importlib.util.spec_from_file_location("v2_export_contract", _SRC)
_M = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _M
_SPEC.loader.exec_module(_M)
_FRAME = os.path.join(os.path.dirname(_HERE), "source", "v2_frame_contract.py")
_FS = importlib.util.spec_from_file_location("v2_frame_contract", _FRAME)
_FM = importlib.util.module_from_spec(_FS)
sys.modules[_FS.name] = _FM
_FS.loader.exec_module(_FM)


def profile_bytes():
    p = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))
    return p.tobytes()


def display_frame():
    return _FM.V2Frame(
        np.array([[[0.0, 0.25, 1.0], [0.5, 0.75, 1.0]], [[0.1, 0.2, 0.3], [1.0, 0.0, 0.5]]], dtype=np.float32),
        _FM.ColorSpace("sRGB display", _FM.ColorState.DISPLAY_REFERRED, primaries="sRGB", white="D65", transfer="sRGB", role="display"),
    )


def _decode_png16_with_contract(path):
    import struct
    import zlib
    data = Path(path).read_bytes()
    pos = 8
    width = height = bit_depth = None
    idat = bytearray()
    while pos < len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        kind = data[pos + 4:pos + 8]
        payload = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if kind == b"IHDR":
            width, height, bit_depth, color_type, *_ = struct.unpack(">IIBBBBB", payload)
            assert color_type == 2
        elif kind == b"IDAT":
            idat.extend(payload)
        elif kind == b"IEND":
            break
    assert bit_depth == 16
    raw = zlib.decompress(bytes(idat))
    stride = width * 3 * 2
    rows = []
    off = 0
    for _ in range(height):
        assert raw[off] == 0
        row = raw[off + 1:off + 1 + stride]
        rows.append(np.frombuffer(row, dtype=">u2").astype(np.uint16).reshape(width, 3))
        off += stride + 1
    return np.stack(rows, axis=0)


def scene_frame():
    return _FM.make_scene_linear(
        np.array([[[3.0, 0.5, 1.5], [0.25, 0.7, 0.1]], [[1.0, 0.2, 0.75], [0.99, 1.2, 0.33]]], dtype=np.float32),
        primaries="AP1", white="ACES 0.32168/0.33767",
    )


def test_tiff_16bit_preserves_pixels_and_icc(tmp_path):
    icc = profile_bytes()
    out = tmp_path / "x.tif"
    result = _M.write_tiff(display_frame(), out, bits=16, icc_profile=icc)
    inspected = _M.inspect_tiff(out)
    assert result["bits"] == 16
    assert inspected["dtype"] == "uint16"
    assert inspected["icc_profile_sha256"] == _M.sha256_bytes(icc)
    assert inspected["pixel_sha256"] == result["pixel_sha256"]


def test_exr_preserves_scene_headroom(tmp_path):
    out = tmp_path / "x.exr"
    result = _M.write_exr(scene_frame(), out)
    inspected = _M.inspect_exr(out)
    assert result["dtype"] == "float32"
    assert inspected["dtype"] == "float32"
    assert inspected["pixel_sha256"] == result["pixel_sha256"]
    import OpenEXR
    with OpenEXR.File(str(out)) as f:
        arr = f.channels()["RGB"].pixels
    assert float(arr.max()) == pytest.approx(3.0)


@pytest.mark.parametrize("bits", [8, 16])
def test_png_exact_roundtrip(tmp_path, bits):
    icc = profile_bytes()
    out = tmp_path / f"x{bits}.png"
    result = _M.write_png(display_frame(), out, bits=bits, icc_profile=icc)
    inspected = _M.inspect_png(out)
    assert inspected["icc_profile_sha256"] == _M.sha256_bytes(icc)
    if bits == 8:
        expected = np.rint(np.clip(display_frame().rgb, 0, 1) * 255).astype(np.uint8)
        with Image.open(out) as im:
            decoded = np.asarray(im, dtype=np.uint8)
    else:
        expected = np.rint(np.clip(display_frame().rgb, 0, 1) * 65535).astype(np.uint16)
        decoded = _decode_png16_with_contract(out)
    assert np.array_equal(decoded, expected)


def test_jpeg_roundtrip_is_lossy_but_bounded_and_preserves_icc(tmp_path):
    icc = profile_bytes()
    out = tmp_path / "x.jpg"
    _M.write_jpeg(display_frame(), out, quality=95, icc_profile=icc)
    inspected = _M.inspect_jpeg(out)
    with Image.open(out) as im:
        decoded = np.asarray(im).astype(np.int16)
    expected = np.rint(np.clip(display_frame().rgb, 0, 1) * 255).astype(np.int16)
    assert int(np.max(np.abs(decoded - expected))) <= 6
    assert inspected["icc_profile_sha256"] == _M.sha256_bytes(icc)


def test_integer_raster_rejects_scene_linear():
    with pytest.raises(ValueError, match="display-referred"):
        _M.write_tiff(scene_frame(), Path("bad.tif"), bits=16)
    with pytest.raises(ValueError, match="display-referred"):
        _M.write_png(scene_frame(), Path("bad.png"), bits=8)
    with pytest.raises(ValueError, match="display-referred"):
        _M.write_jpeg(scene_frame(), Path("bad.jpg"), quality=95)
