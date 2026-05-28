"""Version helpers for Cisco Config Generator."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version as distribution_version
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    import tomli as tomllib  # type: ignore[no-redef]

_ROOT = Path(__file__).resolve().parent.parent
_PYPROJECT_FILE = _ROOT / "pyproject.toml"
_DIST_NAME = "cisco-config-generator"
_APP_NAME = "Cisco Config Generator"


def _read_project_metadata() -> dict[str, object]:
    try:
        data = tomllib.loads(_PYPROJECT_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

    project = data.get("project")
    return project if isinstance(project, dict) else {}


def get_version() -> str:
    """Return the canonical project version string."""
    try:
        installed_version = distribution_version(_DIST_NAME)
    except PackageNotFoundError:
        installed_version = ""

    if isinstance(installed_version, str) and installed_version.strip():
        return installed_version.strip()

    project = _read_project_metadata()
    version = project.get("version")
    if isinstance(version, str) and version.strip():
        return version.strip()

    return "unknown"


def get_version_info() -> str:
    """Return a user-facing version summary."""
    return "\n".join([_APP_NAME, f"Version: {get_version()}"])
