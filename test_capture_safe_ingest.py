"""Regression tests for source-agnostic, authorized local-media capture."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from vios.capture import engine as capture_engine
from vios.capture.fetch import fetch_local
from vios.capture.inputs import parse_any, parse_local_manifest
from vios.capture.ledger import open_ledger


def test_manifest_parser_accepts_local_records_only():
    text = '\n'.join([
        json.dumps({"path": "/tmp/a.mp4", "creator": "owner", "license": "permission"}),
        json.dumps({"path": "https://instagram.com/reel/no-download"}),
        json.dumps({"source_url": "https://example.test/a", "path": "/tmp/b.jpg"}),
    ])
    rows = parse_local_manifest(text)
    assert len(rows) == 2
    assert rows[0]["creator"] == "owner"
    assert rows[1]["source_url"].startswith("https://")


def test_local_media_is_content_addressed_and_reimport_safe():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        media = root / "a.mp4"
        media.write_bytes(b"authorized media bytes\x00" * 100)
        moved = root / "renamed.mp4"
        moved.write_bytes(media.read_bytes())
        manifest = root / "manifest.jsonl"
        manifest.write_text(json.dumps({"path": "a.mp4", "creator": "owner",
                                        "collection": "research"}) + "\n")

        parsed = parse_any(str(manifest))
        assert parsed["format"] == "authorized-local-manifest"
        assert parsed["external"][0]["path"] == "a.mp4"

        ledger = open_ledger(str(root / "ledger.db"))
        first = ledger.add_external_many([{"path": str(media), "creator": "owner"}],
                                         source="manifest")
        second = ledger.add_external_many([{"path": str(media), "creator": "owner"}],
                                          source="manifest")
        third = ledger.add_external_many([{"path": str(moved), "creator": "owner"}],
                                         source="manifest")
        assert first["added"] == 1
        assert second["duplicate"] == 1
        assert third["duplicate"] == 1
        assert ledger.counts()["total"] == 1

        key = ledger.conn.execute("SELECT key FROM item").fetchone()["key"]
        work = root / "work"
        result = fetch_local(str(media), key, str(work),
                             {"creator": "owner", "license": "permission"}, [])
        assert result["tool"] == "authorized-local"
        assert result["video"] and Path(result["video"]).exists()
        assert result["record"]["source"]["kind"] == "authorized-local"
        assert result["record"]["source"]["license"] == "permission"
        assert "path" not in result["record"]["source"]["manifest"]
        assert result["record"]["url"].startswith("authorized://")
        assert result["record"]["media"]["sha256"]
        ledger.close()


def test_local_only_preflight_does_not_require_ytdlp():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        media = root / "a.mp4"
        media.write_bytes(b"local")
        eng = capture_engine.CaptureEngine(str(root))
        eng.ledger.add_external(str(media), {"license": "permission"})
        old = capture_engine.tool_versions
        capture_engine.tool_versions = lambda: {"yt_dlp": "", "gallery_dl": "", "ffmpeg": "", "ok": False}
        try:
            checks = {item["name"]: item for item in eng.preflight()["checks"]}
            assert checks["yt-dlp"]["ok"] is True
        finally:
            capture_engine.tool_versions = old
            eng.shutdown()


def test_single_object_manifest_json():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "one.json"
        path.write_text(json.dumps({"path": "clip.mp4", "title": "one"}))
        parsed = parse_any(str(path))
        assert parsed["format"] == "authorized-local-manifest"
        assert parsed["external"][0]["title"] == "one"


if __name__ == "__main__":
    test_manifest_parser_accepts_local_records_only()
    test_local_media_is_content_addressed_and_reimport_safe()
    test_local_only_preflight_does_not_require_ytdlp()
    test_single_object_manifest_json()
    print("capture safe-ingest tests passed")
