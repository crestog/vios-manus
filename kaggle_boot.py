"""Kaggle launcher for VIOS.

Run with either:

    %run kaggle_boot.py

or:

    !python kaggle_boot.py

The notebook form is preferred because it keeps the Kaggle Secrets bridge and
VIOS boot in the same Python process. This file deliberately delegates secret
normalization to vios.creds, the repository's single credential bridge, and
never prints secret values.
"""

from __future__ import annotations

import os
import runpy

from vios import creds


if __name__ == "__main__":
    bridged = creds.export_to_env()
    if bridged:
        print(
            "🔑 [KAGGLE] Secrets bridged: "
            + ", ".join(sorted(set(bridged.values())))
        )
    elif creds.on_kaggle():
        print("ℹ️ [KAGGLE] No new secrets bridged; existing environment retained.")

    boot_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "boot.py")
    runpy.run_path(boot_path, run_name="__main__")
