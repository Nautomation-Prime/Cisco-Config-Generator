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
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.utils import get_column_letter
from openpyxl.workbook.defined_name import DefinedName

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

import yaml

from cisco_config_generator.site_loader import list_available_sites, load_site, SITES_DIR

HARDWARE_CATALOG = yaml.safe_load((REPO_ROOT / "packs/default/hardware_catalog.yaml").read_text())
PORT_PROFILES = yaml.safe_load((REPO_ROOT / "packs/default/port_profiles.yaml").read_text())
# The Feature Selection sheet is built from features.yaml so the list lives in one place.
FEATURES = yaml.safe_load((REPO_ROOT / "packs/default/features.yaml").read_text(encoding="utf-8"))["features"]

MODELS = list(HARDWARE_CATALOG["switch_models"].keys())
UPLINK_MODULES = list(HARDWARE_CATALOG["uplink_modules"].keys())
PROFILES = list(PORT_PROFILES["profiles"].keys())
SITES = list_available_sites(SITES_DIR)

# --- Styles ---
HEADER_FILL = PatternFill("solid", fgColor="1F3864")
HEADER_FONT = Font(color="FFFFFF", bold=True, name="Calibri", size=11)
ROW_FILL_ALT = PatternFill("solid", fgColor="DCE6F1")
ROW_FILL_NORM = PatternFill("solid", fgColor="FFFFFF")
NORMAL_FONT = Font(name="Calibri", size=11)
BOLD_FONT = Font(name="Calibri", size=11, bold=True)
_BORDER_SIDE = Side(style="thin", color="B8CCE4")

# --- Tab colours ---
TAB_GREY = "595959"
TAB_BLUE = "1F3864"
TAB_GREEN = "375623"
TAB_ORANGE = "C55A11"
TAB_PURPLE = "7030A0"
TAB_TEAL = "0070C0"
TAB_RED = "C00000"


def _border() -> Border:
    return Border(left=_BORDER_SIDE, right=_BORDER_SIDE, top=_BORDER_SIDE, bottom=_BORDER_SIDE)


def style_header(ws, headers: list[str], widths: list[int] | None = None, row: int = 1) -> None:
    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=row, column=col_idx)
        cell.value = header
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = _border()
        ws.column_dimensions[get_column_letter(col_idx)].width = (widths[col_idx - 1] if widths else 22)
    ws.row_dimensions[row].height = 25


def apply_row_style(ws, row: int, num_cols: int, alt: bool = False) -> None:
    fill = ROW_FILL_ALT if alt else ROW_FILL_NORM
    for col in range(1, num_cols + 1):
        cell = ws.cell(row=row, column=col)
        cell.fill = fill
        cell.font = NORMAL_FONT
        cell.border = _border()
        cell.alignment = Alignment(vertical="center")
    ws.row_dimensions[row].height = 18


def add_list_validation(ws, col: int, formula: str, start_row: int = 2, end_row: int = 300) -> None:
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


def add_whole_number_validation(ws, col: int, minimum: int, maximum: int, start_row: int = 2, end_row: int = 300) -> None:
    """VLAN ID columns can't offer a live dropdown (VLANs are defined per-site in sites/*.yaml,
    not in the workbook), so just range-check the number. See the Site Reference sheet for the
    VLAN IDs each site actually defines."""
    col_letter = get_column_letter(col)
    dv = DataValidation(
        type="whole",
        operator="between",
        formula1=str(minimum),
        formula2=str(maximum),
        allow_blank=True,
        showErrorMessage=True,
        error=f"Enter a whole number between {minimum} and {maximum}.",
        errorTitle="Invalid VLAN ID",
    )
    ws.add_data_validation(dv)
    dv.sqref = f"{col_letter}{start_row}:{col_letter}{end_row}"


def add_named_ranges(wb: Workbook) -> None:
    """Named ranges enable cross-sheet dropdown references in Excel."""
    wb.defined_names["DeviceNames"] = DefinedName("DeviceNames", attr_text="Devices!$A$2:$A$300")


# -----------------------------------------------------------------------
# Instructions sheet (inserted at position 0 — first tab)
# -----------------------------------------------------------------------
def create_instructions_sheet(wb: Workbook) -> None:
    ws = wb.create_sheet("Instructions", 0)
    ws.sheet_properties.tabColor = TAB_GREY
    ws.sheet_view.showGridLines = False
    ws.column_dimensions["A"].width = 24
    ws.column_dimensions["B"].width = 65

    # Title
    ws.merge_cells("A1:B1")
    title = ws.cell(row=1, column=1)
    title.value = "Cisco Config Generator — Intent Workbook"
    title.font = Font(name="Calibri", size=16, bold=True, color="1F3864")
    title.alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[1].height = 36

    ws.merge_cells("A2:B2")
    sub = ws.cell(row=2, column=1)
    sub.value = "Nautomation Prime  |  Fill in all sheets then run the tool to generate configs."
    sub.font = Font(name="Calibri", size=11, italic=True, color="595959")
    ws.row_dimensions[2].height = 18
    ws.row_dimensions[3].height = 8  # spacer

    # Sheet guide table
    guide = [
        ("Sheet", "What to fill in"),
        ("Devices", "One row per switch. Select Model, Uplink Module and Site from the dropdowns. Model/Uplink Module drive the full physical interface inventory used by the generator; Site selects which sites/<name>.yaml file supplies this device's NTP/DNS/SNMP/AAA/banner, VLANs and ACLs (see the Site Reference sheet). Each device needs a unique Hostname, Management IP, VLAN, Default Gateway; Timezone and Mgmt Subnet may be left blank to inherit the site's (or the pack's) default."),
        ("Interfaces", "Add rows only for ports that need explicit config. The generator derives the full interface list from each device's selected Model and Uplink Module; any omitted ports default to the unused profile and render as shutdown ports. Access/Voice/Native VLAN columns take the VLAN ID directly — check the Site Reference sheet for the VLAN IDs that device's site actually defines. Trunk and AP-trunk ports use Native VLAN, optional Allowed VLANs, optional Storm Control Broadcast/Multicast overrides, and Port Channel No. where required; access ports use Access/Voice VLAN."),
        ("Port-Channels", "Optional. Leave it empty and each Port-channel interface takes its settings from its member ports (the rows sharing a Port Channel No. on the Interfaces sheet). Add a row only to make a Port-channel differ from its members: fill in just the cells to change - blank cells keep the members' values."),
        ("Feature Selection", "Toggle which config sections to generate (Yes/No). The top-level 'base_config' flag controls whether the base config runs at all. Sub-features (aaa, snmp, ntp, dhcp_snooping, spanning_tree, banner) let you skip individual sections within the base config \u2014 useful if those sections are already deployed or managed by another system."),
        ("Site Reference", "Read-only. Lists every sites/<name>.yaml file found when this workbook was generated, with its VLANs and ACL names, so you know what to type into the Devices/Interfaces sheets. Not read back by the generator — edit the site YAML files themselves, then re-run this script to refresh this sheet."),
    ]
    for i, (sheet, desc) in enumerate(guide):
        row = i + 4
        a = ws.cell(row=row, column=1, value=sheet)
        b = ws.cell(row=row, column=2, value=desc)
        if i == 0:
            a.font = HEADER_FONT
            b.font = HEADER_FONT
            a.fill = HEADER_FILL
            b.fill = HEADER_FILL
            a.alignment = Alignment(horizontal="center", vertical="center")
            b.alignment = Alignment(horizontal="left", vertical="center")
            ws.row_dimensions[row].height = 22
        else:
            fill = ROW_FILL_ALT if i % 2 == 0 else ROW_FILL_NORM
            a.font = BOLD_FONT
            b.font = NORMAL_FONT
            a.fill = fill
            b.fill = fill
            b.alignment = Alignment(wrap_text=True, vertical="top")
            ws.row_dimensions[row].height = 38

    ws.row_dimensions[len(guide) + 5].height = 10  # spacer

    # Tips section
    tips_row = len(guide) + 6
    ws.merge_cells(f"A{tips_row}:B{tips_row}")
    tip_hdr = ws.cell(row=tips_row, column=1, value="Tips")
    tip_hdr.font = Font(name="Calibri", size=12, bold=True, color="1F3864")
    ws.row_dimensions[tips_row].height = 22

    tips = [
        "• Fill in the VLANs sheet before the Interfaces sheet so VLAN dropdowns are populated.",
        "• Fill in the Devices sheet before the Interfaces sheet so the Device Name dropdown works and the generator can derive the full port inventory.",
        "• You only need to add rows on the Interfaces sheet for ports that are in use or need custom settings. Omitted ports are auto-generated as unused from the selected model and uplink module.",
        "• To add a new switch model or port profile, edit the YAML files in packs/default/ and re-run scripts/generate_workbook.py.",
        "• Save your completed workbook with a descriptive name (e.g. site-london-2024.xlsx).",
        "• Generated configs are written to the output\\ folder — one .cfg file per device.",
    ]
    for j, tip in enumerate(tips):
        r = tips_row + 1 + j
        ws.merge_cells(f"A{r}:B{r}")
        cell = ws.cell(row=r, column=1, value=tip)
        cell.font = NORMAL_FONT
        cell.alignment = Alignment(wrap_text=True, vertical="center")
        ws.row_dimensions[r].height = 18


# -----------------------------------------------------------------------
# Sheet 1 — Devices
# -----------------------------------------------------------------------
def create_devices_sheet(wb: Workbook) -> None:
    ws = wb.active
    ws.title = "Devices"
    ws.sheet_properties.tabColor = TAB_BLUE
    ws.freeze_panes = "A2"

    headers = ["Hostname", "Mgmt IP", "Mgmt VLAN", "Default Gateway",
               "Model", "Uplink Module", "Site", "Timezone", "Timezone Hours", "Timezone Minutes", "Mgmt Subnet"]
    widths = [22, 18, 14, 20, 22, 20, 20, 14, 16, 18, 18]
    style_header(ws, headers, widths=widths)

    add_list_validation(ws, col=5, formula='"' + ",".join(MODELS) + '"')
    add_list_validation(ws, col=6, formula='"' + ",".join(UPLINK_MODULES) + '"')
    if SITES:
        add_list_validation(ws, col=7, formula='"' + ",".join(SITES) + '"')

    example_site = SITES[0] if SITES else "site-a"
    example_rows = [
        ("SW-OFFICE-01", "10.0.10.2", 10, "10.0.10.1", MODELS[0], UPLINK_MODULES[0], example_site, "", "", "", ""),
        ("SW-OFFICE-02", "10.0.10.3", 10, "10.0.10.1", MODELS[1], UPLINK_MODULES[0], example_site, "", "", "", ""),
    ]
    for i, row_data in enumerate(example_rows):
        ws.append(row_data)
        apply_row_style(ws, ws.max_row, len(headers), alt=(i % 2 == 1))


# -----------------------------------------------------------------------
# Sheet 2 — Site Reference (read-only; generated from sites/*.yaml)
# -----------------------------------------------------------------------
def create_site_reference_sheet(wb: Workbook) -> None:
    """Not read back by the generator — a convenience lookup so the person
    filling in Devices/Interfaces can see what each site actually defines
    (its VLAN IDs/names and ACL names) without opening the YAML files.
    Global settings (NTP/DNS/SNMP/AAA/banner/credentials) live only in the
    site YAML — they aren't duplicated here since they're not needed to
    fill in the workbook.
    """
    ws = wb.create_sheet("Site Reference")
    ws.sheet_properties.tabColor = TAB_GREEN
    ws.freeze_panes = "A2"

    style_header(ws, ["Site", "VLAN ID", "VLAN Name", "VLAN Description", "ACL Names Defined"],
                 widths=[20, 12, 22, 38, 40])

    if not SITES:
        ws.cell(row=2, column=1, value="No sites/*.yaml files found — see docs/RUNBOOK.md to create one.")
        apply_row_style(ws, 2, 5)
        return

    row_idx = 2
    for site_name in SITES:
        try:
            site = load_site(site_name, SITES_DIR)
        except Exception as exc:  # keep workbook generation resilient to one bad site file
            ws.cell(row=row_idx, column=1, value=site_name)
            ws.cell(row=row_idx, column=2, value=f"ERROR: {exc}")
            apply_row_style(ws, row_idx, 5, alt=(row_idx % 2 == 0))
            row_idx += 1
            continue

        acl_names = ", ".join(sorted({acl.acl_name for acl in site.acls if acl.acl_name})) or "(none)"
        vlans = site.vlans or [None]
        for vlan in vlans:
            if vlan is None:
                ws.append([site_name, "(no VLANs defined)", "", "", acl_names])
            else:
                ws.append([site_name, vlan.vlan_id, vlan.vlan_name, vlan.description, acl_names])
            apply_row_style(ws, ws.max_row, 5, alt=(row_idx % 2 == 0))
            row_idx += 1


# -----------------------------------------------------------------------
# Sheet 3 — Interfaces
# -----------------------------------------------------------------------
def create_interfaces_sheet(wb: Workbook) -> None:
    ws = wb.create_sheet("Interfaces")
    ws.sheet_properties.tabColor = TAB_PURPLE
    ws.freeze_panes = "A3"  # keep header row and instruction row visible while scrolling

    headers = ["Device Name", "Interface Name", "Port Profile",
               "Description", "Access VLAN", "Voice VLAN", "Native VLAN", "Allowed VLANs",
               "Storm Control Broadcast", "Storm Control Multicast", "Port Channel No."]
    widths = [22, 32, 24, 40, 14, 14, 14, 22, 24, 24, 16]
    style_header(ws, headers, widths=widths)

    # Instruction row (row 2).
    # Column A is left empty so the workbook loader skips this row (it skips rows with no Device Name).
    # The instruction text spans columns B–K as a merged cell.
    INFO_FILL = PatternFill("solid", fgColor="FFF2CC")
    INFO_FONT = Font(name="Calibri", size=10, italic=True, color="7F6000")

    ws.cell(row=2, column=1).fill = INFO_FILL
    ws.cell(row=2, column=1).border = _border()

    ws.merge_cells("B2:K2")
    instr = ws.cell(row=2, column=2)
    instr.value = (
        "HOW TO USE:  Each row configures one switch port.  "
        "Set Device Name (must match the Devices sheet), choose a Port Profile, enter a Description, "
        "and fill in the VLAN column(s) required by the chosen profile.  "
        "The first four rows are filled with examples showing common port types — update or replace them as needed.  "
        "For a 24-port switch, delete rows GigabitEthernet1/0/25 to GigabitEthernet1/0/48.  "
        "Ports NOT listed in this sheet are automatically generated as 'unused' (shutdown) ports — "
        "only add rows for ports that need explicit configuration.  "
        "The four TenGigabitEthernet uplink rows at the bottom are pre-set for port-channel uplinks; "
        "update Native VLAN, Allowed VLANs, and Port Channel No. to match your environment."
    )
    instr.font = INFO_FONT
    instr.fill = INFO_FILL
    instr.alignment = Alignment(wrap_text=True, vertical="center")
    instr.border = _border()
    ws.row_dimensions[2].height = 52

    for col in range(3, len(headers) + 1):
        c = ws.cell(row=2, column=col)
        c.fill = INFO_FILL
        c.border = _border()

    # Data validations
    add_list_validation(ws, col=1, formula="DeviceNames")
    add_list_validation(ws, col=3, formula='"' + ",".join(PROFILES) + '"')
    add_whole_number_validation(ws, col=5, minimum=1, maximum=4094)
    add_whole_number_validation(ws, col=6, minimum=1, maximum=4094)
    add_whole_number_validation(ws, col=7, minimum=1, maximum=4094)

    device = "SW-OFFICE-01"

    # First four ports are complete examples covering common port types.
    # VLANs reference example IDs from the Site Reference sheet (DATA=20, VOICE=30, WIRELESS=40
    # in the default sites/site-a.yaml — check yours if you copied a different site).
    example_rows = [
        (device, "GigabitEthernet1/0/1", "access-voip",    "CLIENT: PC/Phone - Desk 1",   20, 30, "",  "",              "",          "",          ""),
        (device, "GigabitEthernet1/0/2", "access-printer",  "PRINTER: Floor 1 Copier",     20, "",  "",  "",              "",          "",          ""),
        (device, "GigabitEthernet1/0/3", "access-ap-trunk", "WAP - Lobby",                 "", "",  40,  "10,20,30,40",   "1.00 0.70", "1.00 0.70", ""),
        (device, "GigabitEthernet1/0/4", "access-user",     "CLIENT: Data only - Desk 4",  20, "",  "",  "",              "",          "",          ""),
    ]
    for i, row_data in enumerate(example_rows):
        ws.append(row_data)
        apply_row_style(ws, ws.max_row, len(headers), alt=(i % 2 == 1))

    # Remaining access ports — GigabitEthernet1/0/5 through GigabitEthernet1/0/48
    # Profile pre-set to access-voip (most common). Fill in VLANs and description per port.
    for i, port in enumerate(range(5, 49)):
        row_data = (
            device,
            f"GigabitEthernet1/0/{port}",
            "access-voip",
            "",  # description
            "",  # access vlan
            "",  # voice vlan
            "",  # native vlan
            "",  # allowed vlans
            "",  # storm control broadcast
            "",  # storm control multicast
            "",  # port channel no.
        )
        ws.append(row_data)
        apply_row_style(ws, ws.max_row, len(headers), alt=(i % 2 == 1))

    # 4 NM-4X uplink ports — TenGigabitEthernet1/1/1 through TenGigabitEthernet1/1/4
    # Pre-configured as two port-channels: Po1 = Te1/1/1+Te1/1/2, Po2 = Te1/1/3+Te1/1/4
    for i, port in enumerate(range(1, 5)):
        po_num = 1 if port <= 2 else 2
        row_data = (
            device,
            f"TenGigabitEthernet1/1/{port}",
            "trunk-uplink-portchannel",
            f"L:Po{po_num}  R:Po{po_num} Uplink to Core",
            "",          # access vlan
            "",          # voice vlan
            "",          # native vlan — fill in
            "",          # allowed vlans — fill in
            "1.00 0.70", # storm control broadcast
            "1.00 0.70", # storm control multicast
            po_num,      # port channel number
        )
        ws.append(row_data)
        apply_row_style(ws, ws.max_row, len(headers), alt=(i % 2 == 1))


# -----------------------------------------------------------------------
# Sheet 4 — Port-Channels
# -----------------------------------------------------------------------
def create_port_channels_sheet(wb: Workbook) -> None:
    ws = wb.create_sheet("Port-Channels")
    ws.sheet_properties.tabColor = TAB_ORANGE
    ws.freeze_panes = "A2"

    headers = ["Device Name", "Port Channel No.", "Description", "Native VLAN", "Allowed VLANs", "Storm Control Broadcast", "Storm Control Multicast"]
    widths = [22, 16, 40, 14, 22, 24, 24]
    style_header(ws, headers, widths=widths)

    # No example rows: every row here is applied, so an example left in place
    # would silently override a real port-channel. Instruction row only -
    # column A is left empty so the workbook loader skips it.
    INFO_FILL = PatternFill("solid", fgColor="FFF2CC")
    INFO_FONT = Font(name="Calibri", size=10, italic=True, color="7F6000")

    ws.cell(row=2, column=1).fill = INFO_FILL
    ws.cell(row=2, column=1).border = _border()

    ws.merge_cells(f"B2:{get_column_letter(len(headers))}2")
    instr = ws.cell(row=2, column=2)
    instr.value = (
        "OPTIONAL:  Leave this sheet empty and each Port-channel interface takes its settings from its "
        "member ports — the Interfaces rows sharing its Port Channel No.  "
        "Add a row only to make a Port-channel differ from its members: set Device Name and Port Channel No., "
        "then fill in just the cells to change.  Blank cells keep the members' values."
    )
    instr.font = INFO_FONT
    instr.fill = INFO_FILL
    instr.alignment = Alignment(wrap_text=True, vertical="center")
    instr.border = _border()
    ws.row_dimensions[2].height = 45

    for col in range(3, len(headers) + 1):
        c = ws.cell(row=2, column=col)
        c.fill = INFO_FILL
        c.border = _border()

    add_list_validation(ws, col=1, formula="DeviceNames")
    add_whole_number_validation(ws, col=4, minimum=1, maximum=4094)


# -----------------------------------------------------------------------
# Sheet 5 — Feature Selection
# -----------------------------------------------------------------------
def create_feature_selection_sheet(wb: Workbook) -> None:
    ws = wb.create_sheet("Feature Selection")
    ws.sheet_properties.tabColor = TAB_TEAL
    ws.freeze_panes = "A2"

    style_header(ws, ["Feature", "Enabled", "Description"], widths=[22, 12, 55])
    add_list_validation(ws, col=2, formula='"Yes,No"', start_row=2, end_row=50)

    features = [
        (f["name"], "Yes" if f.get("enabled_by_default", True) else "No", f.get("description", ""))
        for f in FEATURES
    ]
    for i, row_data in enumerate(features):
        ws.append(row_data)
        apply_row_style(ws, ws.max_row, 3, alt=(i % 2 == 1))


def main() -> None:
    output_path = REPO_ROOT / "assets" / "workbook_template.xlsx"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook()

    # Create sheets (Devices uses wb.active — the default blank sheet)
    create_devices_sheet(wb)
    create_site_reference_sheet(wb)
    create_interfaces_sheet(wb)
    create_port_channels_sheet(wb)
    create_feature_selection_sheet(wb)

    # Named ranges must exist before cross-sheet dropdowns are usable
    add_named_ranges(wb)

    # Insert Instructions as the first tab (shifts all others right)
    create_instructions_sheet(wb)

    try:
        wb.save(str(output_path))
    except PermissionError as exc:
        print(
            f"Could not write workbook template to {output_path} because the file is open. "
            "Close the workbook in Excel and run the generator again."
        )
        raise SystemExit(1) from exc

    print(f"Workbook template generated: {output_path}")


if __name__ == "__main__":
    main()
