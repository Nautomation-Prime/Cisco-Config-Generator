from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cisco_config_generator.pack_loader import Pack, load_pack
from cisco_config_generator.site_loader import SITES_DIR, Site, list_available_sites, load_sites
from cisco_config_generator.workbook.loader import load_workbook
from cisco_config_generator.workbook.models import (
    Device, Interface, PortChannel, Intent, HardwareProfile,
)
from cisco_config_generator.workbook.validators import validate_intent, ValidationError
from cisco_config_generator.rendering.engine import create_jinja_env, render_template
from cisco_config_generator.rendering.registry import TemplateRegistry
from cisco_config_generator.rendering.writers import write_config
from cisco_config_generator.logging_setup import get_logger


class Orchestrator:
    """Main pipeline: load pack → parse workbook → resolve sites → validate → render → write."""

    def __init__(
        self,
        pack_path: Path,
        workbook_path: str | Path,
        output_dir: str | Path = "output",
        sites_dir: str | Path = SITES_DIR,
        on_progress: Any = None,
    ):
        self.pack_path = pack_path
        self.workbook_path = Path(workbook_path)
        self.output_dir = Path(output_dir)
        self.sites_dir = Path(sites_dir)
        self.on_progress = on_progress  # callable(str) for TUI progress updates
        self.log = get_logger()

    def run(self) -> list[Path]:
        """Execute the full pipeline. Returns list of written .cfg paths."""
        self._progress("Loading pack...")
        pack = load_pack(str(self.pack_path))

        self._progress("Reading workbook...")
        intent = load_workbook(
            self.workbook_path,
            port_profiles=pack.port_profiles,
            hardware_catalog=pack.hardware_catalog,
            uplink_modules=pack.uplink_modules,
        )

        self._progress("Loading sites...")
        site_names = sorted({d.site for d in intent.devices if d.site})
        sites, site_errors = load_sites(site_names, self.sites_dir)
        available_sites = list_available_sites(self.sites_dir)
        self._resolve_device_defaults(intent.devices, sites, pack)

        self._progress("Validating intent...")
        errors = site_errors + validate_intent(
            intent,
            hardware_catalog=pack.hardware_catalog,
            uplink_modules=pack.uplink_modules,
            port_profiles=pack.port_profiles,
            sites=sites,
            available_sites=available_sites,
            strict=pack.strict_validation,
            defaults=pack.settings,
        )
        if errors:
            raise ValidationError(errors)

        jinja_env = create_jinja_env(pack.templates_dir)
        registry = TemplateRegistry(
            template_map=pack.template_map,
            templates_dir=pack.templates_dir,
        )

        written: list[Path] = []
        for device in intent.devices:
            self._progress(f"Generating config for {device.hostname}...")
            hardware = self._resolve_hardware(device, pack)
            config_text = self._render_device(
                device=device,
                site=sites[device.site],
                intent=intent,
                pack=pack,
                hardware=hardware,
                jinja_env=jinja_env,
                registry=registry,
            )
            path = write_config(self.output_dir, device.hostname, config_text)
            written.append(path)
            self.log.info(f"Written: {path}")

        return written

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _progress(self, message: str) -> None:
        self.log.debug(message)
        if callable(self.on_progress):
            self.on_progress(message)

    def _resolve_device_defaults(
        self,
        devices: list[Device],
        sites: dict[str, Site],
        pack: Pack,
    ) -> None:
        """Fill a blank Timezone/Mgmt Subnet cell from the device's site, then the pack.

        Devices whose site failed to resolve are left as-is — the missing/unknown
        site is already reported by validate_intent, and there is nothing to
        default from.
        """
        pack_timezone = pack.settings.timezone
        pack_mgmt_subnet = pack.settings.mgmt_subnet
        for device in devices:
            site = sites.get(device.site)
            if not device.timezone:
                device.timezone = (site.timezone if site else "") or pack_timezone
            if not device.mgmt_subnet:
                device.mgmt_subnet = (site.mgmt_subnet if site else "") or pack_mgmt_subnet

    def _resolve_hardware(self, device: Device, pack: Pack) -> HardwareProfile:
        # validate_intent has already confirmed both exist in the catalog.
        switch = pack.hardware_catalog[device.model]
        module = pack.uplink_modules[device.uplink_module]
        return HardwareProfile(
            model=device.model,
            access_ports=switch.access_ports,
            access_interface_prefix=switch.interface_prefix,
            access_port_start=switch.access_port_start,
            uplink_module=device.uplink_module,
            uplink_ports=module.uplink_ports,
            uplink_interface_prefix=module.interface_prefix,
            uplink_port_start=module.uplink_port_start,
        )

    def _render_device(
        self,
        device: Device,
        site: Site,
        intent: Intent,
        pack: Pack,
        hardware: HardwareProfile,
        jinja_env: Any,
        registry: TemplateRegistry,
    ) -> str:
        features = intent.feature_selection
        device_interfaces = [
            iface for iface in intent.interfaces
            if iface.device_name == device.hostname
        ]
        device_port_channels = [
            port_channel for port_channel in intent.port_channels
            if port_channel.device_name == device.hostname
        ]

        # Build base context dict
        context = {
            "device": device,
            "vlans": site.vlans,
            "interfaces": device_interfaces,
            "port_channels": device_port_channels,
            "global": site.global_settings,
            "hardware": hardware,
            "acls": site.acls,
            "features": features,
            # The whole merged settings.defaults block, so templates can read any
            # pack policy knob as settings.defaults.<key>.
            "settings": {"defaults": pack.settings},
        }

        sections: list[tuple[int, str]] = []  # (order, rendered_text)

        # --- acls ---
        if features.acls:
            tmpl, order = registry.resolve("acls")
            rendered = render_template(jinja_env, tmpl, context)
            sections.append((order, rendered))

        # --- base_config ---
        if features.base_config:
            tmpl, order = registry.resolve("base_config")
            rendered = render_template(jinja_env, tmpl, context)
            sections.append((order, rendered))

        # --- vlans ---
        if features.vlans:
            tmpl, order = registry.resolve("vlans")
            rendered = render_template(jinja_env, tmpl, context)
            sections.append((order, rendered))

        # --- interfaces (grouped by template_hint) ---
        if features.interfaces:
            sections.extend(
                self._render_interfaces(device_interfaces, context, registry, jinja_env)
            )

        if features.port_channels and device_port_channels:
            tmpl, order = registry.resolve("port_channels")
            rendered = render_template(jinja_env, tmpl, {**context, "port_channels": device_port_channels})
            sections.append((order, rendered))

        # Sort by order and join
        sections.sort(key=lambda t: t[0])
        return "\n".join(text for _, text in sections)

    def _render_interfaces(
        self,
        device_interfaces: list[Interface],
        context: dict,
        registry: TemplateRegistry,
        jinja_env: Any,
    ) -> list[tuple[int, str]]:
        """Group interfaces by template_hint and render each group once."""
        groups: dict[str, list[Interface]] = {}
        for iface in device_interfaces:
            hint = iface.template_hint or "interfaces_unused"
            groups.setdefault(hint, []).append(iface)

        sections: list[tuple[int, str]] = []
        for hint, ifaces in groups.items():
            try:
                tmpl, order = registry.resolve(hint)
            except KeyError:
                self.log.warning(f"Unknown template hint '{hint}', skipping {len(ifaces)} interface(s).")
                continue
            group_context = {**context, "interfaces": ifaces}
            rendered = render_template(jinja_env, tmpl, group_context)
            sections.append((order, rendered))
        return sections
