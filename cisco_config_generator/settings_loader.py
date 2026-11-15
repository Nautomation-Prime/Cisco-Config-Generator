from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_pack_settings(pack_path: Path) -> dict[str, Any]:
    """Load and merge all YAML config files from a pack into one dict."""
    yaml_files = [
        "settings.yaml",
        "hardware_catalog.yaml",
        "port_profiles.yaml",
        "template_map.yaml",
        "features.yaml",
    ]
    merged: dict[str, Any] = {}
    for filename in yaml_files:
        path = pack_path / filename
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            merged.update(data)
    return merged
