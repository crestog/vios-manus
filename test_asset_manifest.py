import json
import os
import sqlite3
import tempfile

from vios.capture.assets import build_manifest, manifest_digest, validate_manifest
from atlas.index import ensure_schema, record_parts, clips_for


def sample():
    return build_manifest(
        "up_42",
        {"kind": "video", "msg_id": 42, "name": "up_42.mp4"},
        [
            {"i": 0, "t0": 0.0, "t1": 2.1, "name": "up_42-chunk-0000.mp4", "msg_id": 100},
            {"i": 1, "t0": 2.1, "t1": 4.2, "name": "up_42-chunk-0001.mp4", "msg_id": 101},
        ],
        [], duration=4.2,
    )


def main():
    man = sample()
    assert validate_manifest(man) == (True, "")
    man["manifest_digest"] = manifest_digest(man)
    assert validate_manifest(man) == (True, "")

    tampered = dict(man)
    tampered["duration"] = 9.0
    assert validate_manifest(tampered)[0] is False

    unsafe = sample()
    unsafe["chunks"][0]["name"] = "../escape.mp4"
    assert validate_manifest(unsafe)[0] is False

    with tempfile.TemporaryDirectory() as td:
        db = os.path.join(td, "atlas.db")
        conn = sqlite3.connect(db)
        ensure_schema(conn)
        assert record_parts(conn, man) == 3
        assert len(clips_for(conn, "42")) == 2
        replacement = sample()
        replacement["chunks"] = [dict(replacement["chunks"][0], msg_id=200)]
        replacement["manifest_digest"] = manifest_digest(replacement)
        assert record_parts(conn, replacement) == 2
        rows = clips_for(conn, "42")
        assert len(rows) == 1 and rows[0]["msg_id"] == 200
        conn.close()
    print("asset manifest tests passed")


if __name__ == "__main__":
    main()
