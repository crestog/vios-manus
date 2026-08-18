"""VIOS Omni dashboard sidecar.

The sidecar keeps `/omni` available when the heavyweight Omni model workers are
not selected for the current GPU budget. It exposes a functional read-only view
of the Atlas SQLite projection when that database exists, instead of returning
an indefinite `ready:false` response that makes the browser retry forever.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path

from flask import Flask, jsonify, request, send_file


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("VIOS_OMNI_DASHBOARD_PORT", "5000"))
HTML_PATH = os.path.join(BASE_DIR, "omni_dashboard.html")
STARTED_AT = time.time()
app = Flask("VIOSOmniDashboardSidecar")


def _db_candidates() -> list[str]:
    explicit = os.environ.get("VIOS_ATLAS_DB_PATH") or os.environ.get("ATLAS_DB_PATH")
    home = os.environ.get("ATLAS_HOME")
    candidates = [explicit] if explicit else []
    if home:
        candidates.append(os.path.join(home, "atlas.db"))
    candidates.extend((
        "/kaggle/working/atlas/atlas.db",
        "/kaggle/temp/atlas/atlas.db",
        os.path.join(BASE_DIR, "atlas", "atlas.db"),
    ))
    return [p for p in candidates if p]


def _db() -> sqlite3.Connection | None:
    for raw in _db_candidates():
        path = Path(raw)
        if not path.exists() or path.stat().st_size <= 0:
            continue
        try:
            conn = sqlite3.connect(
                f"file:{path}?mode=ro", uri=True, timeout=2,
                check_same_thread=False)
            conn.row_factory = sqlite3.Row
            return conn
        except sqlite3.Error:
            continue
    return None


def _json(value, default=None):
    if value in (None, ""):
        return default
    try:
        return json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return bool(row)


def _video_index(conn: sqlite3.Connection, limit: int = 1000) -> list[dict]:
    if not _has_table(conn, "video_index"):
        return []
    rows = conn.execute(
        "SELECT video_key, title, creator, duration, moment_count, created_at "
        "FROM video_index ORDER BY created_at DESC LIMIT ?", (max(1, min(limit, 5000)),)
    ).fetchall()
    return [{
        "video_uuid": str(r["video_key"]),
        "title": r["title"] or f"Video {r['video_key']}",
        "creator": r["creator"] or "",
        "duration": r["duration"],
        "moment_count": int(r["moment_count"] or 0),
        "evidence_count": int(r["moment_count"] or 0),
        "created_at": r["created_at"],
        "stage": "atlas-read-only",
        "dashboard_only": True,
    } for r in rows]


def _graph(conn: sqlite3.Connection, limit: int = 400) -> dict:
    if not (_has_table(conn, "graph_nodes") and _has_table(conn, "graph_edges")):
        return {"nodes": [], "edges": [], "counts": {},
                "empty_reason": "Atlas graph tables are not available yet."}
    cap = max(10, min(int(limit or 400), 1000))
    rows = conn.execute(
        "SELECT id, kind, label, sub, weight, meta FROM graph_nodes "
        "ORDER BY weight DESC LIMIT ?", (cap,)).fetchall()
    ids = {str(r["id"]) for r in rows}
    nodes = []
    counts = {}
    for r in rows:
        kind = str(r["kind"] or "dim")
        labels = ["Video" if kind == "video" else kind.title()]
        props = _json(r["meta"], {}) or {}
        if not isinstance(props, dict):
            props = {"meta": str(props)}
        props.update({"id": r["id"], "label": r["label"], "sub": r["sub"]})
        if kind == "video":
            props["uuid"] = str(r["id"])[2:] if str(r["id"]).startswith("v:") else str(r["id"])
        counts[labels[0]] = counts.get(labels[0], 0) + 1
        nodes.append({
            "id": r["id"], "label": r["label"] or r["id"],
            "group": labels[0], "value": max(1, float(r["weight"] or 1)),
            "raw_properties": {"labels": labels, "properties": props},
        })
    edges = []
    if ids:
        placeholders = ",".join("?" * len(ids))
        for r in conn.execute(
            f"SELECT src, dst, rel, weight, ref FROM graph_edges "
            f"WHERE src IN ({placeholders}) AND dst IN ({placeholders}) LIMIT ?",
            tuple(ids) + tuple(ids) + (cap * 3,)).fetchall():
            edge_id = f"{r['src']}|{r['dst']}|{r['rel']}"
            props = {"src": r["src"], "dst": r["dst"], "rel": r["rel"],
                     "weight": r["weight"], "ref": r["ref"]}
            edges.append({
                "id": edge_id, "from": r["src"], "to": r["dst"],
                "label": r["rel"] or "related", "value": float(r["weight"] or 1),
                "raw_properties": {"type": r["rel"], "properties": props},
            })
    return {"nodes": nodes, "edges": edges, "counts": counts,
            "truncated": len(rows) >= cap,
            "mode": "atlas-read-only"}


def _mode_payload(message: str = "") -> dict:
    conn = _db()
    videos = []
    graph = {"nodes": [], "edges": [], "counts": {}}
    if conn:
        try:
            videos = _video_index(conn)
            graph = _graph(conn)
        except sqlite3.Error:
            pass
        finally:
            conn.close()
    return {
        "ok": True,
        "ready": True,
        "mode": "dashboard-only",
        "read_only": True,
        "workers_active": False,
        "omni": {
            "phase": "dashboard",
            "message": message or "read-only dashboard backed by the Atlas evidence index",
            "started_at": STARTED_AT,
        },
        "atlas": {"videos": len(videos), "graph_nodes": len(graph.get("nodes", [])),
                  "graph_edges": len(graph.get("edges", []))},
    }


@app.get("/")
def index():
    return send_file(HTML_PATH, mimetype="text/html")


@app.get("/api/health")
def health():
    return jsonify(_mode_payload())


@app.get("/api/graph/health")
def graph_health():
    payload = _mode_payload()
    payload.update({"neo4j": False, "entity_extraction": False,
                    "note": "Heavy Omni workers are disabled; Atlas graph data is available read-only."})
    return jsonify(payload)


@app.get("/api/videos")
def videos():
    conn = _db()
    try:
        return jsonify(_video_index(conn) if conn else [])
    finally:
        if conn:
            conn.close()


@app.get("/api/neo4j/graph")
def global_graph():
    conn = _db()
    try:
        return jsonify(_graph(conn, request.args.get("limit", 400)) if conn
                        else {"nodes": [], "edges": [], "counts": {},
                              "empty_reason": "Atlas evidence index is not mounted yet.",
                              "mode": "atlas-read-only"})
    finally:
        if conn:
            conn.close()


@app.get("/api/neo4j/graph/<video_uuid>")
def video_graph(video_uuid: str):
    conn = _db()
    try:
        data = _graph(conn, 1000) if conn else {"nodes": [], "edges": []}
        key = str(video_uuid)
        keep = {f"v:{key}", key}
        nodes = [n for n in data.get("nodes", []) if str(n["id"]) in keep]
        ids = {n["id"] for n in nodes}
        data["nodes"] = nodes
        data["edges"] = [e for e in data.get("edges", [])
                          if e.get("from") in ids and e.get("to") in ids]
        data["empty_reason"] = "No Atlas graph rows for this video yet." if not nodes else ""
        return jsonify(data)
    finally:
        if conn:
            conn.close()


@app.route("/api/<path:path>", methods=["GET", "POST"])
def not_ready(path: str):
    payload = _mode_payload(
        "read-only Atlas-backed dashboard; this endpoint belongs to the disabled heavy Omni workers")
    payload.update({"error": "heavy Omni worker endpoint is disabled in dashboard-only mode",
                    "path": path})
    return jsonify(payload)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=PORT, debug=False, use_reloader=False)
