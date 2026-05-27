from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cisco_config_generator.pack_loader import Pack, load_pack
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
    """Main pipeline: load pack → parse workbook → validate → render → write."""

    def __init__(
        self,
        pack_path: Path,
        workbook_path: str | Path,
        output_dir: str | Path = "output",
        on_progress: Any = None,
    ):
        self.pack_path = pack_path
        self.workbook_path = Path(workbook_path)
        self.output_dir = Path(output_dir)
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

        self._progress("Validating intent...")
        errors = validate_intent(
            intent,
            hardware_catalog=pack.hardware_catalog,
            uplink_modules=pack.uplink_modules,
            port_profiles=pack.port_profiles,
            strict=pack.strict_validation,
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

    def _resolve_hardware(self, device: Device, pack: Pack) -> HardwareProfile:
        model_data = pack.hardware_catalog.get(device.model, {})
        module_data = pack.uplink_modules.get(device.uplink_module, {})
        return HardwareProfile(
            model=device.model,
            access_ports=model_data.get("access_ports", 0),
            access_interface_prefix=model_data.get("interface_prefix", ""),
            access_port_start=model_data.get("access_port_start", 1),
            uplink_module=device.uplink_module,
            uplink_ports=module_data.get("uplink_ports", 0),
            uplink_interface_prefix=module_data.get("interface_prefix", ""),
            uplink_port_start=module_data.get("uplink_port_start", 1),
        )

    def _render_device(
        self,
        device: Device,
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
            "vlans": intent.vlans,
            "interfaces": device_interfaces,
            "port_channels": device_port_channels,
            "global": intent.global_settings,
            "hardware": hardware,
            "acls": intent.acls,
            "features": features,
            "settings": {"defaults": {
                "unused_vlan": pack.settings.get("unused_vlan", 999),
                "native_vlan": pack.settings.get("native_vlan", 1),
            }},
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
