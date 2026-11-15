#!/usr/bin/env python3
"""
Write the JSON schemas for the pack YAML files and the site files to schemas/.

Run from the repo root after changing cisco_config_generator/pack_schema.py,
the workbook models or SiteFile in cisco_config_generator/site_loader.py:
    python scripts/export_pack_schemas.py

Each pack YAML file points at its schema with a first-line comment such as
    # yaml-language-server: $schema=../../schemas/settings.schema.json
and each site file at ../schemas/site.schema.json the same way. That gives autocomplete and inline errors in VS Code (Red Hat YAML extension)
and other editors that speak the YAML language server. The test suite fails if
the committed schemas drift from the models.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from cisco_config_generator.pack_schema import json_schemas  # noqa: E402

SCHEMA_DIR = REPO_ROOT / "schemas"


def main() -> None:
    SCHEMA_DIR.mkdir(exist_ok=True)
    for name, text in json_schemas().items():
        (SCHEMA_DIR / name).write_text(text, encoding="utf-8", newline="\n")
        print(f"Written: schemas/{name}")


if __name__ == "__main__":
    main()
