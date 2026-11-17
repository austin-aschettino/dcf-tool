"""Keep the app's own package in step with the files on disk.

Streamlit Cloud reruns app.py in the same Python process after a push, but Python keeps modules it has
already imported in memory. If a push adds a function to the dcf package and app.py imports it, the new
app.py meets the old package and fails with an ImportError until someone reboots the app.

refresh_package() runs before app.py imports the package. When the package's files have changed since
they were last imported (or the first time this check runs in a process that already imported them), it
drops the package's modules from memory so the import that follows loads the current files.
"""

from __future__ import annotations

import os
import sys
import time
import types

_REGISTRY = "_package_freshness"   # survives reruns: lives in sys.modules, not in app.py's namespace


def _registry() -> types.ModuleType:
    reg = sys.modules.get(_REGISTRY)
    if reg is None:
        reg = types.ModuleType(_REGISTRY)
        reg.checked_at = {}   # package name -> time of the last check that left it loaded
        sys.modules[_REGISTRY] = reg
    return reg


def refresh_package(package: str) -> bool:
    """Forget `package` and its submodules if their files changed since they were loaded. True if it did."""
    names = [n for n in sys.modules if n == package or n.startswith(package + ".")]
    reg = _registry()
    last = reg.checked_at.get(package)
    stale = False
    if names and last is None:
        # This check has never run in this process, yet the package is already in memory: it was loaded by
        # an older version of the app, so its age is unknown. Load it again to be safe (once).
        stale = True
    elif names:
        for n in names:
            path = getattr(sys.modules[n], "__file__", None)
            try:
                if path and os.path.getmtime(path) > last:
                    stale = True
                    break
            except OSError:
                stale = True   # a file that disappeared: reload so the import reports the real problem
                break
    if stale:
        for n in names:
            del sys.modules[n]
    reg.checked_at[package] = time.time()
    return stale
