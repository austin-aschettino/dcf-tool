"""The safeguard against Streamlit Cloud keeping an old version of the dcf package in memory after a push."""

from __future__ import annotations

import importlib
import os
import sys
import time

from freshness import refresh_package


def _write(path, text, mtime=None):
    path.write_text(text)
    if mtime is not None:
        os.utime(path, (mtime, mtime))


def test_a_changed_package_is_loaded_again(tmp_path, monkeypatch):
    pkg = tmp_path / "pkgfresh"
    pkg.mkdir()
    old = time.time() - 100
    _write(pkg / "__init__.py", "", old)
    _write(pkg / "tools.py", "def old():\n    return 1\n", old)
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop("_package_freshness", None)

    # First run of a fresh process: nothing in memory yet, nothing to do.
    assert refresh_package("pkgfresh") is False
    import pkgfresh.tools
    assert not hasattr(pkgfresh.tools, "new")

    # Unchanged files: the package stays as loaded.
    assert refresh_package("pkgfresh") is False

    # A "push" adds a function. The old module is still in memory, so the import that the new app.py makes
    # would fail; refresh_package drops it, and the import loads the new file.
    _write(pkg / "tools.py", "def old():\n    return 1\n\ndef new():\n    return 2\n", time.time() + 1)
    importlib.invalidate_caches()
    assert refresh_package("pkgfresh") is True
    from pkgfresh.tools import new
    assert new() == 2
    for name in [n for n in sys.modules if n.startswith("pkgfresh")]:
        del sys.modules[name]


def test_a_package_loaded_before_the_check_existed_is_reloaded_once(tmp_path, monkeypatch):
    """The deploy that first ships this safeguard runs in a process where the old package is already loaded."""
    pkg = tmp_path / "pkgonce"
    pkg.mkdir()
    _write(pkg / "__init__.py", "")
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop("_package_freshness", None)
    import pkgonce  # noqa: F401  (loaded by the "previous deploy")

    assert refresh_package("pkgonce") is True     # unknown age: reload
    import pkgonce  # noqa: F401,F811
    assert refresh_package("pkgonce") is False    # now tracked and unchanged
    del sys.modules["pkgonce"]
