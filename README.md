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

This checks for Python 3.10+, creates a virtual environment, and installs all dependencies.

### 2. Generate the intent workbook template

```bat
.venv\Scripts\python.exe scripts\generate_workbook.py
```

This creates `assets/workbook_template.xlsx`. Open it, fill in your intent, and save.

### 3. Run the tool

```bat
run.bat
```

The interactive TUI will launch. Select your pack, point to your workbook, and click **Run**.

### Headless (no TUI)

```bat
.venv\Scripts\python.exe -m cisco_config_generator --no-tui --workbook assets\workbook_template.xlsx
```

Generated configs are written to `output\<hostname>.cfg`.

---

## Excel Workbook Sheets

| Sheet | Purpose |
|-------|---------|
| **Devices** | One row per switch — hostname, IP, model, uplink module |
| **Global Settings** | Shared settings — NTP, DNS, SNMP, banner, AAA |
| **VLANs** | VLAN ID, name, description |
| **Interfaces** | Per-device per-port intent — profile selection + description |
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
   ├─ base.j2
   ├─ vlans.j2
   ├─ interfaces_access.j2
   ├─ interfaces_trunk.j2
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
    "device":    Device,           # hostname, mgmt_ip, model, timezone...
    "vlans":     [VLAN],           # full VLAN list
    "interfaces": [Interface],     # interfaces for this device (filtered per template group)
    "global":    GlobalSettings,   # NTP, SNMP, AAA, banner...
    "hardware":  HardwareProfile,  # port counts and interface naming
    "settings":  {"defaults": {}}  # pack defaults (unused_vlan, native_vlan)
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

| Profile | Type | VLAN Required |
|---------|------|---------------|
| `access-user` | Access | Yes |
| `access-ap` | Access (WAP) | Yes |
| `access-voip` | Access + Voice VLAN | Yes |
| `trunk-uplink` | Trunk | No |
| `unused` | Disabled | No |

---

## Running Tests

```bat
.venv\Scripts\python.exe -m pytest tests/ -v
```

---

## Requirements

- Python 3.10+
- Windows (launcher scripts are `.bat`)
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
