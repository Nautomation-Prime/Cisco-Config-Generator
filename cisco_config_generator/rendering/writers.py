from __future__ import annotations

from pathlib import Path


def write_config(output_dir: str | Path, hostname: str, content: str) -> Path:
    """Write a rendered config string to output/<hostname>.cfg."""
    out_path = Path(output_dir).resolve()
    out_path.mkdir(parents=True, exist_ok=True)
    # Guard against path traversal: strip any leading directory components from hostname.
    safe_name = Path(hostname).name
    cfg_file = (out_path / f"{safe_name}.cfg").resolve()
    if cfg_file.parent != out_path:
        raise ValueError(
            f"Hostname '{hostname}' resolved to a path outside the output directory."
        )
    cfg_file.write_text(content, encoding="utf-8")
    return cfg_file
