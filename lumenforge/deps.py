# SPDX-License-Identifier: MIT
"""Optional third-party capabilities (rawpy, OpenCV, Numba, OpenColorIO)."""



try:
    import rawpy
except Exception:
    rawpy = None


try:
    import cv2
    HAVE_CV2 = True
except Exception:
    HAVE_CV2 = False


try:
    import PyOpenColorIO as OCIO
    HAVE_OCIO = True
except Exception:
    HAVE_OCIO = False
    OCIO = None
