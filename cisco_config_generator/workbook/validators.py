from __future__ import annotations

from cisco_config_generator.workbook.models import Intent, Device, VLAN, Interface


class ValidationError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("Validation failed: " + "; ".join(errors))


def validate_intent(
    intent: Intent,
    hardware_catalog: dict,
    uplink_modules: dict,
    port_profiles: dict,
    strict: bool = True,
) -> list[str]:
    """Validate loaded intent. Returns list of error strings. Empty = valid."""
    errors: list[str] = []
    warnings: list[str] = []

    vlan_ids = {v.vlan_id for v in intent.vlans}
    device_names = {d.hostname for d in intent.devices}

    # --- Devices ---
    if not intent.devices:
        errors.append("No devices found in the Devices sheet.")

    for device in intent.devices:
        if not device.hostname:
            errors.append("A device row is missing a hostname.")
        if not device.mgmt_ip:
            errors.append(f"Device '{device.hostname}' is missing a management IP.")
        if not device.default_gateway:
            errors.append(f"Device '{device.hostname}' is missing a default gateway.")
        if device.model not in hardware_catalog:
            errors.append(
                f"Device '{device.hostname}': model '{device.model}' not found in hardware catalog. "
                f"Valid models: {list(hardware_catalog.keys())}"
            )
        if device.uplink_module not in uplink_modules:
            errors.append(
                f"Device '{device.hostname}': uplink module '{device.uplink_module}' not found "
                f"in hardware catalog. Valid modules: {list(uplink_modules.keys())}"
            )

    # --- VLANs ---
    seen_vlan_ids: set[int] = set()
    for vlan in intent.vlans:
        if vlan.vlan_id in seen_vlan_ids:
            errors.append(f"Duplicate VLAN ID: {vlan.vlan_id}")
        seen_vlan_ids.add(vlan.vlan_id)
        if not vlan.vlan_name:
            errors.append(f"VLAN {vlan.vlan_id} has no name.")

    # --- Interfaces ---
    for iface in intent.interfaces:
        if iface.device_name not in device_names:
            errors.append(
                f"Interface '{iface.interface_name}' references unknown device '{iface.device_name}'."
            )
        if iface.port_profile not in port_profiles:
            errors.append(
                f"Interface '{iface.interface_name}' on '{iface.device_name}': "
                f"unknown port profile '{iface.port_profile}'."
            )
        profile_data = port_profiles.get(iface.port_profile, {})
        if profile_data.get("requires_vlan") and iface.access_vlan is None:
            errors.append(
                f"Interface '{iface.interface_name}' on '{iface.device_name}' "
                f"uses profile '{iface.port_profile}' which requires an access VLAN, but none is set."
            )
        if iface.access_vlan is not None and iface.access_vlan not in vlan_ids:
            errors.append(
                f"Interface '{iface.interface_name}' on '{iface.device_name}': "
                f"access VLAN {iface.access_vlan} is not defined in the VLANs sheet."
            )
        if profile_data.get("requires_voice_vlan") and iface.voice_vlan is None:
            errors.append(
                f"Interface '{iface.interface_name}' on '{iface.device_name}' "
                f"uses profile '{iface.port_profile}' which requires a voice VLAN, but none is set."
            )

    return errors
