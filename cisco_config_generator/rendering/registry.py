from __future__ import annotations

from pathlib import Path
from typing import Any


class TemplateRegistry:
    """Resolves template hints to .j2 filenames and render order."""

    def __init__(self, template_map: dict[str, Any], templates_dir: Path):
        """Initialise with a hint→template mapping and the directory containing .j2 files."""
        self._map = template_map
        self._dir = templates_dir

    def resolve(self, hint: str) -> tuple[str, int]:
        """
        Returns (template_filename, render_order) for a given hint.
        Raises KeyError if hint not found.
        """
        entry = self._map.get(hint)
        if not entry:
            raise KeyError(f"Template hint '{hint}' not found in template_map.")
        return entry["template"], entry.get("order", 99)

    def list_hints(self) -> list[str]:
        """Return all registered template hint keys."""
        return list(self._map.keys())

    def template_path(self, filename: str) -> Path:
        """Return the absolute path to a template file by filename."""
        return self._dir / filename
