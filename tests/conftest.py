from __future__ import annotations

import importlib
import sys
from pathlib import Path


def _ensure_local_orbit_import() -> None:
    """Force tests to import orbit from this repo checkout (not site-packages).

    Some environments have a globally installed `orbit` package which can shadow the
    working tree. That breaks tests that rely on local changes.
    """

    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) in sys.path:
        sys.path.remove(str(repo_root))
    sys.path.insert(0, str(repo_root))

    mod = sys.modules.get("orbit")
    if mod is not None:
        mod_file = getattr(mod, "__file__", "") or ""
        if str(repo_root) not in mod_file:
            for name in list(sys.modules.keys()):
                if name == "orbit" or name.startswith("orbit."):
                    del sys.modules[name]

    importlib.invalidate_caches()
    importlib.import_module("orbit")


def pytest_sessionstart(session):  # noqa: ANN001
    _ensure_local_orbit_import()

