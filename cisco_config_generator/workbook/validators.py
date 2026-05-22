from __future__ import annotations

import re

from cisco_config_generator.workbook.models import Intent, Device, VLAN, Interface


_STORM_CONTROL_LEVEL_RE = re.compile(r"^\d+(?:\.\d+)?\s+\d+(?:\.\d+)?$")


def _is_valid_storm_control_level(value: str) -> bool:
    return bool(_STORM_CONTROL_LEVEL_RE.fullmatch(value.strip()))


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
        if not -23 <= device.timezone_hours_offset <= 23:
            errors.append(
                f"Device '{device.hostname}': timezone hours offset {device.timezone_hours_offset} is out of range. "
                "Valid range: -23 to 23."
            )
        if not 0 <= device.timezone_minutes_offset <= 59:
            errors.append(
                f"Device '{device.hostname}': timezone minutes offset {device.timezone_minutes_offset} is out of range. "
                "Valid range: 0 to 59."
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
        if iface.voice_vlan is not None and iface.voice_vlan not in vlan_ids:
            errors.append(
                f"Interface '{iface.interface_name}' on '{iface.device_name}': "
                f"voice VLAN {iface.voice_vlan} is not defined in the VLANs sheet."
            )
        if profile_data.get("requires_native_vlan") and iface.native_vlan is None:
            errors.append(
                f"Interface '{iface.interface_name}' on '{iface.device_name}' "
                f"uses profile '{iface.port_profile}' which requires a native VLAN, but none is set."
            )
        if iface.native_vlan is not None and iface.native_vlan not in vlan_ids:
            errors.append(
                f"Interface '{iface.interface_name}' on '{iface.device_name}': "
                f"native VLAN {iface.native_vlan} is not defined in the VLANs sheet."
            )
        if iface.storm_control_broadcast and not _is_valid_storm_control_level(iface.storm_control_broadcast):
            errors.append(
                f"Interface '{iface.interface_name}' on '{iface.device_name}': "
                "Storm Control Broadcast must contain two numeric values, for example '1.00 0.70'."
            )
        if iface.storm_control_multicast and not _is_valid_storm_control_level(iface.storm_control_multicast):
            errors.append(
                f"Interface '{iface.interface_name}' on '{iface.device_name}': "
                "Storm Control Multicast must contain two numeric values, for example '1.00 0.70'."
            )
        if profile_data.get("requires_port_channel") and iface.port_channel_number is None:
            errors.append(
                f"Interface '{iface.interface_name}' on '{iface.device_name}' "
                f"uses profile '{iface.port_profile}' which requires a Port Channel No., but none is set."
            )

    if intent.feature_selection.base_config:
        global_settings = intent.global_settings
        if global_settings.snmp_host and not (global_settings.snmp_ro_user or global_settings.snmp_rw_user):
            errors.append(
                "Global Settings sets snmp_host but no SNMPv3 user is defined. Configure snmp_ro_user or snmp_rw_user, or clear snmp_host."
            )

    # --- ACLs ---
    if intent.feature_selection.acls:
        valid_actions = {"permit", "deny"}
        defined_acl_names = {acl.acl_name for acl in intent.acls if acl.acl_name}

        for acl in intent.acls:
            has_action = bool(acl.action)
            has_network = bool(acl.network)

            if acl.action and acl.action not in valid_actions:
                errors.append(
                    f"ACL '{acl.acl_name}' has invalid action '{acl.action}'. Valid actions: permit, deny."
                )
            if has_action != has_network:
                errors.append(
                    f"ACL '{acl.acl_name}' entry must include both Action and Network/Host together."
                )
            if not acl.remark and not (has_action and has_network):
                errors.append(
                    f"ACL '{acl.acl_name}' contains an empty entry. Populate Remark or Action + Network/Host."
                )

        if intent.feature_selection.base_config:
            if global_settings.vty_acl and global_settings.vty_acl not in defined_acl_names:
                errors.append(
                    f"Global Settings references VTY ACL '{global_settings.vty_acl}' but it is not defined in the ACLs sheet."
                )
            if (
                global_settings.snmp_ro_user
                and global_settings.snmp_ro_acl
                and global_settings.snmp_ro_acl not in defined_acl_names
            ):
                errors.append(
                    f"Global Settings references SNMP RO ACL '{global_settings.snmp_ro_acl}' but it is not defined in the ACLs sheet."
                )
            if (
                global_settings.snmp_rw_user
                and global_settings.snmp_rw_acl
                and global_settings.snmp_rw_acl not in defined_acl_names
            ):
                errors.append(
                    f"Global Settings references SNMP RW ACL '{global_settings.snmp_rw_acl}' but it is not defined in the ACLs sheet."
                )

    return errors
