"""Compatibility entry point for the repository's current source layout.
The active implementation lives in source/lumenforge.py.
"""
import importlib.util as _importlib_util
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_IMPL = _os.path.join(_HERE, "source", "lumenforge.py")
if _HERE not in _sys.path:
    _sys.path.insert(0, _HERE)
_SOURCE_DIR = _os.path.join(_HERE, "source")
if _SOURCE_DIR not in _sys.path:
    _sys.path.insert(0, _SOURCE_DIR)
_spec = _importlib_util.spec_from_file_location("lumenforge_impl", _IMPL)
if _spec is None or _spec.loader is None:
    raise ImportError(f"Cannot load LumenForge implementation: {_IMPL}")
_impl = _importlib_util.module_from_spec(_spec)
_sys.modules[_spec.name] = _impl
_spec.loader.exec_module(_impl)

for _name in dir(_impl):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_impl, _name)

if __name__ == "__main__":
    _impl.__name__ = "__main__"
    app = _impl.App()
    _impl._hc = app._hc
    app._hc.bind("<Configure>", lambda e: app._hist(app._lo) if app._lo is not None else None)
    app.mainloop()
