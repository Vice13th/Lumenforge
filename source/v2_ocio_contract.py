"""Explicit OCIO boundary recovered from LumenParallel.

This module supplements V2 ColorManager. It does not remove the mathematical
fallback and does not claim universal GPU/backend support.
"""
import os


def load_ocio():
    try:
        import PyOpenColorIO as ocio
    except Exception:
        return None
    return ocio


def resolve_config(config_path=None):
    ocio = load_ocio()
    if ocio is None:
        return None
    if config_path:
        return ocio.Config.CreateFromFile(config_path)
    env_path = os.environ.get("OCIO", "")
    if env_path:
        return ocio.Config.CreateFromFile(env_path)
    return ocio.GetCurrentConfig()


def describe(config_path=None):
    ocio = load_ocio()
    if ocio is None:
        return {"available": False, "reason": "PyOpenColorIO unavailable", "displays": {}}
    cfg = resolve_config(config_path)
    displays = {d: list(cfg.getViews(d)) for d in cfg.getDisplays()}
    return {
        "available": True,
        "config_description": cfg.getDescription() or "",
        "displays": displays,
        "roles": list(cfg.getRoles()),
    }


def build_processor(*, src, display, view, config_path=None):
    ocio = load_ocio()
    if ocio is None:
        raise RuntimeError("PyOpenColorIO unavailable")
    cfg = resolve_config(config_path)
    if display not in cfg.getDisplays():
        raise ValueError(f"display not present in active OCIO config: {display}")
    if view not in cfg.getViews(display):
        raise ValueError(f"view not present in active OCIO config: {display}/{view}")
    transform = ocio.DisplayViewTransform()
    transform.setSrc(src)
    transform.setDisplay(display)
    transform.setView(view)
    return cfg.getProcessor(transform)


def cpu_apply_rgb(rgb, *, src, display, view, config_path=None):
    import numpy as np
    proc = build_processor(src=src, display=display, view=view, config_path=config_path)
    cpu = proc.getDefaultCPUProcessor()
    x = np.ascontiguousarray(np.asarray(rgb, dtype=np.float32))
    if x.ndim < 2 or x.shape[-1] != 3:
        raise ValueError("OCIO RGB input must have last dimension 3")
    flat = x.reshape(-1, 3).copy()
    cpu.applyRGB(flat)
    return flat.reshape(x.shape).astype(np.float32)


def processor_capabilities(*, src=None, display=None, view=None, config_path=None):
    ocio = load_ocio()
    if ocio is None:
        return {"available": False, "cpu": False, "gpu": False, "reason": "PyOpenColorIO unavailable"}
    cfg = resolve_config(config_path)
    resolved_src = src or cfg.getRoleColorSpace(getattr(ocio, "ROLE_SCENE_LINEAR", "scene_linear"))
    resolved_display = display or cfg.getDefaultDisplay()
    resolved_view = view or cfg.getDefaultView(resolved_display)
    try:
        proc = build_processor(src=resolved_src, display=resolved_display, view=resolved_view, config_path=config_path)
    except Exception as exc:
        return {"available": True, "cpu": False, "gpu": False, "reason": str(exc)}
    cpu = gpu = False
    cpu_error = gpu_error = ""
    try:
        proc.getDefaultCPUProcessor(); cpu = True
    except Exception as exc:
        cpu_error = str(exc)
    try:
        proc.getDefaultGPUProcessor(); gpu = True
    except Exception as exc:
        gpu_error = str(exc)
    return {
        "available": True,
        "cpu": cpu,
        "gpu": gpu,
        "src": resolved_src,
        "display": resolved_display,
        "view": resolved_view,
        "cpu_error": cpu_error,
        "gpu_error": gpu_error,
    }
