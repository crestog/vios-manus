"""Reverse image/frame retrieval over VIOS frame-vector evidence."""

from __future__ import annotations

import os
import sqlite3
import threading

_MODEL_LOCK = threading.Lock()
_MODEL = None
_ERROR = ""


def _load(space: str):
    global _MODEL, _ERROR
    with _MODEL_LOCK:
        if _MODEL is not None:
            return _MODEL
        try:
            import torch
            from PIL import Image
            from transformers import AutoModel, AutoProcessor
        except Exception as exc:
            _ERROR = f"visual dependencies unavailable: {type(exc).__name__}: {exc}"
            return None
        model_name = os.environ.get(
            "VIOS_VISUAL_QUERY_MODEL", "openai/clip-vit-large-patch14")
        device = "cuda" if torch.cuda.is_available() else "cpu"
        try:
            proc = AutoProcessor.from_pretrained(model_name)
            model = AutoModel.from_pretrained(model_name)
            model = model.to(device).eval()
            _MODEL = {"model": model, "processor": proc, "device": device,
                      "space": space, "Image": Image, "torch": torch,
                      "model_name": model_name}
            return _MODEL
        except Exception as exc:
            _ERROR = f"visual encoder unavailable: {type(exc).__name__}: {exc}"
            return None


def error() -> str:
    return _ERROR


def encode_image(path: str, space: str = "clip"):
    """Return one normalized float32 image vector, or None."""
    import numpy as np
    pack = _load(space)
    if pack is None:
        return None
    try:
        image = pack["Image"].open(path).convert("RGB")
        inputs = pack["processor"](images=image, return_tensors="pt")
        inputs = {k: v.to(pack["device"]) if hasattr(v, "to") else v
                  for k, v in inputs.items()}
        with pack["torch"].inference_mode():
            out = pack["model"].get_image_features(**inputs)
            out = out / out.norm(dim=-1, keepdim=True)
        return out[0].float().cpu().numpy().astype("float32")
    except Exception as exc:
        global _ERROR
        _ERROR = f"visual query encoding failed: {type(exc).__name__}: {exc}"
        return None


def _frame_time(conn: sqlite3.Connection, video_key: str, frame_idx: int):
    try:
        row = conn.execute(
            "SELECT t0 FROM claim WHERE video_key=? AND frame_idx=? "
            "AND t0 IS NOT NULL ORDER BY t0 LIMIT 1",
            (video_key, int(frame_idx))).fetchone()
        if row:
            return float(row[0])
    except sqlite3.Error:
        pass
    return None


def reverse_frame(conn: sqlite3.Connection, path: str, limit: int = 24,
                  space: str = "clip") -> dict:
    """Search packed frame vectors exactly and group hits by video."""
    import numpy as np
    q = encode_image(path, space)
    if q is None:
        return {"ok": False, "mode": "unavailable", "results": [],
                "error": error()}
    try:
        rows = conn.execute(
            "SELECT video_key, dim, n, dtype, frames, data, observer_id "
            "FROM frame_vector WHERE space=?", (space,)).fetchall()
    except sqlite3.Error as exc:
        return {"ok": False, "mode": "no-frame-index", "results": [],
                "error": f"frame-vector table unavailable: {exc}"}

    hits = []
    for row in rows:
        try:
            dim = int(row[1])
            n = int(row[2])
            if dim != len(q) or n <= 0:
                continue
            frame_ids = np.frombuffer(row[4], dtype="<i4", count=n)
            dtype = "<f2" if str(row[3]).lower() in ("f16", "float16") else "<f4"
            mat = np.frombuffer(row[5], dtype=dtype, count=n * dim)
            if mat.size != n * dim or len(frame_ids) != n:
                continue
            mat = mat.reshape(n, dim).astype("float32")
            sims = mat @ q
            take = min(n, max(8, limit * 4))
            idxs = np.argpartition(-sims, take - 1)[:take]
            for i in idxs:
                hits.append({"video_key": str(row[0]),
                             "frame_idx": int(frame_ids[i]),
                             "similarity": float(sims[i]),
                             "observer_id": row[6]})
        except (TypeError, ValueError):
            continue

    hits.sort(key=lambda h: -h["similarity"])
    best = {}
    for hit in hits:
        vk = hit["video_key"]
        if vk not in best or hit["similarity"] > best[vk]["similarity"]:
            best[vk] = hit
    chosen = sorted(best.values(), key=lambda h: -h["similarity"])[:limit]
    for hit in chosen:
        hit["t_start"] = _frame_time(conn, hit["video_key"], hit["frame_idx"])
    return {"ok": True, "mode": "reverse-frame", "space": space,
            "model": _MODEL.get("model_name") if _MODEL else "",
            "results": chosen, "total": len(chosen)}
