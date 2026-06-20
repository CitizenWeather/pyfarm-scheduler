"""Pytest configuration for pyfarm-scheduler tests.

Sets up sys.path so the pyfarm namespace package resolves correctly across
sibling packages.
"""

from __future__ import annotations

import os
import sys

# ---------------------------------------------------------------------------
# 1.  Add source roots — scheduler LAST so its pyfarm/__init__.py (which
#     calls pkgutil.extend_path) wins and extends __path__ to cover siblings.
# ---------------------------------------------------------------------------

_SCHEDULER_SRC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"
)

_SIBLING_SRCS = [
    "/home/user/pyfarm-core/src",
    "/home/user/pyfarm-analytics/src",
]

for _p in _SIBLING_SRCS:
    if _p not in sys.path:
        sys.path.append(_p)

if _SCHEDULER_SRC not in sys.path:
    sys.path.insert(0, _SCHEDULER_SRC)

# ---------------------------------------------------------------------------
# 2.  Bootstrap the pyfarm namespace package NOW (before any test imports it)
#     so that extend_path runs with the correct sys.path above.
# ---------------------------------------------------------------------------
import pyfarm  # noqa: E402  (must come after sys.path setup)
