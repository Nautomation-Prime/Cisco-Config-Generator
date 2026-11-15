from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from cisco_config_generator.field_types import format_loc, friendly_message, join_location
from cisco_config_generator.pack_schema import (
    PACK_FILES,
    FeatureEntry,
    FeaturesFile,
    HardwareCatalogFile,
    PackDefaults,
    PortProfile,
    PortProfilesFile,
    SettingsFile,
    SwitchModel,
    TemplateEntry,
    TemplateMapFile,
    UplinkModule,
)

PACKS_DIR = Path(__file__).parent.parent / "packs"

REQUIRED_FILES = list(PACK_FILES)
REQUIRED_DIRS = ["templates"]

# Pack schema versions this release understands. A pack may omit
# schema_version; anything present must share this major version.
SUPPORTED_SCHEMA_MAJOR = "1"

# template_map sections the orchestrator renders by name.
REQUIRED_TEMPLATE_SECTIONS = ["acls", "vlans", "base_config", "port_channels"]

# The profile every port the workbook leaves out is rendered with.
UNUSED_PROFILE = "unused"


class PackNotFoundError(Exception):
    pass


class InvalidPackError(Exception):
    pass


class Pack:
    """Represents a loaded and validated customer pack."""

    def __init__(
        self,
        path: Path,
        settings: SettingsFile,
        hardware: HardwareCatalogFile,
        profiles: PortProfilesFile,
        templates: TemplateMapFile,
        features: FeaturesFile,
    ):
        self.path = path
        self.name = path.name
        self.templates_dir = path / "templates"
        # settings.defaults, with every key the pack leaves out filled from
        # the PackDefaults field defaults.
        self.settings: PackDefaults = settings.defaults
        self.hardware_catalog: dict[str, SwitchModel] = hardware.switch_models
        self.uplink_modules: dict[str, UplinkModule] = hardware.uplink_modules
        self.port_profiles: dict[str, PortProfile] = profiles.profiles
        self.template_map: dict[str, TemplateEntry] = templates.template_map
        self.features: list[FeatureEntry] = features.features
        self.log_level: str = settings.log_level
        self.strict_validation: bool = settings.strict_validation

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


def validate_schema_version(settings: dict[str, Any]) -> list[str]:
    """Reject a pack written for an incompatible schema major version."""
    raw = settings.get("schema_version")
    if raw is None or not str(raw).strip():
        return []
    version = str(raw).strip()
    major = version.split(".", 1)[0]
    if major != SUPPORTED_SCHEMA_MAJOR:
        return [
            f"settings.yaml: schema_version is '{version}', but this release "
            f"supports schema {SUPPORTED_SCHEMA_MAJOR}.x."
        ]
    return []


def _read_yaml(path: Path) -> tuple[Any, list[str]]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}, []
    except yaml.YAMLError as exc:
        return None, [f"{path.name}: not valid YAML - {exc}"]


def _validate_file(filename: str, raw: Any) -> tuple[BaseModel | None, list[str]]:
    """Validate one pack file against its model. Returns (model, error strings)."""
    model_cls = PACK_FILES[filename]
    try:
        return model_cls.model_validate(raw), []
    except ValidationError as exc:
        errors: list[str] = []
        for error in exc.errors():
            message = join_location(
                f"{filename}: {format_loc(error['loc'])}" if error["loc"] else filename,
                friendly_message(error, model_cls),
            )
            if error["type"] == "extra_forbidden" and filename == "settings.yaml" and error["loc"][:1] == ("defaults",):
                message += " Values read only by your own templates belong under defaults.custom."
            errors.append(message)
        return None, errors


def _cross_file_errors(
    pack_path: Path,
    profiles: PortProfilesFile,
    templates: TemplateMapFile,
) -> list[str]:
    """Checks that span more than one pack file."""
    errors: list[str] = []
    template_map = templates.template_map

    for section in REQUIRED_TEMPLATE_SECTIONS:
        if section not in template_map:
            errors.append(f"template_map.yaml: template_map is missing the required '{section}' entry.")

    for hint, entry in template_map.items():
        if not (pack_path / "templates" / entry.template).is_file():
            errors.append(
                f"template_map.yaml: template_map.{hint}.template is '{entry.template}', "
                "which does not exist in the pack's templates/ folder."
            )

    if UNUSED_PROFILE not in profiles.profiles:
        errors.append(
            f"port_profiles.yaml: profiles has no '{UNUSED_PROFILE}' profile. Ports the "
            "workbook leaves out are rendered with it - without it they get no config at all."
        )
    for name, profile in profiles.profiles.items():
        if profile.template_hint not in template_map:
            errors.append(
                f"port_profiles.yaml: profiles.{name}.template_hint is '{profile.template_hint}', "
                "which is not defined in template_map.yaml."
            )
    return errors


def load_pack(name_or_path: str) -> Pack:
    """Load and validate a pack. Returns a Pack object."""
    pack_path = resolve_pack_path(name_or_path)
    errors = validate_pack(pack_path)
    if errors:
        raise InvalidPackError(
            f"Pack at '{pack_path}' is invalid:\n" + "\n".join(f"  - {e}" for e in errors)
        )

    raw_files: dict[str, Any] = {}
    for filename in REQUIRED_FILES:
        raw, read_errors = _read_yaml(pack_path / filename)
        raw_files[filename] = raw
        errors.extend(read_errors)

    # A pack written for another schema major version would otherwise produce
    # a flood of unrelated field errors - report only the version mismatch.
    if isinstance(raw_files["settings.yaml"], dict):
        version_errors = validate_schema_version(raw_files["settings.yaml"])
        if version_errors:
            errors = version_errors

    models: dict[str, BaseModel] = {}
    if not errors:
        for filename, raw in raw_files.items():
            model, file_errors = _validate_file(filename, raw)
            errors.extend(file_errors)
            if model is not None:
                models[filename] = model

    if not errors:
        errors.extend(_cross_file_errors(
            pack_path, models["port_profiles.yaml"], models["template_map.yaml"]
        ))

    if errors:
        raise InvalidPackError(
            f"Pack at '{pack_path}' is invalid:\n" + "\n".join(f"  - {e}" for e in errors)
        )

    return Pack(
        path=pack_path,
        settings=models["settings.yaml"],
        hardware=models["hardware_catalog.yaml"],
        profiles=models["port_profiles.yaml"],
        templates=models["template_map.yaml"],
        features=models["features.yaml"],
    )


def list_available_packs() -> list[str]:
    """Return names of all packs found in the packs/ directory."""
    if not PACKS_DIR.exists():
        return []
    return sorted(d.name for d in PACKS_DIR.iterdir() if d.is_dir())
