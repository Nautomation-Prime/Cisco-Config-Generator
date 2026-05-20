# Cisco Config Generator

> Generate per-device Cisco IOS-XE access switch configuration files from an Excel intent workbook.
> Built by **Nautomation Prime**.

---

## Overview

The Cisco Config Generator reads network intent from a structured Excel workbook and renders
per-device `.cfg` files using Jinja2 templates. It is designed as a customisable product:
the core Python engine never needs to change between customers — all site-specific templates
and settings live in a **pack** folder.

```
Excel intent → Python core → Jinja2 templates → per-device .cfg files
```

---

## Quick Start

### 1. Setup (Windows)

```bat
setup.bat
```

This downloads a portable Python 3.12 runtime and installs all dependencies.
Internet connection required (one-time only).

### 2. Generate the intent workbook template

The workbook template is auto-generated on first run. To regenerate it manually:

```bat
python_runtime\python.exe scripts\generate_workbook.py
```

This creates `assets/workbook_template.xlsx`. Open it, fill in your intent, and save.

### 3. Run the tool

```bat
run.bat
```

The interactive TUI will launch. Select your pack, point to your workbook, and click **Run**.

### Headless (no TUI)

```bat
python_runtime\python.exe -m cisco_config_generator --no-tui --workbook assets\workbook_template.xlsx
```

Generated configs are written to `output\<hostname>.cfg`.

---

## CLI Reference

```
run.bat [OPTIONS]
python_runtime\python.exe -m cisco_config_generator [OPTIONS]

Options:
  -p, --pack TEXT       Pack name (folder under packs/) or full path  [default: default]
  -w, --workbook PATH   Path to the intent workbook (.xlsx)
  -o, --output TEXT     Directory to write generated config files     [default: output]
  --no-tui              Run headless without the interactive TUI
  --version             Print version and exit
```

---

## ACL Workflow

ACLs are defined in the **ACLs** sheet and referenced by name in **Global Settings**.

**Step 1 — Define ACLs in the ACLs sheet:**

| ACL Name | Remark | Action | Network/Host | Wildcard |
|----------|--------|--------|--------------|----------|
| ACL_VTY_ACCESS | Management hosts | permit | 10.0.0.0 | 0.0.0.255 |
| ACL_VTY_ACCESS | | deny | any | |
| ACL_SNMP_RO_ACCESS | NMS server | permit | 10.1.1.100 | |
| ACL_SNMP_RO_ACCESS | | deny | any | |

- Leave **Wildcard** blank for host entries (`permit 10.1.1.100`) or `deny any`
- Add a **Remark** row (no Action/Network) before permit/deny lines for readability

**Step 2 — Reference ACL names in Global Settings:**

| Setting | Example Value |
|---------|---------------|
| `vty_acl` | ACL_VTY_ACCESS |
| `snmp_ro_acl` | ACL_SNMP_RO_ACCESS |
| `snmp_rw_acl` | ACL_SNMP_RW_ACCESS |

The generator validates that every ACL name referenced in Global Settings is defined in the ACLs sheet. To disable ACL generation entirely, set **ACLs → No** in the Feature Selection sheet.

---

## Excel Workbook Sheets

| Sheet | Purpose |
|-------|---------|
| **Devices** | One row per switch — hostname, IP, model, uplink module |
| **Global Settings** | Shared settings — NTP, DNS, SNMP, banner, AAA, ACL names |
| **VLANs** | VLAN ID, name, description |
| **Interfaces** | Per-device per-port intent — profile selection + description |
| **ACLs** | Standard ACL entries — name, remark, action, network/host, wildcard |
| **Feature Selection** | Toggle which config sections to generate (Yes/No) |

---

## Pack System

All customer-facing configuration lives in `packs/<name>/`:

```
packs/default/
├─ settings.yaml          # Defaults (unused VLAN, native VLAN, log level)
├─ hardware_catalog.yaml  # Switch models and uplink modules
├─ port_profiles.yaml     # Port profile definitions
├─ template_map.yaml      # Maps profiles/features to Jinja2 templates
├─ features.yaml          # Feature toggle defaults
└─ templates/
   ├─ acls.j2
   ├─ base.j2
   ├─ vlans.j2
   ├─ interfaces_access.j2
   ├─ interfaces_access_server.j2
   ├─ interfaces_trunk.j2
   ├─ interfaces_trunk_portchannel.j2
   ├─ interfaces_trunk_server.j2
   ├─ interfaces_ap_trunk.j2
   └─ interfaces_unused.j2
```

To create a customer pack:
1. Copy `packs/default/` to `packs/<customer-name>/`
2. Edit the templates and YAML files
3. Select the pack in the TUI or via `--pack <name>`

---

## Template Context

All Jinja2 templates receive:

```python
{
    "device":     Device,           # hostname, mgmt_ip, model, timezone...
    "vlans":      [VLAN],           # full VLAN list
    "interfaces": [Interface],      # interfaces for this device (filtered per template group)
    "global":     GlobalSettings,   # NTP, SNMP, AAA, banner, ACL names...
    "hardware":   HardwareProfile,  # port counts and interface naming
    "acls":       [ACLEntry],       # all ACL entries (for acls.j2)
    "features":   FeatureSelection, # feature flags (base_config, vlans, interfaces, acls)
    "settings":   {"defaults": {}}  # pack defaults (unused_vlan, native_vlan)
}
```

---

## Hardware Catalog

Supported switch models and uplink modules are defined in `hardware_catalog.yaml`.

| Switch Model | Access Ports |
|---|---|
| C9200-48P | 48 |
| C9200-24P | 24 |
| C9300-48P | 48 |
| C9300-24P | 24 |
| C2960X-48FPD-L | 48 |
| C2960X-24PD-L | 24 |

| Uplink Module | Ports |
|---|---|
| NM-4X | 4 × 10G SFP+ |
| NM-8X | 8 × 10G SFP+ |
| C9200-NM-4X | 4 × 10G SFP+ |
| NONE | No uplink module |

---

## Port Profiles

| Profile | Type | Notes |
|---------|------|-------|
| `access-user` | Access | Standard PC port |
| `access-voip` | Access + Voice VLAN | Data + voice VLAN, QoS DSCP trust |
| `access-printer` | Access | Printer port |
| `access-video` | Access | Video device, QoS DSCP trust |
| `access-special` | Access | Special purpose |
| `access-control` | Access | Door entry / access control |
| `access-server` | Access | Server port |
| `access-ap` | Access | Wireless AP (access mode) |
| `access-ap-trunk` | Trunk | Wireless AP (trunk mode, native VLAN = AP VLAN) |
| `trunk-uplink` | Trunk | Uplink to core/distribution |
| `trunk-uplink-portchannel` | Trunk + Port-Channel | Uplink with port-channel |
| `trunk-server` | Trunk | Server trunk port |
| `unused` | Disabled | Unused/shutdown port |

---

## Running Tests

```bat
python_runtime\python.exe -m pytest tests/ -v
```

---

## Requirements

- Windows (launcher scripts are `.bat`)
- Internet connection for first-time setup (downloads portable Python 3.12)
- See `requirements.txt` for Python dependencies

---

## Project Structure

```
Cisco-Config-Generator/
├─ cisco_config_generator/   # Core Python package
│  ├─ workbook/              # Excel parsing and validation
│  ├─ rendering/             # Jinja2 engine and file writer
│  └─ tui/                   # Textual interactive UI
├─ packs/                    # Customer packs (YAML + templates)
├─ scripts/                  # Utility scripts
├─ assets/                   # Generated workbook template
├─ output/                   # Generated config files
├─ tests/                    # pytest test suite
├─ setup.bat                 # First-time setup
└─ run.bat                   # Launch the tool
```

---

*Cisco Config Generator — Nautomation Prime*
