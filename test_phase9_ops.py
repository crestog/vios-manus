import json
import os
import tempfile

from vios import observability


def main():
    observability.reset()
    observability.increment("test_total", component="probe")
    observability.observe("test_seconds", 0.25, component="probe")
    observability.event("test", token="must-not-appear", component="probe")
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "metrics.json")
        os.environ["VIOS_METRICS_PATH"] = path
        out = observability.snapshot({"queue": {"pending": 2}})
        assert "test_total{component=probe}" in out["counters"]
        assert "test_seconds{component=probe}" in out["timings"]
        assert "token" not in json.dumps(out)
        assert os.path.exists(path)
        del os.environ["VIOS_METRICS_PATH"]
    print("phase-9 ops tests passed")


if __name__ == "__main__":
    main()
