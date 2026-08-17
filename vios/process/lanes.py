"""Concurrent GPU lane orchestration for the VIOS processing plane.

GPU0 owns capture restore, structure, perception, embeddings, and publication.
GPU1 owns the Qwen language components. Each lane keeps its own model cache and
coverage leases, while both write the same WAL-backed evidence store. The public
surface deliberately mirrors :class:`ProcessEngine` so existing routes do not
know whether one or two lanes are active.
"""

from __future__ import annotations

import os
import threading
from typing import Any

from . import registry, resources


class DualGpuCoordinator:
    """Route-compatible coordinator for two explicit physical GPU lanes."""

    def __init__(self, base_dir: str | None = None):
        from .engine import ProcessEngine

        self.base = base_dir
        self.primary = ProcessEngine(base_dir, gpu_index=0,
                                     publish_enabled=True)
        self.language = ProcessEngine(base_dir, gpu_index=1,
                                      publish_enabled=False)
        self._lock = threading.RLock()
        self._configured = False
        self._language_enabled = True
        self.gpu_lanes = {"gpu0": 0, "gpu1": 1}

    @property
    def store(self):
        return self.primary.store

    @property
    def coverage(self):
        return self.primary.coverage

    @property
    def selected(self):
        return list(dict.fromkeys(self.primary.selected + self.language.selected))

    @property
    def _channel(self):
        return self.primary._channel

    def _split(self, components):
        chosen = list(components or registry.all_ids())
        chosen = [c for c in chosen if c in registry.BY_ID]
        gpu1 = [c for c in chosen if registry.get(c).gpu_lane == 1]
        gpu0 = [c for c in chosen if registry.get(c).gpu_lane != 1]
        return gpu0, gpu1

    def configure(self, **kwargs):
        components = kwargs.pop("components", None)
        if components is None:
            components = self.selected or registry.defaults()
        gpu0, gpu1 = self._split(components)
        common = dict(kwargs)
        self.primary.configure(components=gpu0, **common)
        self.language.configure(components=gpu1, **common)
        self._language_enabled = bool(gpu1)
        self._configured = True
        return self.settings()

    def settings(self):
        out = self.primary.settings()
        lang = self.language.settings()
        out["components"] = self.selected
        out["gpu_mode"] = "dual-lane"
        out["gpu_lanes"] = {
            "gpu0": {"physical_index": 0, "role": "capture, structure, perception, embeddings, publisher",
                     "components": list(self.primary.selected)},
            "gpu1": {"physical_index": 1, "role": "Qwen language interpretation",
                     "components": list(self.language.selected),
                     "enabled": self._language_enabled},
        }
        out["language_credentials"] = {
            "bot_token_set": lang.get("bot_token_set", False),
            "hf_token_set": lang.get("hf_token_set", False),
        }
        return out

    def preflight(self):
        first = self.primary.preflight()
        second = self.language.preflight() if self._language_enabled else {
            "ok": True, "checks": [], "blocking": [], "resources": {},
            "stats": {}, "disabled": True,
        }
        checks = ([{"lane": "gpu0", **c} for c in first.get("checks", [])] +
                  [{"lane": "gpu1", **c} for c in second.get("checks", [])])
        return {
            "ok": bool(first.get("ok")) and bool(second.get("ok")),
            "checks": checks,
            "blocking": (list(first.get("blocking", [])) +
                         list(second.get("blocking", []))),
            "resources": {"gpu0": first.get("resources", {}),
                          "gpu1": second.get("resources", {})},
            "stats": first.get("stats", {}),
            "lanes": {"gpu0": first, "gpu1": second},
        }

    def plan(self):
        first = self.primary.plan()
        second = self.language.plan() if self._language_enabled else {
            "cohorts": [], "unrunnable": {}, "estimate": {}, "videos": 0,
            "my_videos": 0, "resources": {}, "vram_budget_mb": 0,
        }
        first["gpu_mode"] = "dual-lane"
        first["gpu_lanes"] = {"gpu0": first.copy(), "gpu1": second}
        return first

    def start(self):
        with self._lock:
            result0 = self.primary.start()
            if not result0.get("ok"):
                return {"ok": False, "error": result0.get("error", "GPU0 failed to start"),
                        "lanes": {"gpu0": result0}}
            result1 = self.language.start() if self._language_enabled else {
                "ok": True, "disabled": True}
            if not result1.get("ok"):
                self.primary.stop()
                return {"ok": False, "error": result1.get("error", "GPU1 failed to start"),
                        "lanes": {"gpu0": result0, "gpu1": result1}}
            return {"ok": True, "lanes": {"gpu0": result0, "gpu1": result1},
                    "gpu_mode": "dual-lane"}

    def pause(self):
        a = self.primary.pause()
        b = self.language.pause() if self._language_enabled else {"ok": True, "disabled": True}
        return {"ok": bool(a.get("ok")) and bool(b.get("ok")),
                "lanes": {"gpu0": a, "gpu1": b}}

    def resume(self):
        a = self.primary.resume()
        b = self.language.resume() if self._language_enabled else {"ok": True, "disabled": True}
        return {"ok": bool(a.get("ok")) and bool(b.get("ok")),
                "lanes": {"gpu0": a, "gpu1": b}}

    def stop(self):
        a = self.primary.stop()
        b = self.language.stop() if self._language_enabled else {"ok": True, "disabled": True}
        return {"ok": bool(a.get("ok")) and bool(b.get("ok")),
                "lanes": {"gpu0": a, "gpu1": b}}

    def shutdown(self):
        self.primary.shutdown()
        self.language.shutdown()

    def status(self, fresh: bool = False):
        a = self.primary.status(fresh=fresh)
        b = self.language.status(fresh=fresh) if self._language_enabled else {
            "state": "disabled", "message": "GPU1 lane disabled", "session": {},
            "current": {}, "matrix": [], "stages": [], "resources": {},
        }
        state = "error" if "error" in (a.get("state"), b.get("state")) else (
            "running" if "running" in (a.get("state"), b.get("state")) else
            "paused" if "paused" in (a.get("state"), b.get("state")) else
            a.get("state", "idle"))
        merged = dict(a)
        merged.update({"state": state, "gpu_mode": "dual-lane",
                       "gpu_lanes": {"gpu0": a, "gpu1": b},
                       "language_lane": b})
        return merged

    def activity(self, limit: int = 200):
        rows = self.primary.activity(limit) + self.language.activity(limit)
        rows.sort(key=lambda r: r.get("at", 0))
        return rows[-limit:]

    def catalog(self):
        return [registry.get(c).as_dict() for c in self.selected]

    def publish_now(self):
        return self.primary.publish_now()

    def publish_stage_now(self, stage: str = ""):
        return self.primary.publish_stage_now(stage)

    def sync_now(self):
        return self.primary.sync_now()

    def adopt_folder_now(self, folder: str):
        return self.primary.adopt_folder_now(folder)

    def video_detail(self, key: str):
        return self.primary.video_detail(key)

    def stage_status(self):
        return self.primary.stage_status()

    def __getattr__(self, name: str) -> Any:
        # Preserve legacy route access for coverage, store, and operator helpers.
        return getattr(self.primary, name)


def dual_gpu_available() -> bool:
    """Whether automatic dual-lane mode is allowed for this session."""
    raw = os.environ.get("VIOS_DUAL_GPU", "auto").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    try:
        return len(resources.probe(os.environ.get("VIOS_SCRATCH", ".")).get("gpus", [])) >= 2
    except Exception:
        return False
