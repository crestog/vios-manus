"""Small, dependency-free VIOS observability surface.

Metrics are deliberately process-local and append-only enough for a Kaggle
session. They never contain credentials, prompts, raw media, or evidence text.
A deployment can scrape ``snapshot()`` through the UI or ship the JSON file to a
real metrics backend later without changing processing code.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections import Counter, deque

_LOCK = threading.RLock()
_COUNTERS = Counter()
_TIMINGS = {}
_EVENTS = deque(maxlen=500)


def _path() -> str:
    return os.environ.get("VIOS_METRICS_PATH", "").strip()


def increment(name: str, value: int = 1, **labels) -> None:
    key = name + "{" + ",".join(f"{k}={labels[k]}" for k in sorted(labels)) + "}"
    with _LOCK:
        _COUNTERS[key] += int(value)


def observe(name: str, seconds: float, **labels) -> None:
    key = name + "{" + ",".join(f"{k}={labels[k]}" for k in sorted(labels)) + "}"
    with _LOCK:
        bucket = _TIMINGS.setdefault(key, {"count": 0, "sum_seconds": 0.0,
                                           "max_seconds": 0.0})
        bucket["count"] += 1
        bucket["sum_seconds"] += max(float(seconds), 0.0)
        bucket["max_seconds"] = max(bucket["max_seconds"], float(seconds))


def event(kind: str, **fields) -> None:
    safe = {"at": time.time(), "kind": str(kind)}
    for key, value in fields.items():
        if key in {"secret", "token", "password", "prompt", "text", "path"}:
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            safe[key] = value
    with _LOCK:
        _EVENTS.append(safe)


def sample_gpu() -> list:
    try:
        from .process import resources
        return resources.probe().get("gpus", [])
    except Exception:
        return []


def snapshot(extra: dict | None = None) -> dict:
    with _LOCK:
        out = {"at": time.time(), "counters": dict(_COUNTERS),
               "timings": json.loads(json.dumps(_TIMINGS)),
               "events": list(_EVENTS)}
    out["gpus"] = sample_gpu()
    if extra:
        out["extra"] = {k: v for k, v in extra.items()
                        if k not in {"token", "secret", "password"}}
    path = _path()
    if path:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(out, fh, sort_keys=True)
            os.replace(tmp, path)
        except OSError:
            pass
    return out


def reset() -> None:
    with _LOCK:
        _COUNTERS.clear()
        _TIMINGS.clear()
        _EVENTS.clear()
