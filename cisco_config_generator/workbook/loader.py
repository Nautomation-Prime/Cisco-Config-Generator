from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import openpyxl
from openpyxl.workbook import Workbook
from openpyxl.worksheet.worksheet import Worksheet
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from cisco_config_generator.field_types import friendly_message, join_location
from cisco_config_generator.pack_schema import PortProfile, SwitchModel, UplinkModule
from cisco_config_generator.workbook.models import (
    Device, Interface, PortChannel, FeatureSelection, Intent
)
from cisco_config_generator.workbook.validators import ValidationError

# Column header (lower-cased, spaces as underscores) -> model field, per sheet.
# Columns not listed here are ignored, so a sheet can carry notes or helper
# columns of its own.
DEVICE_COLUMNS = {
    "hostname": "hostname",
    "mgmt_ip": "mgmt_ip",
    "mgmt_vlan": "mgmt_vlan",
    "default_gateway": "default_gateway",
    "model": "model",
    "uplink_module": "uplink_module",
    "site": "site",
    "timezone": "timezone",
    "timezone_hours": "timezone_hours_offset",
    "timezone_minutes": "timezone_minutes_offset",
    "mgmt_subnet": "mgmt_subnet",
}
INTERFACE_COLUMNS = {
    "device_name": "device_name",
    "interface_name": "interface_name",
    "port_profile": "port_profile",
    "description": "description",
    "access_vlan": "access_vlan",
    "voice_vlan": "voice_vlan",
    "native_vlan": "native_vlan",
    "allowed_vlans": "allowed_vlans",
    "storm_control_broadcast": "storm_control_broadcast",
    "storm_control_multicast": "storm_control_multicast",
    "port_channel_no.": "port_channel_number",
}
PORT_CHANNEL_COLUMNS = {
    "device_name": "device_name",
    "port_channel_no.": "port_channel_number",
    "description": "description",
    "native_vlan": "native_vlan",
    "allowed_vlans": "allowed_vlans",
    "storm_control_broadcast": "storm_control_broadcast",
    "storm_control_multicast": "storm_control_multicast",
}
def _normalise_key(value: Any) -> str:
    return str(value).strip().lower().replace(" ", "_")


def _cell(ws: Worksheet, row: int, col: int) -> Any:
    """A cell's value, with blank text read as no value at all."""
    value = ws.cell(row=row, column=col).value
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def _header_map(ws: Worksheet) -> dict[str, tuple[int, str]]:
    """Return {normalised_header: (col_index, header_as_written)} from row 1."""
    headers: dict[str, tuple[int, str]] = {}
    for col in range(1, ws.max_column + 1):
        val = ws.cell(row=1, column=col).value
        if val:
            headers[_normalise_key(val)] = (col, str(val).strip())
    return headers


def _validate_required_headers(headers: dict[str, Any], required: list[str], sheet_name: str) -> None:
    """Raise ValueError listing any required column headers absent from the sheet."""
    missing = [h for h in required if h not in headers]
    if missing:
        raise ValueError(
            f"Sheet '{sheet_name}' is missing required column(s): "
            + ", ".join(f"'{h}'" for h in missing)
            + f". Found: {list(headers.keys())}"
        )


def _describe(error: dict[str, Any], model: type[BaseModel], location: str, noun: str = "setting") -> str:
    return join_location(location, friendly_message(error, model, noun))


def _load_rows(
    ws: Worksheet,
    model: type[BaseModel],
    columns: dict[str, str],
    required: list[str],
    key_column: str,
    errors: list[str],
    extra_values: dict[str, Any] | None = None,
) -> list[Any]:
    """Validate each data row of a table sheet against ``model``.

    Rows whose ``key_column`` is blank are skipped. Every problem in every row
    is appended to ``errors`` with its sheet, row and column; rows that fail
    are left out of the result.
    """
    headers = _header_map(ws)
    _validate_required_headers(headers, required, ws.title)
    field_to_header = {
        field: headers[key][1] for key, field in columns.items() if key in headers
    }
    key_col = headers[key_column][0]

    rows: list[Any] = []
    for row in range(2, ws.max_row + 1):
        if _cell(ws, row, key_col) is None:
            continue
        values: dict[str, Any] = dict(extra_values or {})
        for key, field in columns.items():
            if key in headers:
                value = _cell(ws, row, headers[key][0])
                if value is not None:
                    values[field] = value
        try:
            rows.append(model.model_validate(values))
        except PydanticValidationError as exc:
            for error in exc.errors():
                location = f"Sheet '{ws.title}', row {row}"
                if error["loc"]:
                    field = str(error["loc"][0])
                    location += f", column '{field_to_header.get(field, field)}'"
                errors.append(_describe(error, model, location))
    return rows


def _load_devices(ws: Worksheet, errors: list[str]) -> list[Device]:
    """Parse the Devices sheet.

    Timezone and Mgmt Subnet are left blank ("") here when the cell is empty
    rather than defaulted — the orchestrator resolves those from the
    device's site, then the pack, once the site is known.
    """
    return _load_rows(
        ws, Device, DEVICE_COLUMNS,
        required=["hostname", "mgmt_ip", "mgmt_vlan", "default_gateway", "model", "uplink_module", "site"],
        key_column="hostname",
        errors=errors,
    )


def _load_interfaces(
    ws: Worksheet,
    port_profiles: dict[str, PortProfile],
    errors: list[str],
) -> list[Interface]:
    interfaces = _load_rows(
        ws, Interface, INTERFACE_COLUMNS,
        ["device_name", "interface_name", "port_profile"], "device_name", errors,
    )
    # The profile decides the template and QoS trust. An unknown profile is
    # reported by validate_intent.
    for interface in interfaces:
        profile = port_profiles.get(interface.port_profile)
        if profile is not None:
            interface.template_hint = profile.template_hint
            interface.qos_trust_dscp = profile.qos_trust_dscp
    return interfaces


def _load_port_channels(ws: Worksheet, errors: list[str]) -> list[PortChannel]:
    return _load_rows(
        ws, PortChannel, PORT_CHANNEL_COLUMNS,
        ["device_name", "port_channel_no."], "device_name", errors,
    )


def _key_value_rows(ws: Worksheet, first_row: int) -> dict[str, Any]:
    """Read a two-column name | value sheet into {normalised_name: value}."""
    kv: dict[str, Any] = {}
    for row in range(first_row, ws.max_row + 1):
        key = _cell(ws, row, 1)
        if key is not None:
            kv[_normalise_key(key)] = _cell(ws, row, 2)
    return kv


def _load_feature_selection(ws: Worksheet, errors: list[str]) -> FeatureSelection:
    """Reads feature name (col A) and enabled Yes/No (col B)."""
    kv = _key_value_rows(ws, first_row=2)
    # A blank Enabled cell is an error rather than a silent "No".
    values = {key: ("" if value is None else value) for key, value in kv.items()}
    try:
        return FeatureSelection.model_validate(values)
    except PydanticValidationError as exc:
        for error in exc.errors():
            feature = error["loc"][0] if error["loc"] else ""
            errors.append(
                _describe(error, FeatureSelection, f"Sheet '{ws.title}', feature '{feature}'", noun="feature")
            )
        return FeatureSelection()


def _build_interface_names(prefix: str, port_start: int, port_count: int) -> list[str]:
    if not prefix:
        return []
    return [f"{prefix}{port_number}" for port_number in range(port_start, port_start + port_count)]


def _build_unused_interface(
    device_name: str,
    interface_name: str,
    port_profiles: dict[str, PortProfile],
) -> Interface:
    return Interface(
        device_name=device_name,
        interface_name=interface_name,
        port_profile="unused",
        template_hint=port_profiles["unused"].template_hint,
    )


def _build_port_channel_from_members(
    device_name: str,
    port_channel_number: int,
    members: list[Interface],
) -> PortChannel:
    representative = members[0]
    return PortChannel(
        device_name=device_name,
        port_channel_number=port_channel_number,
        description=representative.description,
        native_vlan=representative.native_vlan,
        allowed_vlans=representative.allowed_vlans,
        storm_control_broadcast=representative.storm_control_broadcast,
        storm_control_multicast=representative.storm_control_multicast,
    )


def _expand_interfaces_from_hardware(
    devices: list[Device],
    interfaces: list[Interface],
    hardware_catalog: dict[str, SwitchModel],
    uplink_modules: dict[str, UplinkModule],
    port_profiles: dict[str, PortProfile],
) -> list[Interface]:
    if not devices or not hardware_catalog or "unused" not in port_profiles:
        return interfaces

    interfaces_by_device: dict[str, list[Interface]] = {}
    for interface in interfaces:
        interfaces_by_device.setdefault(interface.device_name, []).append(interface)

    expanded: list[Interface] = []
    known_devices = {device.hostname for device in devices}

    for device in devices:
        switch = hardware_catalog.get(device.model)
        module = uplink_modules.get(device.uplink_module)
        device_interfaces = interfaces_by_device.pop(device.hostname, [])

        # An unknown model or module is reported by validate_intent; until
        # then it simply contributes no ports.
        inventory = [
            *(_build_interface_names(switch.interface_prefix, switch.access_port_start, switch.access_ports)
              if switch else []),
            *(_build_interface_names(module.interface_prefix, module.uplink_port_start, module.uplink_ports)
              if module else []),
        ]

        if not inventory:
            expanded.extend(device_interfaces)
            continue

        inventory_names = set(inventory)
        interface_overrides: dict[str, list[Interface]] = {}
        for interface in device_interfaces:
            interface_overrides.setdefault(interface.interface_name, []).append(interface)

        for interface_name in inventory:
            overrides = interface_overrides.get(interface_name)
            if overrides:
                expanded.extend(overrides)
                continue
            expanded.append(_build_unused_interface(device.hostname, interface_name, port_profiles))

        for interface in device_interfaces:
            if interface.interface_name not in inventory_names:
                expanded.append(interface)

    for interface in interfaces:
        if interface.device_name not in known_devices:
            expanded.append(interface)

    return expanded


def _derive_port_channels_from_interfaces(interfaces: list[Interface]) -> list[PortChannel]:
    groups: dict[tuple[str, int], list[Interface]] = {}
    for interface in interfaces:
        if interface.port_channel_number is None:
            continue
        key = (interface.device_name, interface.port_channel_number)
        groups.setdefault(key, []).append(interface)

    port_channels: list[PortChannel] = []
    for (device_name, port_channel_number), members in groups.items():
        port_channels.append(_build_port_channel_from_members(device_name, port_channel_number, members))
    return port_channels


def _apply_port_channel_rows(derived: list[PortChannel], rows: list[PortChannel]) -> list[PortChannel]:
    """Lay each Port-Channels sheet row over the port-channel derived from its members.

    Only the cells the row fills in are overridden; blank cells keep the
    members' values. Port-channels without a row stay as derived. A row with
    no members, or a second row for the same port-channel, is kept as-is so
    validate_intent reports it.
    """
    merged = list(derived)
    index = {(pc.device_name, pc.port_channel_number): i for i, pc in enumerate(merged)}
    applied: set[tuple[str, int]] = set()
    for row in rows:
        key = (row.device_name, row.port_channel_number)
        if key not in index or key in applied:
            merged.append(row)
            continue
        overrides = {field: getattr(row, field) for field in row.model_fields_set}
        merged[index[key]] = merged[index[key]].model_copy(update=overrides)
        applied.add(key)
    return merged


def _sheet_key(name: str) -> str:
    """'Port-Channels', 'Port Channels' and 'port_channels' all name the same sheet."""
    return re.sub(r"[\s_-]+", " ", name.strip().lower())


def load_workbook(
    path: str | Path,
    port_profiles: dict[str, PortProfile] | None = None,
    hardware_catalog: dict[str, SwitchModel] | None = None,
    uplink_modules: dict[str, UplinkModule] | None = None,
) -> Intent:
    """Parse an intent workbook and return an Intent object.

    The workbook only carries per-device intent (Devices, Interfaces,
    Port-Channels, Feature Selection). Global settings, VLANs and ACLs are
    site-scoped and live in sites/<site>.yaml instead — see
    cisco_config_generator.site_loader.

    Every row of every sheet is checked before anything is returned, and all
    problems are raised together as one ValidationError.
    """
    port_profiles = port_profiles or {}
    wb: Workbook = openpyxl.load_workbook(str(path), data_only=True)

    def _get_sheet(name: str) -> Worksheet | None:
        for sname in wb.sheetnames:
            if _sheet_key(sname) == name:
                return wb[sname]
        return None

    devices_ws = _get_sheet("devices")
    interfaces_ws = _get_sheet("interfaces")
    port_channels_ws = _get_sheet("port channels")
    features_ws = _get_sheet("feature selection")

    errors: list[str] = []
    features = _load_feature_selection(features_ws, errors) if features_ws else FeatureSelection()
    devices = _load_devices(devices_ws, errors) if devices_ws else []
    loaded_interfaces = _load_interfaces(interfaces_ws, port_profiles, errors) if interfaces_ws else []
    port_channel_rows = _load_port_channels(port_channels_ws, errors) if port_channels_ws else []
    if errors:
        raise ValidationError(errors)

    interfaces = _expand_interfaces_from_hardware(
        devices=devices,
        interfaces=loaded_interfaces,
        hardware_catalog=hardware_catalog or {},
        uplink_modules=uplink_modules or {},
        port_profiles=port_profiles,
    )
    port_channels = _apply_port_channel_rows(
        _derive_port_channels_from_interfaces(interfaces), port_channel_rows
    )

    return Intent(
        devices=devices,
        interfaces=interfaces,
        port_channels=port_channels,
        feature_selection=features,
    )
