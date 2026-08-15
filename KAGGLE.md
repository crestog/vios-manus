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
