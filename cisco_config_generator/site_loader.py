from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic import ValidationError as PydanticValidationError

from cisco_config_generator.field_types import OptionalSubnetMask, format_loc, friendly_message, join_location
from cisco_config_generator.workbook.models import ACLEntry, GlobalSettings, Site, VLAN

SITES_DIR = Path(__file__).parent.parent / "sites"


class SiteNotFoundError(Exception):
    pass


class InvalidSiteError(Exception):
    """A site file that exists but cannot be used. ``errors`` lists every problem."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


class SiteFile(GlobalSettings):
    """sites/<name>.yaml: the shared settings at the top level, plus VLANs and ACLs.

    Inherits every GlobalSettings field and its checks, and like it rejects
    keys it does not know, so a misspelt setting is reported rather than
    silently replaced by its default.
    """

    site_name: str = ""
    # Device-column fallbacks: used when a device's own Timezone / Mgmt Subnet
    # cell is blank, before falling back further to the pack's defaults.
    timezone: str = ""
    mgmt_subnet: OptionalSubnetMask = ""
    vlans: list[VLAN] = Field(default_factory=list)
    acls: list[ACLEntry] = Field(default_factory=list)

    def to_site(self, name: str) -> Site:
        global_fields = set(GlobalSettings.model_fields)
        return Site(
            name=self.site_name or name,
            global_settings=GlobalSettings.model_validate(
                {key: value for key, value in self if key in global_fields}
            ),
            vlans=self.vlans,
            acls=self.acls,
            timezone=self.timezone,
            mgmt_subnet=self.mgmt_subnet,
        )


def resolve_site_path(name: str, sites_dir: Path = SITES_DIR) -> Path:
    """Resolve a site name to its YAML file under sites_dir.

    Tries an exact '<name>.yaml' match first, then falls back to a
    case-insensitive filename match so 'Site-A' in the workbook can resolve
    to sites/site-a.yaml. Both compare against the names actually on disk, so
    the result is the same on case-insensitive filesystems (Windows) as on
    Linux.
    """
    if not sites_dir.is_dir():
        raise SiteNotFoundError(f"Site '{name}' not found under {sites_dir}.")
    candidates = sorted(sites_dir.glob("*.yaml"))
    for candidate in candidates:
        if candidate.stem == name:
            return candidate
    wanted = name.strip().lower()
    for candidate in candidates:
        if candidate.stem.lower() == wanted:
            return candidate
    raise SiteNotFoundError(f"Site '{name}' not found under {sites_dir}.")


def list_available_sites(sites_dir: Path = SITES_DIR) -> list[str]:
    """Return the names (filename stems) of every site YAML file found."""
    if not sites_dir.is_dir():
        return []
    return sorted(f.stem for f in sites_dir.glob("*.yaml"))


def _blank_to_missing(value: Any) -> Any:
    """Treat an empty YAML value ('key:' or 'key: ""') as not set, so the default applies."""
    if isinstance(value, dict):
        return {k: _blank_to_missing(v) for k, v in value.items() if v is not None and v != ""}
    if isinstance(value, list):
        return [_blank_to_missing(item) for item in value]
    return value


def load_site(name: str, sites_dir: Path = SITES_DIR) -> Site:
    """Load and parse a single site YAML file. Raises SiteNotFoundError or InvalidSiteError."""
    path = resolve_site_path(name, sites_dir)
    return load_site_from_path(path, name)


def load_site_from_path(path: Path, name: str) -> Site:
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        raise InvalidSiteError([f"could not parse {path.name}: {e}"]) from e

    if not isinstance(raw, dict):
        raise InvalidSiteError([f"{path.name} must contain a YAML mapping, not a {type(raw).__name__}."])

    try:
        site_file = SiteFile.model_validate(_blank_to_missing(raw))
    except PydanticValidationError as exc:
        raise InvalidSiteError([
            join_location(format_loc(error["loc"]) or path.name, friendly_message(error, SiteFile))
            for error in exc.errors()
        ]) from None
    return site_file.to_site(name)


def load_sites(names: list[str], sites_dir: Path = SITES_DIR) -> tuple[dict[str, Site], list[str]]:
    """Load every named site. Returns (loaded sites keyed by the requested name, error strings).

    A name that doesn't resolve to a file is silently skipped here (not an
    error) — the workbook validator reports that against the devices that
    reference it, with the list of available sites as a hint. A file that
    resolves but fails to parse or validate is a genuine site-file error, and
    each of its problems is reported here instead.
    """
    sites: dict[str, Site] = {}
    errors: list[str] = []
    for name in names:
        if not name:
            continue
        try:
            path = resolve_site_path(name, sites_dir)
        except SiteNotFoundError:
            continue
        try:
            sites[name] = load_site_from_path(path, name)
        except InvalidSiteError as e:
            errors.extend(f"Site '{name}' ({path.name}): {error}" for error in e.errors)
    return sites, errors
