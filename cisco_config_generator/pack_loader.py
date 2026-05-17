from __future__ import annotations

from pathlib import Path
from typing import Any

from cisco_config_generator.settings_loader import load_pack_settings

PACKS_DIR = Path(__file__).parent.parent / "packs"

REQUIRED_FILES = [
    "settings.yaml",
    "hardware_catalog.yaml",
    "port_profiles.yaml",
    "template_map.yaml",
    "features.yaml",
]
REQUIRED_DIRS = ["templates"]


class PackNotFoundError(Exception):
    pass


class InvalidPackError(Exception):
    pass


class Pack:
    """Represents a loaded and validated customer pack."""

    def __init__(self, path: Path, settings: dict[str, Any]):
        self.path = path
        self.name = path.name
        self.templates_dir = path / "templates"
        self.settings: dict[str, Any] = settings.get("defaults", {})
        self.hardware_catalog: dict[str, Any] = settings.get("switch_models", {})
        self.uplink_modules: dict[str, Any] = settings.get("uplink_modules", {})
        self.port_profiles: dict[str, Any] = settings.get("profiles", {})
        self.template_map: dict[str, Any] = settings.get("template_map", {})
        self.features: list[dict[str, Any]] = settings.get("features", [])
        self.log_level: str = settings.get("log_level", "INFO")
        self.strict_validation: bool = settings.get("strict_validation", True)

    def list_models(self) -> list[str]:
        return list(self.hardware_catalog.keys())

    def list_uplink_modules(self) -> list[str]:
        return list(self.uplink_modules.keys())

    def list_profiles(self) -> list[str]:
        return list(self.port_profiles.keys())


def resolve_pack_path(name_or_path: str) -> Path:
    """Resolve a pack name or path string to an absolute Path."""
    candidate = Path(name_or_path)
    if candidate.is_absolute() and candidate.is_dir():
        return candidate
    if candidate.is_dir():
        return candidate.resolve()
    from_packs = PACKS_DIR / name_or_path
    if from_packs.is_dir():
        return from_packs
    raise PackNotFoundError(
        f"Pack '{name_or_path}' not found. "
        f"Expected a folder under packs/ or an absolute path."
    )


def validate_pack(pack_path: Path) -> list[str]:
    """Validate pack structure. Returns list of error strings (empty = valid)."""
    errors: list[str] = []
    for filename in REQUIRED_FILES:
        if not (pack_path / filename).exists():
            errors.append(f"Missing required file: {filename}")
    for dirname in REQUIRED_DIRS:
        if not (pack_path / dirname).is_dir():
            errors.append(f"Missing required directory: {dirname}/")
    return errors


def load_pack(name_or_path: str) -> Pack:
    """Load and validate a pack. Returns a Pack object."""
    pack_path = resolve_pack_path(name_or_path)
    errors = validate_pack(pack_path)
    if errors:
        raise InvalidPackError(
            f"Pack at '{pack_path}' is invalid:\n" + "\n".join(f"  - {e}" for e in errors)
        )
    settings = load_pack_settings(pack_path)
    return Pack(path=pack_path, settings=settings)


def list_available_packs() -> list[str]:
    """Return names of all packs found in the packs/ directory."""
    if not PACKS_DIR.exists():
        return []
    return sorted(d.name for d in PACKS_DIR.iterdir() if d.is_dir())
