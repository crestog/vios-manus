import os
import tempfile

from vios.process.store import Store
from vios.process.engine import ProcessEngine
from vios.process.runners.vision import _kaggle_ocr_only


def main():
    original = os.environ.get("KAGGLE_KERNEL_RUN_TYPE")
    try:
        os.environ["KAGGLE_KERNEL_RUN_TYPE"] = "Interactive"
        assert _kaggle_ocr_only() is True
        os.environ["VIOS_KAGGLE_OCR_EASYOCR_ONLY"] = "0"
        assert _kaggle_ocr_only() is False
    finally:
        if original is None:
            os.environ.pop("KAGGLE_KERNEL_RUN_TYPE", None)
        else:
            os.environ["KAGGLE_KERNEL_RUN_TYPE"] = original
        os.environ.pop("VIOS_KAGGLE_OCR_EASYOCR_ONLY", None)

    assert ProcessEngine._is_transient_failure(RuntimeError("CUDA out of memory"))
    assert ProcessEngine._is_transient_failure(RuntimeError("invalid device ordinal"))
    assert not ProcessEngine._is_transient_failure(ValueError("bad JSON"))

    with tempfile.TemporaryDirectory() as td:
        store = Store(os.path.join(td, "evidence.db"))
        store.add_video("v1", duration=10.0)
        first = store.observer("describe", "model-a", "r1", {}, "cuda:0")
        second = store.observer("describe", "model-b", "r2", {}, "cuda:0")
        claim = {"channel": "visual", "kind": "shot_description",
                 "value": "a red car on a road", "confidence": 0.7}
        assert store.add_claims("v1", first, [claim]) == 1
        assert store.add_claims("v1", second, [{**claim, "confidence": 0.9}]) == 1
        assert len(store.claims("v1")) == 2
        canonical = store.canonical_claims("v1")
        assert len(canonical) == 1
        assert canonical[0]["confidence"] == 0.9
        store.close()
    print("phase-5 quality tests passed")


if __name__ == "__main__":
    main()
