"""Compatibility entry point for the repository's current source layout."""
import sys as _sys
import os as _os

_HERE = _os.path.dirname(_os.path.abspath(__file__))
if _HERE not in _sys.path:
    _sys.path.insert(0, _HERE)

from source.lumenforge import *
from source import lumenforge as _impl

if __name__ == "__main__":
    _impl.App().mainloop()
