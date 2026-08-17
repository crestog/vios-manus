import os
import tempfile

from vios.process import registry, resources
from vios.process.lanes import DualGpuCoordinator
from vios.process.engine import ProcessEngine


def main():
    assert registry.get("describe").gpu_lane == 1
    assert registry.get("narrate").gpu_lane == 1
    assert registry.get("concepts").gpu_lane == 1
    assert registry.get("visual-embed").gpu_lane is None

    probe = {"gpus": [
        {"index": 0, "name": "T4", "free_mb": 14000, "total_mb": 15360},
        {"index": 1, "name": "T4", "free_mb": 13000, "total_mb": 15360},
    ], "gpu_count": 2, "vram_total_mb": 30720,
              "vram_free_mb": 27000, "usable_vram_mb": 12000,
              "usable_vram_total_mb": 25000}
    lane = resources.pin(probe, 1)
    assert lane["gpu_count"] == 1 and lane["gpu_index"] == 1
    assert lane["gpus"][0]["index"] == 1

    with tempfile.TemporaryDirectory() as td:
        coord = DualGpuCoordinator(td)
        zero, one = coord._split(["probe", "visual-embed", "describe", "concepts"])
        assert "describe" not in zero and "concepts" not in zero
        assert "describe" in one and "concepts" in one
        assert coord.primary.publish_enabled is True
        assert coord.language.publish_enabled is False
        coord.shutdown()
    print("phase-6 lane tests passed")


if __name__ == "__main__":
    main()
