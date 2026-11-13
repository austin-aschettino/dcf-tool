"""A small on-disk cache so a ticker you've already loaded opens instantly.

Downloaded data is saved under `.cache/` in the project folder and reused for
`max_age_hours` (12 by default). It survives restarts of the dashboard and is
shared with `main.py`. Delete the folder, or pass refresh=True, to force a fresh
download.
"""

from __future__ import annotations

import os
import pickle
import re
import tempfile
import time
from pathlib import Path
from typing import Callable, Optional, TypeVar

T = TypeVar("T")

CACHE_DIR = Path(os.environ.get("DCF_CACHE_DIR", Path(__file__).resolve().parent.parent / ".cache"))
# Bump when the saved data classes change shape, so old files are ignored.
CACHE_VERSION = 3
DEFAULT_MAX_AGE_HOURS = 12.0


def _path(key: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", key)
    return CACHE_DIR / f"v{CACHE_VERSION}_{safe}.pkl"


def read(key: str, max_age_hours: float = DEFAULT_MAX_AGE_HOURS) -> Optional[object]:
    p = _path(key)
    try:
        if time.time() - p.stat().st_mtime > max_age_hours * 3600:
            return None
        with p.open("rb") as fh:
            return pickle.load(fh)
    except Exception:  # missing, unreadable or from an older version of the code
        return None


def write(key: str, value: object) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        # Write to a temp file then rename, so a crash never leaves a half-written file.
        fd, tmp = tempfile.mkstemp(dir=CACHE_DIR, suffix=".tmp")
        with os.fdopen(fd, "wb") as fh:
            pickle.dump(value, fh)
        os.replace(tmp, _path(key))
    except Exception:
        pass  # caching is a convenience; never fail a valuation because of it


def cached(key: str, fn: Callable[[], T], max_age_hours: float = DEFAULT_MAX_AGE_HOURS, refresh: bool = False) -> T:
    if not refresh:
        hit = read(key, max_age_hours)
        if hit is not None:
            return hit  # type: ignore[return-value]
    value = fn()
    write(key, value)
    return value


def age_hours(key: str) -> Optional[float]:
    try:
        return (time.time() - _path(key).stat().st_mtime) / 3600
    except OSError:
        return None
