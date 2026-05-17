from __future__ import annotations

from pathlib import Path
from typing import Any

import openpyxl
from openpyxl.workbook import Workbook
from openpyxl.worksheet.worksheet import Worksheet

from cisco_config_generator.workbook.models import (
    Device, VLAN, Interface, GlobalSettings, FeatureSelection, Intent
)


def _cell_value(ws: Worksheet, row: int, col: int) -> Any:
    val = ws.cell(row=row, column=col).value
    return val if val is not None else ""


def _list_field(raw: Any) -> list[str]:
    if not raw:
        return []
    return [s.strip() for s in str(raw).split(",") if s.strip()]


def _header_map(ws: Worksheet) -> dict[str, int]:
    """Return {header_lower: col_index} from row 1 of a worksheet."""
    headers: dict[str, int] = {}
    for col in range(1, ws.max_column + 1):
        val = ws.cell(row=1, column=col).value
        if val:
            headers[str(val).strip().lower().replace(" ", "_")] = col
    return headers


def _load_devices(ws: Worksheet) -> list[Device]:
    headers = _header_map(ws)
    devices: list[Device] = []
    for row in range(2, ws.max_row + 1):
        hostname = _cell_value(ws, row, headers.get("hostname", 1))
        if not hostname:
            continue
        devices.append(Device(
            hostname=str(hostname).strip(),
            mgmt_ip=str(_cell_value(ws, row, headers.get("mgmt_ip", 2))).strip(),
            mgmt_vlan=int(_cell_value(ws, row, headers.get("mgmt_vlan", 3)) or 1),
            default_gateway=str(_cell_value(ws, row, headers.get("default_gateway", 4))).strip(),
            model=str(_cell_value(ws, row, headers.get("model", 5))).strip(),
            uplink_module=str(_cell_value(ws, row, headers.get("uplink_module", 6))).strip(),
            site=str(_cell_value(ws, row, headers.get("site", 7))).strip(),
            timezone=str(_cell_value(ws, row, headers.get("timezone", 8)) or "GMT").strip(),
            mgmt_subnet=str(_cell_value(ws, row, headers.get("mgmt_subnet", 9)) or "255.255.255.0").strip(),
        ))
    return devices


def _load_vlans(ws: Worksheet) -> list[VLAN]:
    headers = _header_map(ws)
    vlans: list[VLAN] = []
    for row in range(2, ws.max_row + 1):
        vlan_id = _cell_value(ws, row, headers.get("vlan_id", 1))
        if not vlan_id:
            continue
        vlans.append(VLAN(
            vlan_id=int(vlan_id),
            vlan_name=str(_cell_value(ws, row, headers.get("vlan_name", 2))).strip(),
            description=str(_cell_value(ws, row, headers.get("description", 3))).strip(),
        ))
    return vlans


def _load_interfaces(ws: Worksheet, port_profiles: dict[str, Any]) -> list[Interface]:
    headers = _header_map(ws)
    interfaces: list[Interface] = []
    for row in range(2, ws.max_row + 1):
        device_name = _cell_value(ws, row, headers.get("device_name", 1))
        if not device_name:
            continue
        port_profile = str(_cell_value(ws, row, headers.get("port_profile", 3))).strip()
        template_hint = ""
        if port_profile and port_profiles:
            profile_data = port_profiles.get(port_profile, {})
            template_hint = profile_data.get("template_hint", "")
        access_vlan_raw = _cell_value(ws, row, headers.get("access_vlan", 5))
        voice_vlan_raw = _cell_value(ws, row, headers.get("voice_vlan", 6))
        native_vlan_raw = _cell_value(ws, row, headers.get("native_vlan", 7))
        interfaces.append(Interface(
            device_name=str(device_name).strip(),
            interface_name=str(_cell_value(ws, row, headers.get("interface_name", 2))).strip(),
            port_profile=port_profile,
            description=str(_cell_value(ws, row, headers.get("description", 4))).strip(),
            access_vlan=int(access_vlan_raw) if access_vlan_raw else None,
            voice_vlan=int(voice_vlan_raw) if voice_vlan_raw else None,
            native_vlan=int(native_vlan_raw) if native_vlan_raw else None,
            template_hint=template_hint,
        ))
    return interfaces


def _load_global_settings(ws: Worksheet) -> GlobalSettings:
    """Reads key-value pairs from columns A and B."""
    kv: dict[str, Any] = {}
    for row in range(1, ws.max_row + 1):
        key = ws.cell(row=row, column=1).value
        val = ws.cell(row=row, column=2).value
        if key:
            kv[str(key).strip().lower().replace(" ", "_")] = val
    return GlobalSettings(
        domain_name=str(kv.get("domain_name", "") or "").strip(),
        ntp_servers=_list_field(kv.get("ntp_servers", "")),
        dns_servers=_list_field(kv.get("dns_servers", "")),
        snmp_v3_group=str(kv.get("snmp_v3_group", "") or "").strip(),
        snmp_v3_user=str(kv.get("snmp_v3_user", "") or "").strip(),
        snmp_v3_auth_protocol=str(kv.get("snmp_v3_auth_protocol", "SHA") or "SHA").strip().upper(),
        snmp_v3_auth_password=str(kv.get("snmp_v3_auth_password", "") or "").strip(),
        snmp_v3_priv_protocol=str(kv.get("snmp_v3_priv_protocol", "AES") or "AES").strip().upper(),
        snmp_v3_priv_password=str(kv.get("snmp_v3_priv_password", "") or "").strip(),
        snmp_host=str(kv.get("snmp_host", "") or "").strip(),
        syslog_server=str(kv.get("syslog_server", "") or "").strip(),
        banner_motd=str(kv.get("banner_motd", "") or "AUTHORISED ACCESS ONLY. Disconnect immediately if not authorised.").strip(),
        enable_secret=str(kv.get("enable_secret", "changeme") or "changeme").strip(),
        local_username=str(kv.get("local_username", "") or "").strip(),
        local_password=str(kv.get("local_password", "changeme") or "changeme").strip(),
        aaa_server=str(kv.get("aaa_server", "") or "").strip(),
        aaa_key=str(kv.get("aaa_key", "") or "").strip(),
    )


def _load_feature_selection(ws: Worksheet) -> FeatureSelection:
    """Reads feature name (col A) and enabled Yes/No (col B)."""
    kv: dict[str, bool] = {}
    for row in range(2, ws.max_row + 1):
        name = ws.cell(row=row, column=1).value
        val = ws.cell(row=row, column=2).value
        if name:
            kv[str(name).strip().lower().replace(" ", "_")] = str(val).strip().lower() in ("yes", "true", "1")
    return FeatureSelection(
        base_config=kv.get("base_config", True),
        vlans=kv.get("vlans", True),
        interfaces=kv.get("interfaces", True),
    )


def load_workbook(path: str | Path, port_profiles: dict[str, Any] | None = None) -> Intent:
    """Parse an intent workbook and return an Intent object."""
    wb: Workbook = openpyxl.load_workbook(str(path), data_only=True)
    sheet_names = [s.lower() for s in wb.sheetnames]

    def _get_sheet(name: str) -> Worksheet | None:
        for sname in wb.sheetnames:
            if sname.lower() == name:
                return wb[sname]
        return None

    devices_ws = _get_sheet("devices")
    vlans_ws = _get_sheet("vlans")
    interfaces_ws = _get_sheet("interfaces")
    global_ws = _get_sheet("global settings")
    features_ws = _get_sheet("feature selection")

    return Intent(
        devices=_load_devices(devices_ws) if devices_ws else [],
        vlans=_load_vlans(vlans_ws) if vlans_ws else [],
        interfaces=_load_interfaces(interfaces_ws, port_profiles or {}) if interfaces_ws else [],
        global_settings=_load_global_settings(global_ws) if global_ws else GlobalSettings(),
        feature_selection=_load_feature_selection(features_ws) if features_ws else FeatureSelection(),
    )
