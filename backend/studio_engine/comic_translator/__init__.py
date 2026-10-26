"""Manga/comic translation engine.

Importing this package preloads torch (Windows DLL-order fix, see below).
"""

__version__ = "2.0.0"

# ── Windows DLL-order fix (PaddleOCR vs torch) ──────────────────────────────
# PaddleOCR (paddlepaddle) and torch both ship ``libiomp5md.dll``. If paddle is
# imported first (during the Extract/OCR step), torch later fails to load with
# ``OSError: [WinError 127] ... torch\lib\shm.dll`` because the conflicting
# OpenMP DLL is already in the process. Pre-importing torch here — before any
# PaddleOCR code runs — lets torch's OpenMP DLL win the load order so the
# cv_auto SimpleLaMa fallback works during the Clean step.
try:
    import torch  # noqa: F401  (preload to resolve the DLL conflict)
except Exception:
    pass
