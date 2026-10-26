from pathlib import Path

import yaml


def load_yaml(path: str | Path) -> dict:
    with Path(path).open(encoding="utf-8") as config_file:
        payload = yaml.safe_load(config_file)
    if not isinstance(payload, dict):
        raise ValueError(f"配置文件必须包含对象: {path}")
    return payload

