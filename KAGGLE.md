# Kaggle launch

The VIOS credential bridge reads Kaggle Secrets through `kaggle_secrets.UserSecretsClient` and exports them into the environment before the workers import `config.py`. Python variables such as `secret_value_0` are not automatically environment variables, so assigning them in a notebook cell does not make them visible to `boot.py`.

The recommended single Kaggle cell is:

```python
!git clone -b main https://github.com/crestog/vios-manus.git VideoIntelligenceOS
%cd VideoIntelligenceOS
!bash setup.sh
%run kaggle_boot.py
```

`%run kaggle_boot.py` is preferred over `!python boot.py` because it executes the launcher in the current Kaggle Python process. The launcher calls `vios.creds.export_to_env()` first, then runs the existing `boot.py`. It does not print credential values and does not write them to disk.

The existing direct startup command remains available:

```python
!python boot.py
```

It will work when the credentials have already been exported into the environment before it runs. If the notebook only assigned values to variables from `UserSecretsClient.get_secret(...)`, use `%run kaggle_boot.py` instead.

The launcher does not bypass missing credentials. If a secret is absent or incorrectly named, VIOS continues to start its UI/CV services and reports Telegram as disabled, preserving the original safety behavior.

## Evidence-first runtime behavior

The processing plane now publishes smaller evidence checkpoints more frequently, Atlas refreshes from those checkpoints during the same session, and the next source video is prefetched while the current video is analyzed. This overlaps download latency with inference without running concurrent model calls against the same GPU memory or writing the SQLite evidence store from multiple engine threads.

The defaults can be tuned before launch:

```python
import os
os.environ["VIOS_PREFETCH_WORKERS"] = "1"
os.environ["VIOS_PUBLISH_MIN_SECONDS"] = "30"
os.environ["VIOS_PUBLISH_MAX_SECONDS"] = "180"
os.environ["VIOS_ATLAS_LIVE_REFRESH"] = "1"
os.environ["VIOS_ATLAS_REFRESH_SECONDS"] = "120"
```

The Omni dashboard binds before its models finish warming and exposes `/omni/api/health` with liveness, readiness, model count, and service state. A short retry in the parent proxy covers the remaining socket-binding race. PaddleOCR remains preferred; EasyOCR is used as a Kaggle fallback when PaddleOCR cannot initialize. Visual-only videos are eligible for local narrative analysis when shot descriptions exist, so an empty transcript no longer automatically produces a zero-claim language result.

The startup cell remains:

```python
!git clone -b main https://github.com/crestog/vios-manus.git VideoIntelligenceOS
%cd VideoIntelligenceOS
!bash setup.sh
%run kaggle_boot.py
```

On a machine with two visible GPUs, the processing plane now runs explicit lanes: physical GPU 0 owns capture restore, structure, perception, embeddings, and Telegram publication; physical GPU 1 owns Qwen language interpretation and writes evidence into the same WAL-backed store without publishing duplicate checkpoints. Set `VIOS_DUAL_GPU=0` only for a deliberate single-engine diagnostic run. If a GPU1 source handoff exceeds `VIOS_GPU_LANE_SOURCE_WAIT_SECONDS` (default 180), it falls back to standalone acquisition rather than silently losing work. Set `VIOS_PREFETCH_WORKERS=0` or `VIOS_ATLAS_LIVE_REFRESH=0` to disable the respective background behaviors.

For a public cloudflared session, add a Kaggle Secret named `VIOS_ADMIN_TOKEN`. Mutating process, queue, capture, and admin routes require the `X-VIOS-Admin-Token` header. Do not set `VIOS_ALLOW_UNAUTH_ADMIN=1` on a public tunnel; it is only an explicit bypass for trusted local debugging.

> Only `crestog/vios-manus` is an intended modification target. The original `crestog/VideoIntelligenceOS` remains read-only.

## References

[1]: https://github.com/crestog/vios-manus "VIOS Manus target repository"

## Omni dashboard availability

The boot supervisor now launches an Omni dashboard sidecar by default even when the v2 processing plane owns the GPU budget. This prevents `/omni` from becoming a permanent `ConnectError` merely because the full Omni model stack was intentionally held back to avoid GPU contention. The dashboard page and `/omni/api/health` remain available while data services or model workers are unavailable, and the page retries readiness-sensitive calls automatically.

For the full Omni model workers, explicitly set the mode before launching only after reserving GPU capacity:

```python
import os
os.environ["VIOS_OMNI_DASHBOARD_ONLY"] = "0"
```

The safe default remains dashboard-only. The normal Kaggle cell is unchanged:

```python
!git clone -b main https://github.com/crestog/vios-manus.git VideoIntelligenceOS
%cd VideoIntelligenceOS
!bash setup.sh
%run kaggle_boot.py
```
