"""Pytest configuration for pyfarm-scheduler tests.

Sets up sys.path so the pyfarm namespace package resolves correctly across
sibling packages, and stubs ``pyfarm.storage`` sub-modules to avoid a
SQLAlchemy version mismatch in the SQLite backend that is unrelated to the
scheduler's own functionality.
"""

from __future__ import annotations

import os
import sys
from types import ModuleType
from unittest.mock import MagicMock

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
    # pyfarm-storage src intentionally omitted — we stub it below
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

# ---------------------------------------------------------------------------
# 3.  Stub pyfarm.storage.* AFTER the namespace is initialised.
#     This prevents the broken sqlite_backend module-level Table() call from
#     ever executing, while leaving pyfarm.scheduler / pyfarm.core / pyfarm.analytics
#     available as real code.
# ---------------------------------------------------------------------------

def _register_storage_stubs() -> None:
    """Insert lightweight stubs for pyfarm.storage into sys.modules."""
    if "pyfarm.storage" in sys.modules:
        return  # already stubbed or successfully imported

    storage_stub = ModuleType("pyfarm.storage")
    storage_stub.StorageBackend = MagicMock  # type: ignore[attr-defined]
    storage_stub.get_backend = MagicMock()  # type: ignore[attr-defined]
    sys.modules["pyfarm.storage"] = storage_stub

    for _sub in ("backend", "sqlite_backend", "postgres_backend", "factory", "models"):
        mod = ModuleType(f"pyfarm.storage.{_sub}")
        if _sub == "backend":
            mod.StorageBackend = MagicMock  # type: ignore[attr-defined]
        sys.modules[f"pyfarm.storage.{_sub}"] = mod


_register_storage_stubs()
