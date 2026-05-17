#!/usr/bin/env python3
"""
Generate the intent workbook template: assets/workbook_template.xlsx

Run from the repo root:
    python scripts/generate_workbook.py
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    import openpyxl
except ImportError:
    print("openpyxl not installed. Run: pip install -r requirements.txt")
    sys.exit(1)

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.utils import get_column_letter

# Resolve pack config so dropdowns use real values
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

import yaml

HARDWARE_CATALOG = yaml.safe_load((REPO_ROOT / "packs/default/hardware_catalog.yaml").read_text())
PORT_PROFILES = yaml.safe_load((REPO_ROOT / "packs/default/port_profiles.yaml").read_text())

MODELS = list(HARDWARE_CATALOG["switch_models"].keys())
UPLINK_MODULES = list(HARDWARE_CATALOG["uplink_modules"].keys())
PROFILES = list(PORT_PROFILES["profiles"].keys())

HEADER_FILL = PatternFill("solid", fgColor="1F3864")
HEADER_FONT = Font(color="FFFFFF", bold=True)
ALT_FILL = PatternFill("solid", fgColor="DCE6F1")


def style_header(ws, headers: list[str], row: int = 1) -> None:
    for col, header in enumerate(headers, start=1):
        cell = ws.cell(row=row, column=col)
        cell.value = header
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(col)].width = 22


def add_list_validation(ws, col: int, formula: str, start_row: int = 2, end_row: int = 200) -> None:
    col_letter = get_column_letter(col)
    dv = DataValidation(
        type="list",
        formula1=formula,
        allow_blank=True,
        showDropDown=False,
        showErrorMessage=True,
        error="Please select a valid value from the dropdown.",
        errorTitle="Invalid Value",
    )
    ws.add_data_validation(dv)
    dv.sqref = f"{col_letter}{start_row}:{col_letter}{end_row}"


# -----------------------------------------------------------------------
# Sheet 1 — Devices
# -----------------------------------------------------------------------
def create_devices_sheet(wb: Workbook) -> None:
    ws = wb.active
    ws.title = "Devices"
    headers = [
        "Hostname", "Mgmt IP", "Mgmt VLAN", "Default Gateway",
        "Model", "Uplink Module", "Site", "Timezone", "Mgmt Subnet"
    ]
    style_header(ws, headers)

    # Model dropdown
    models_formula = '"' + ",".join(MODELS) + '"'
    add_list_validation(ws, col=5, formula=models_formula)

    # Uplink module dropdown
    modules_formula = '"' + ",".join(UPLINK_MODULES) + '"'
    add_list_validation(ws, col=6, formula=modules_formula)

    # Example row
    ws.append([
        "SW-OFFICE-01", "10.0.10.2", 10, "10.0.10.1",
        MODELS[0], UPLINK_MODULES[0], "Head Office", "GMT", "255.255.255.0"
    ])


# -----------------------------------------------------------------------
# Sheet 2 — Global Settings
# -----------------------------------------------------------------------
def create_global_settings_sheet(wb: Workbook) -> None:
    ws = wb.create_sheet("Global Settings")
    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 45

    ws.cell(row=1, column=1).value = "Setting"
    ws.cell(row=1, column=2).value = "Value"
    ws.cell(row=1, column=1).font = HEADER_FONT
    ws.cell(row=1, column=1).fill = HEADER_FILL
    ws.cell(row=1, column=2).font = HEADER_FONT
    ws.cell(row=1, column=2).fill = HEADER_FILL

    rows = [
        ("domain_name", "example.local"),
        ("ntp_servers", "10.0.0.1, 10.0.0.2"),
        ("dns_servers", "8.8.8.8, 8.8.4.4"),
        ("snmp_community", "public"),
        ("snmp_host", "10.0.0.5"),
        ("syslog_server", "10.0.0.6"),
        ("banner_motd", "AUTHORISED ACCESS ONLY. Disconnect immediately if not authorised."),
        ("enable_secret", "changeme"),
        ("local_username", "admin"),
        ("local_password", "changeme"),
        ("aaa_server", ""),
        ("aaa_key", ""),
    ]
    for row_data in rows:
        ws.append(row_data)


# -----------------------------------------------------------------------
# Sheet 3 — VLANs
# -----------------------------------------------------------------------
def create_vlans_sheet(wb: Workbook) -> None:
    ws = wb.create_sheet("VLANs")
    headers = ["VLAN ID", "VLAN Name", "Description"]
    style_header(ws, headers)
    example_vlans = [
        (10, "MGMT", "Management VLAN"),
        (20, "DATA", "User Data VLAN"),
        (30, "VOICE", "VoIP VLAN"),
        (40, "WIRELESS", "Wireless VLAN"),
        (999, "UNUSED", "Unused ports VLAN"),
    ]
    for vlan in example_vlans:
        ws.append(vlan)


# -----------------------------------------------------------------------
# Sheet 4 — Interfaces
# -----------------------------------------------------------------------
def create_interfaces_sheet(wb: Workbook) -> None:
    ws = wb.create_sheet("Interfaces")
    headers = [
        "Device Name", "Interface Name", "Port Profile",
        "Description", "Access VLAN", "Voice VLAN"
    ]
    style_header(ws, headers)

    # Port profile dropdown
    profiles_formula = '"' + ",".join(PROFILES) + '"'
    add_list_validation(ws, col=3, formula=profiles_formula)

    # Access VLAN uses the VLANs sheet (indirect — user selects VLAN ID manually)
    # Note: cross-sheet dropdowns require a named range in Excel
    # We reference column A of VLANs sheet via named range workaround
    # Simple approach: just provide text hint in header
    ws.column_dimensions["A"].width = 22
    ws.column_dimensions["B"].width = 30
    ws.column_dimensions["C"].width = 20
    ws.column_dimensions["D"].width = 35
    ws.column_dimensions["E"].width = 16
    ws.column_dimensions["F"].width = 16

    example_rows = [
        ("SW-OFFICE-01", "GigabitEthernet1/0/1", "access-user", "PC - Desk 1", 20, ""),
        ("SW-OFFICE-01", "GigabitEthernet1/0/2", "access-voip", "Phone - Desk 1", 20, 30),
        ("SW-OFFICE-01", "GigabitEthernet1/0/3", "access-ap", "WAP - Lobby", 40, ""),
        ("SW-OFFICE-01", "TenGigabitEthernet1/1/1", "trunk-uplink", "Uplink to Core", "", ""),
        ("SW-OFFICE-01", "GigabitEthernet1/0/48", "unused", "", "", ""),
    ]
    for row in example_rows:
        ws.append(row)


# -----------------------------------------------------------------------
# Sheet 5 — Feature Selection
# -----------------------------------------------------------------------
def create_feature_selection_sheet(wb: Workbook) -> None:
    ws = wb.create_sheet("Feature Selection")
    ws.column_dimensions["A"].width = 25
    ws.column_dimensions["B"].width = 12
    ws.column_dimensions["C"].width = 45

    ws.cell(row=1, column=1).value = "Feature"
    ws.cell(row=1, column=2).value = "Enabled"
    ws.cell(row=1, column=3).value = "Description"
    for col in range(1, 4):
        ws.cell(row=1, column=col).font = HEADER_FONT
        ws.cell(row=1, column=col).fill = HEADER_FILL

    # Yes/No dropdown for Enabled column
    dv = DataValidation(
        type="list",
        formula1='"Yes,No"',
        allow_blank=False,
        showDropDown=False,
    )
    ws.add_data_validation(dv)
    dv.sqref = "B2:B50"

    features = [
        ("base_config", "Yes", "Base switch configuration (hostname, AAA, NTP, SNMP, STP)"),
        ("vlans", "Yes", "VLAN definitions"),
        ("interfaces", "Yes", "Interface configuration"),
    ]
    for row in features:
        ws.append(row)


def main() -> None:
    output_path = REPO_ROOT / "assets" / "workbook_template.xlsx"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook()

    create_devices_sheet(wb)
    create_global_settings_sheet(wb)
    create_vlans_sheet(wb)
    create_interfaces_sheet(wb)
    create_feature_selection_sheet(wb)

    wb.save(str(output_path))
    print(f"Workbook template generated: {output_path}")


if __name__ == "__main__":
    main()
