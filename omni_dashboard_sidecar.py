"""VIOS Omni dashboard sidecar.

This process deliberately has no torch, cv2, transformers, database-driver, or
model imports. It keeps the `/omni` page and readiness contract alive while the
full Omniscient worker is disabled, warming, or unavailable because the v2
processing plane owns the GPU budget.
"""
from __future__ import annotations

import os
import time
from flask import Flask, jsonify, send_file


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("VIOS_OMNI_DASHBOARD_PORT", "5000"))
HTML_PATH = os.path.join(BASE_DIR, "omni_dashboard.html")
STARTED_AT = time.time()

app = Flask("VIOSOmniDashboardSidecar")


@app.get("/")
def index():
    return send_file(HTML_PATH, mimetype="text/html")


@app.get("/api/health")
def health():
    return jsonify({
        "ok": True,
        "ready": False,
        "omni": {
            "phase": "dashboard",
            "message": "dashboard sidecar online; full Omni model workers are disabled",
            "started_at": STARTED_AT,
        },
        "services": {},
    })


@app.route("/api/<path:path>", methods=["GET", "POST"])
def not_ready(path: str):
    return jsonify({
        "ok": True,
        "ready": False,
        "omni": {
            "phase": "dashboard",
            "message": "full Omni model workers are disabled",
        },
        "error": "Omni data services are not active in dashboard-only mode",
        "path": path,
    })


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=PORT, debug=False, use_reloader=False)
