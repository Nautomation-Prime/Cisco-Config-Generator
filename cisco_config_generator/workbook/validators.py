"""Checks that span rows, sheets, sites or the pack.

Anything that can be judged from one row or entry on its own (address
formats, ranges, allowed values) is enforced by the models in models.py as
the workbook and site files load. What is left here compares rows with each
other, with their site and with the pack: duplicates, references, profile
requirements and policy rules.
"""

from __future__ import annotations

import ipaddress
import logging

from cisco_config_generator.pack_schema import PackDefaults, PortProfile, SwitchModel, UplinkModule
from cisco_config_generator.workbook.models import (
    ACLEntry, Device, GlobalSettings, Intent, Interface, PortChannel, Site, VLAN,
)

_ALL_ONES = 0xFFFFFFFF


class ValidationError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("Validation failed: " + "; ".join(errors))


def _validate_devices(
    devices: list[Device],
    hardware_catalog: dict[str, SwitchModel],
    uplink_modules: dict[str, UplinkModule],
    sites: dict[str, Site],
    available_sites: list[str],
) -> list[str]:
    """Validate device rows against each other, the hardware catalog and known sites."""
    errors: list[str] = []
    if not devices:
        errors.append("No devices found in the Devices sheet.")
        return errors
    seen_hostnames: set[str] = set()
    for device in devices:
        if device.hostname in seen_hostnames:
            errors.append(
                f"Duplicate hostname '{device.hostname}': each device must have a unique hostname."
            )
        seen_hostnames.add(device.hostname)
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

        # --- Site ---
        if not device.site:
            errors.append(
                f"Device '{device.hostname}' has no Site. Set it to the name of a site YAML file "
                f"(available: {', '.join(available_sites) if available_sites else 'none found'})."
            )
        elif device.site not in sites:
            errors.append(
                f"Device '{device.hostname}': site '{device.site}' was not found under sites/. "
                f"Available sites: {', '.join(available_sites) if available_sites else 'none found'}."
            )
        else:
            site_vlan_ids = {v.vlan_id for v in sites[device.site].vlans}
            if site_vlan_ids and device.mgmt_vlan not in site_vlan_ids:
                errors.append(
                    f"Device '{device.hostname}': management VLAN {device.mgmt_vlan} is not defined in "
                    f"site '{device.site}'. The management SVI would be built on a VLAN the switch does not have."
                )
    return errors


def _validate_vlans(vlans: list[VLAN], site_label: str) -> list[str]:
    """Validate one site's VLAN entries for duplicates. Returns error strings."""
    errors: list[str] = []
    seen_vlan_ids: set[int] = set()
    for vlan in vlans:
        if vlan.vlan_id in seen_vlan_ids:
            errors.append(f"{site_label}Duplicate VLAN ID: {vlan.vlan_id}")
        seen_vlan_ids.add(vlan.vlan_id)
    return errors


# Stand-in for an unknown profile, which is reported separately.
_NO_PROFILE = PortProfile(template_hint="")


def _validate_interfaces(
    interfaces: list[Interface],
    device_vlan_ids: dict[str, set[int] | None],
    device_names: set[str],
    port_profiles: dict[str, PortProfile],
) -> list[str]:
    """Validate interface rows against known devices, VLANs, and profile rules. Returns error strings."""
    errors: list[str] = []
    for iface in interfaces:
        where = f"Interface '{iface.interface_name}' on '{iface.device_name}'"
        if iface.device_name not in device_names:
            errors.append(
                f"Interface '{iface.interface_name}' references unknown device '{iface.device_name}'."
            )
        if iface.port_profile not in port_profiles:
            errors.append(f"{where}: unknown port profile '{iface.port_profile}'.")
        profile = port_profiles.get(iface.port_profile, _NO_PROFILE)
        requirements = [
            (profile.requires_vlan, iface.access_vlan, "an access VLAN"),
            (profile.requires_voice_vlan, iface.voice_vlan, "a voice VLAN"),
            (profile.requires_native_vlan, iface.native_vlan, "a native VLAN"),
            (profile.requires_port_channel, iface.port_channel_number, "a Port Channel No."),
        ]
        for required, value, what in requirements:
            if required and value is None:
                errors.append(
                    f"{where} uses profile '{iface.port_profile}' which requires {what}, but none is set."
                )
        # None when the device's site did not resolve - that is reported
        # against the device, and there are no VLANs to check against.
        vlan_ids = device_vlan_ids.get(iface.device_name)
        if vlan_ids is not None:
            for label, vlan in (("access", iface.access_vlan), ("voice", iface.voice_vlan), ("native", iface.native_vlan)):
                if vlan is not None and vlan not in vlan_ids:
                    errors.append(f"{where}: {label} VLAN {vlan} is not defined in its site's VLANs.")
    return errors


def _validate_port_channels(
    port_channels: list[PortChannel],
    device_vlan_ids: dict[str, set[int] | None],
    device_names: set[str],
    interfaces: list[Interface],
) -> list[str]:
    errors: list[str] = []
    seen_keys: set[tuple[str, int]] = set()
    interface_keys = {
        (iface.device_name, iface.port_channel_number)
        for iface in interfaces
        if iface.port_channel_number is not None
    }

    for port_channel in port_channels:
        key = (port_channel.device_name, port_channel.port_channel_number)
        if port_channel.device_name not in device_names:
            errors.append(
                f"Port-channel {port_channel.port_channel_number} references unknown device '{port_channel.device_name}'."
            )
        if key in seen_keys:
            errors.append(
                f"Duplicate Port-channel {port_channel.port_channel_number} on device '{port_channel.device_name}'."
            )
        seen_keys.add(key)
        vlan_ids = device_vlan_ids.get(port_channel.device_name)
        if port_channel.native_vlan is not None and vlan_ids is not None and port_channel.native_vlan not in vlan_ids:
            errors.append(
                f"Port-channel {port_channel.port_channel_number} on '{port_channel.device_name}': "
                f"native VLAN {port_channel.native_vlan} is not defined in its site's VLANs."
            )
        if key not in interface_keys:
            errors.append(
                f"Port-channel {port_channel.port_channel_number} on '{port_channel.device_name}' has no member interfaces referencing it."
            )

    return errors


def _validate_global_settings(
    global_settings: GlobalSettings,
    defaults: PackDefaults,
    site_label: str,
) -> tuple[list[str], list[str]]:
    """Validate one site's global settings. Returns (hard_errors, soft_warnings)."""
    errors: list[str] = []
    warnings: list[str] = []

    # A banner whose text contains its own delimiter ends early on the switch,
    # and everything after it is parsed as configuration commands.
    delimiters = [
        ("banner_motd", global_settings.banner_motd, defaults.banner_delimiter),
        ("aaa_fail_message", global_settings.aaa_fail_message, defaults.aaa_fail_message_delimiter),
    ]
    for field_name, text, delimiter in delimiters:
        if text and delimiter and delimiter in text:
            errors.append(
                f"{site_label}'{field_name}' contains the delimiter character "
                f"'{delimiter}', which ends the message early on the switch. "
                f"Remove it, or change the delimiter in the pack's settings.yaml."
            )
    if global_settings.snmp_host and not (global_settings.snmp_ro_user or global_settings.snmp_rw_user):
        errors.append(
            f"{site_label}sets snmp_host but no SNMPv3 user is defined. "
            "Configure snmp_ro_user or snmp_rw_user, or clear snmp_host."
        )
    if global_settings.enable_secret == "changeme":
        warnings.append(
            f"{site_label}'enable_secret' is the default placeholder value. "
            "Replace it with a strong enable secret before deploying."
        )
    if global_settings.local_username and global_settings.local_password == "changeme":
        warnings.append(
            f"{site_label}'local_password' is the default placeholder value. "
            "Replace it with a strong password before deploying."
        )
    if global_settings.aaa_servers and not global_settings.aaa_key:
        errors.append(
            f"{site_label}AAA servers are defined but 'aaa_key' is empty. "
            "The switch would send an empty shared secret."
        )
    if global_settings.aaa_servers and not global_settings.local_username:
        warnings.append(
            f"{site_label}AAA servers are defined but no 'local_username' is set. "
            "Without a local account there is no fallback if the AAA servers become unreachable."
        )
    return errors, warnings


def _acl_line(entry: ACLEntry) -> str:
    return " ".join(part for part in (entry.action, entry.network, entry.wildcard) if part)


def _acl_match(entry: ACLEntry) -> tuple[int, int]:
    """(address bits, wildcard bits) for a permit/deny entry of a standard ACL."""
    if entry.network == "any":
        return 0, _ALL_ONES
    address = entry.network.split()[-1]  # drops a leading 'host'
    wildcard = int(ipaddress.IPv4Address(entry.wildcard)) if entry.wildcard else 0
    return int(ipaddress.IPv4Address(address)) & ~wildcard & _ALL_ONES, wildcard


def _covers(earlier: tuple[int, int], later: tuple[int, int]) -> bool:
    """True when every address the later entry matches is matched by the earlier one."""
    earlier_address, earlier_wildcard = earlier
    later_address, later_wildcard = later
    fixed = ~earlier_wildcard & _ALL_ONES
    # The earlier entry may only fix bits the later entry also fixes, to the same values.
    return (fixed & later_wildcard) == 0 and (earlier_address & fixed) == (later_address & fixed)


def _shadowed_acl_entries(acls: list[ACLEntry], site_label: str) -> list[str]:
    """Report entries that can never take effect because an earlier entry does the opposite.

    'deny any' followed by 'permit 10.0.0.0 0.0.0.255' never permits anything,
    and 'permit 10.0.0.0 0.0.0.255' followed by 'deny 10.0.0.5' never denies
    that host. A later entry with the same action as the one shadowing it is
    merely redundant and is left alone.
    """
    errors: list[str] = []
    by_name: dict[str, list[ACLEntry]] = {}
    for entry in acls:
        if entry.action:
            by_name.setdefault(entry.acl_name, []).append(entry)
    for acl_name, entries in by_name.items():
        matches = [_acl_match(entry) for entry in entries]
        for index, entry in enumerate(entries):
            for earlier_index in range(index):
                earlier = entries[earlier_index]
                if earlier.action != entry.action and _covers(matches[earlier_index], matches[index]):
                    errors.append(
                        f"{site_label}ACL '{acl_name}': '{_acl_line(entry)}' can never take effect - "
                        f"the earlier entry '{_acl_line(earlier)}' already matches every address it "
                        "covers. Move it above that entry, or remove it."
                    )
                    break
    return errors


def _validate_acls(
    acls: list[ACLEntry],
    global_settings: GlobalSettings,
    defined_acl_names: set[str],
    check_global_references: bool,
    site_label: str,
) -> list[str]:
    """Validate one site's ACL entry order and cross-references. Returns error strings."""
    errors = _shadowed_acl_entries(acls, site_label)

    if check_global_references:
        if global_settings.vty_acl and global_settings.vty_acl not in defined_acl_names:
            errors.append(
                f"{site_label}references VTY ACL '{global_settings.vty_acl}' but it is not defined in this site's ACLs."
            )
        if (
            global_settings.snmp_ro_user
            and global_settings.snmp_ro_acl
            and global_settings.snmp_ro_acl not in defined_acl_names
        ):
            errors.append(
                f"{site_label}references SNMP RO ACL '{global_settings.snmp_ro_acl}' but it is not defined in this site's ACLs."
            )
        if (
            global_settings.snmp_rw_user
            and global_settings.snmp_rw_acl
            and global_settings.snmp_rw_acl not in defined_acl_names
        ):
            errors.append(
                f"{site_label}references SNMP RW ACL '{global_settings.snmp_rw_acl}' but it is not defined in this site's ACLs."
            )

    return errors


def validate_intent(
    intent: Intent,
    hardware_catalog: dict[str, SwitchModel],
    uplink_modules: dict[str, UplinkModule],
    port_profiles: dict[str, PortProfile],
    sites: dict[str, Site],
    available_sites: list[str] | None = None,
    strict: bool = True,
    defaults: PackDefaults | None = None,
) -> list[str]:
    """Validate loaded intent against the pack catalogs and resolved sites. Returns list of error strings. Empty = valid.

    ``sites`` maps each device's Site value to its loaded Site (global
    settings, VLANs, ACLs) — see cisco_config_generator.site_loader.load_sites.
    Devices whose site failed to resolve are still reported here (missing
    site / unknown site), they just have no VLANs to validate references
    against.

    When ``strict`` is False, a small set of hardening *recommendations*
    (placeholder credentials, no local-account AAA fallback) are downgraded
    to warnings that are logged but do not block generation. Everything that
    would break rendering or leave an exploitable gap (invalid addresses,
    undefined VLAN/ACL references, empty AAA secrets, SNMP host with no
    user, etc.) is always a hard error, regardless of this flag.
    """
    defaults = defaults or PackDefaults()
    available_sites = available_sites if available_sites is not None else sorted(sites.keys())
    device_names = {d.hostname for d in intent.devices}
    device_vlan_ids: dict[str, set[int] | None] = {
        d.hostname: ({v.vlan_id for v in sites[d.site].vlans} if d.site in sites else None)
        for d in intent.devices
    }

    errors: list[str] = [
        *_validate_devices(intent.devices, hardware_catalog, uplink_modules, sites, available_sites),
        *_validate_interfaces(intent.interfaces, device_vlan_ids, device_names, port_profiles),
        *_validate_port_channels(intent.port_channels, device_vlan_ids, device_names, intent.interfaces),
    ]
    warnings: list[str] = []

    for site_name, site in sorted(sites.items()):
        label = f"Site '{site_name}': "
        errors.extend(_validate_vlans(site.vlans, label))

        if intent.feature_selection.base_config:
            hard, soft = _validate_global_settings(site.global_settings, defaults, label)
            errors.extend(hard)
            warnings.extend(soft)

        if intent.feature_selection.acls:
            defined_acl_names = {acl.acl_name for acl in site.acls if acl.acl_name}
            errors.extend(_validate_acls(
                site.acls,
                site.global_settings,
                defined_acl_names,
                check_global_references=intent.feature_selection.base_config,
                site_label=label,
            ))

    if warnings:
        if strict:
            errors.extend(warnings)
        else:
            log = logging.getLogger("cisco_config_generator")
            for w in warnings:
                log.warning(f"[hardening] {w}")

    return errors
