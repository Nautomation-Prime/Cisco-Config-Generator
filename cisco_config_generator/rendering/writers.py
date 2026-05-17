from __future__ import annotations

from pathlib import Path


def write_config(output_dir: str | Path, hostname: str, content: str) -> Path:
    """Write a rendered config string to output/<hostname>.cfg."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    cfg_file = out_path / f"{hostname}.cfg"
    cfg_file.write_text(content, encoding="utf-8")
    return cfg_file
