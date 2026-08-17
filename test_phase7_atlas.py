import asyncio
import os
import sqlite3
import tempfile

import numpy as np

from atlas import visual


def main():
    original = visual.encode_image
    visual.encode_image = lambda _path, space="clip": np.array([1.0, 0.0], dtype="float32")
    try:
        with tempfile.TemporaryDirectory() as td:
            db = os.path.join(td, "atlas.db")
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE frame_vector(video_key TEXT, space TEXT, dim INTEGER, n INTEGER, dtype TEXT, frames BLOB, data BLOB, observer_id TEXT)")
            conn.execute("CREATE TABLE claim(video_key TEXT, frame_idx INTEGER, t0 REAL)")
            conn.executemany("INSERT INTO claim VALUES(?,?,?)", [("v1", 4, 12.5), ("v2", 9, 2.0)])
            conn.execute("INSERT INTO frame_vector VALUES(?,?,?,?,?,?,?,?)", (
                "v1", "clip", 2, 2, "f16", np.array([4, 5], dtype="<i4").tobytes(),
                np.array([[1.0, 0.0], [0.0, 1.0]], dtype="<f2").tobytes(), "obs-a"))
            conn.execute("INSERT INTO frame_vector VALUES(?,?,?,?,?,?,?,?)", (
                "v2", "clip", 2, 1, "f32", np.array([9], dtype="<i4").tobytes(),
                np.array([[0.8, 0.6]], dtype="<f4").tobytes(), "obs-b"))
            conn.commit()
            out = visual.reverse_frame(conn, os.path.join(td, "query.jpg"), limit=2)
            assert out["ok"] and out["mode"] == "reverse-frame"
            assert out["results"][0]["video_key"] == "v1"
            assert out["results"][0]["frame_idx"] == 4
            assert out["results"][0]["t_start"] == 12.5
            conn.close()
    finally:
        visual.encode_image = original
    print("phase-7 Atlas tests passed")


if __name__ == "__main__":
    main()
