# RUNBOOK — Generating and deploying switch configurations

Operational procedure for the Cisco Config Generator: from a blank workbook to a
configured switch.

Related documents:

- [RUNBOOK-PACK-AUTHORING.md](RUNBOOK-PACK-AUTHORING.md) — customising a pack, full settings reference
- [RUNBOOK-TROUBLESHOOTING.md](RUNBOOK-TROUBLESHOOTING.md) — every error message and what to do about it

---

## 1. What this tool does

It reads an Excel workbook describing your intent (devices and ports) plus one
YAML file per site (VLANs, ACLs, NTP/DNS/SNMP/AAA, banner) and writes one
complete `.cfg` file per switch. It does **not** talk to any device — it only
writes files. Deployment is a separate, manual step covered in section 6.

Three inputs decide the output:

| Input | What it holds | Who changes it |
|---|---|---|
| The workbook (`.xlsx`) | Per-device facts — hostnames, IPs, ports, and which site each device belongs to | Per deployment, per change |
| The site (`sites/<name>.yaml`) | This site's shared facts — VLANs, ACLs, NTP/DNS/SNMP servers, AAA, banner, credentials | Per site, rarely |
| The pack (`packs/<name>/`) | The house standard — how configs are shaped | Once per customer, rarely |

A device's **Site** column picks which `sites/<name>.yaml` file supplies its
shared settings. A workbook can mix devices from several sites — each renders
against its own site file — or every device can point at the same site.

---

## 2. Install

### Windows (portable — no admin rights, no system Python)

```
run.bat
```

On first run this calls `setup.bat`, which downloads an embedded Python 3.12
runtime into `python_runtime\` and installs the dependencies. It needs internet
access once. Subsequent runs start immediately.

To upgrade Python later: edit `PY_VER` / `PY_SHORT` in `setup.bat`, delete
`python_runtime\`, and run `setup.bat` again.

### Linux (production)

```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -e .
```

That installs the `cisco-config-generator` entry point. `python -m
cisco_config_generator` works identically.

### Verify the install

```bash
cisco-config-generator --version
```

---

## 3. Prepare the site and the workbook

### 3.1 The site YAML

Every device belongs to a site, and every site is one file:
`sites/<name>.yaml`. Copy `sites/site-a.yaml` as a starting point — it is a
complete, fully-commented worked example (fictional addresses and
credentials, safe to read as a reference).

A site file holds everything that used to be workbook-wide:

| Section | Fields |
|---|---|
| Identity / device fallbacks | `site_name` (display only), `timezone`, `mgmt_subnet` — used when a device leaves its own Timezone/Mgmt Subnet cell blank |
| NTP / DNS / syslog | `ntp_servers`, `dns_servers`, `syslog_server`, `domain_name`, `summer_time_config` — each a YAML list or a comma-separated string |
| AAA | `aaa_protocol` (`tacacs+` or `radius`), `aaa_servers`, `aaa_key`, `aaa_key_type` (`0` plaintext, `6`/`7` already encrypted), `aaa_group_name`, `aaa_fail_message` |
| SNMPv3 | `snmp_auth_protocol`, `snmp_priv_protocol`, `snmp_ro_*` / `snmp_rw_*` user+group+passwords, `snmp_host`, `snmp_location`, `snmp_contact` |
| ACL names | `vty_acl`, `snmp_ro_acl`, `snmp_rw_acl` — must match `acl_name` values in this same site's `acls:` list |
| Credentials | `enable_secret`, `local_username`, `local_password` — plaintext and the switch hashes them itself, or an already-hashed value (`$9$…`, `$8$…`, `$1$…`) passed through untouched. See [RUNBOOK-PACK-AUTHORING.md](RUNBOOK-PACK-AUTHORING.md#credentials) |
| `vlans:` | A list of `{vlan_id, vlan_name, description}`. Every VLAN referenced anywhere for a device at this site — access, voice, native, management — must be defined here |
| `acls:` | A list of `{acl_name, remark, action, network, wildcard}`. One entry per ACE; a remark-only row is allowed before a permit/deny block |

The site file is checked as it loads, and every problem is listed at once with
the key it belongs to — `vlans[1].vlan_id: VLAN 5000 is out of range`. A
misspelt key is reported with the closest real one (`ntp_server` → "Did you
mean 'ntp_servers'?") rather than silently ignored. `sites/site-a.yaml` starts
with a comment pointing at `schemas/site.schema.json`; keep it in your copies
and VS Code (Red Hat YAML extension) offers autocomplete and inline errors as
you type.

ACL entries: `network` is an IPv4 address, `host <address>`, or `any`.
`wildcard` is a wildcard mask — `0.0.0.255` for a /24, not `255.255.255.0` —
and stays blank for hosts and `any`. Entries are checked in order: an entry
that can never take effect, because an earlier entry with the opposite action
already matches all its traffic (a `permit` after `deny any`, say), is
reported as an error.

Run `python scripts/generate_workbook.py` after adding a new site file, and
**before** copying the template for it — it regenerates the workbook
template's **Site Reference** sheet (a read-only lookup of each site's VLANs
and ACL names) and the Devices sheet's Site dropdown. Both are a one-time
snapshot baked into `workbook_template.xlsx` at that moment, not a live
lookup, so a workbook already copied from an older template won't offer the
new site — and Excel's dropdown validation stops you typing it in directly.
Editing values *within* an existing site file needs no regeneration; only
adding a site the Devices sheet doesn't know about yet does.

### 3.2 The workbook

Start from `assets/workbook_template.xlsx`. **Copy it** — don't edit the
template in place, it is regenerated by `scripts/generate_workbook.py`.

`assets/sample_intent.xlsx` is a fully worked two-switch example, using
`sites/site-a.yaml`. Open it alongside the template when filling in a
deployment for the first time.

Column headers are matched case-insensitively with spaces converted to
underscores, so `Mgmt IP` and `mgmt_ip` both work.

### Devices — one row per switch

| Column | Required | Notes |
|---|---|---|
| Hostname | yes | Must be a valid IOS hostname: letters, digits, hyphens, ≤63 chars. Becomes the output filename |
| Mgmt IP | yes | IPv4 address of the management SVI |
| Mgmt VLAN | yes | **Must also exist in this device's site's `vlans:` list** |
| Default Gateway | yes | IPv4 |
| Model | yes | Must exist in the pack's `hardware_catalog.yaml` |
| Uplink Module | yes | Must exist in the catalogue. Use `NONE` for no uplink module |
| Site | yes | Name of a `sites/<name>.yaml` file (matched case-insensitively). Supplies this device's VLANs, ACLs, NTP/DNS/SNMP/AAA and banner |
| Timezone / Timezone Hours / Timezone Minutes | no | Defaults to the site's `timezone` (then the pack's `defaults.timezone`) and `0 0` |
| Mgmt Subnet | no | Defaults to the site's `mgmt_subnet` (then the pack's `defaults.mgmt_subnet`). Must be a contiguous mask |

### Site Reference (read-only)

Generated from whatever `sites/*.yaml` files existed when the workbook was
last built — one row per VLAN per site, plus that site's ACL names. Not read
back by the generator; it exists so you know what to type into Devices and
Interfaces without opening the YAML files. Re-run
`scripts/generate_workbook.py` after changing a site file to refresh it.

### Interfaces

**Only add rows for ports that need explicit configuration.** The generator
derives the full port inventory from the model and uplink module, and any port
you do not list is configured as unused: `default interface`, access VLAN
`defaults.unused_vlan`, `shutdown`.

Port Profile drives which template renders the port. The full list is the
dropdown in the sheet, defined by `packs/<name>/port_profiles.yaml`; the common
ones are `access-user`, `access-voip`,
`access-printer`, `access-ap-trunk`, `trunk-uplink`,
`trunk-uplink-portchannel`, `access-server`, `unused`.

Storm Control Broadcast / Multicast override the pack defaults per port. Format
is two numbers: rising then falling, e.g. `1.00 0.70`.

Allowed VLANs takes IDs and ranges separated by commas (`10,20,30-40`), or
`all` / `none`; blank means `all`. Spaces are removed, because IOS rejects a
list such as `10, 20`.

### Port-Channels

Optional. Every port-channel is derived automatically from the Port Channel No.
column in the Interfaces sheet, taking its settings from the first member. Add
a row here only when you want a Port-channel interface to differ from its
members: set Device Name and Port Channel No., then fill in just the cells to
change — blank cells keep the members' values. Port-channels without a row
stay as derived.

> **Workbooks copied from an older template.** Before this release the sheet
> was never read, and the template shipped two example rows for
> `SW-OFFICE-01`. If your workbook still has them, they now apply: either the
> run stops with `references unknown device 'SW-OFFICE-01'`, or — if you kept
> that hostname — they override your Po1 and Po2. Delete any rows you did not
> put there deliberately.

### Feature Selection

Yes/No per section. `vlans`, `interfaces`, `port_channels` and `acls` each
independently gate that section of the file. `base_config` turns the whole
base config on or off; `aaa`, `snmp`, `ntp`, `dhcp_snooping`, `spanning_tree`
and `banner` are sub-sections within it — they have no effect if
`base_config` is off. A blank Enabled cell is an error, not a silent No.

Setting `aaa` to **No** omits `aaa new-model` entirely and puts `login local` on
the console and both vty ranges instead — authentication then relies solely on
`local_username` / `local_password`.

---

## 4. Generate

Interactive:

```bash
cisco-config-generator --workbook /path/to/site-a.xlsx
```

Headless (scripted, CI, or over SSH):

```bash
cisco-config-generator --no-tui --workbook /path/to/site-a.xlsx --output /path/to/out
```

| Option | Default | Purpose |
|---|---|---|
| `--pack` / `-p` | `default` | Pack name under `packs/`, or an absolute path |
| `--workbook` / `-w` | — | Path to the `.xlsx`. Required with `--no-tui` |
| `--output` / `-o` | `output` | Directory for the generated `.cfg` files |
| `--sites-dir` | `sites/` next to `packs/` | Directory containing per-site YAML files |
| `--no-tui` | off | Run headless |
| `--version` | — | Print version and exit |

**Exit codes:** `0` success, `1` validation failure or error. Nothing is written
when validation fails — it is all-or-nothing, so a failed run never leaves a
half-generated directory.

Output lands at `<output>/<hostname>.cfg`. A debug log is written to
`logs/debug.log`.

---

## 5. Review before deploying

Generated files are not reviewed by anyone but you. Check these every time:

1. **Management reachability.** `interface Vlan<n>` has the right address and
   mask, and `ip default-gateway` is correct. Getting this wrong means a site
   visit.
2. **The VTY ACL.** `access-class <name> in vrf-also` on all three line blocks —
   and confirm your own management network is permitted by that ACL earlier in
   the file. This is the most common way to lock yourself out.
3. **AAA fallback.** If `aaa_servers` is set, confirm a `username …` line exists
   and that the method lists end in `local`. Validation enforces both, but read
   it anyway.
4. **Uplink allowed VLAN lists.** A missing VLAN on a trunk is a silent outage
   for that VLAN.
5. **Unused ports.** Confirm nothing live is in the unused block — those ports
   get `default interface` followed by `shutdown`.
6. **Native VLAN consistency** with the far end of every trunk.

**The generated file contains plaintext secrets** — enable secret, local
password, AAA key, SNMP auth and priv passwords. Treat the output directory as
sensitive: restrict permissions, and delete the files once deployed. The same
applies to every `sites/<name>.yaml` file, since that is where those secrets
now live — restrict its permissions and keep it out of any public repository.

---

## 6. Deploy

### 6.1 Get console access first

The config changes VTY access, AAA and SSH. Do not deploy over SSH without a
console or an out-of-band path you have already tested.

### 6.2 Arm the safety net

On the switch, before pasting anything:

```
reload in 15
```

If you lose access mid-change the switch reboots into the last saved config in
15 minutes. **Do not `write memory` until you have verified access.**

### 6.3 Paste the configuration

```
configure terminal
```

Paste the whole `.cfg` file. It is ordered so it can be applied top to bottom
without forward references: ACLs, then VLANs, then base config, then
port-channels, then physical interfaces.

Expect the session to drop briefly if you are connected through a port the
config touches.

### 6.4 Generate the SSH host key

**This step is mandatory and is not in the configuration file.** `crypto key
generate rsa` is a privileged EXEC command — IOS rejects it in configuration
mode — so the generator emits it as a commented block in the file header
instead.

From privileged EXEC, after the config is applied (hostname and `ip domain name`
must already be set, which the pasted config does):

```
end
crypto key generate rsa label SEC2048 general-keys modulus 2048
```

Use the label and modulus from the header comment of the file you just applied —
they follow the pack's `ssh_key_label` and `ssh_key_modulus`. SSH will not start
until this key exists.

### 6.5 Verify

```
show ip interface brief | include Vlan
show ip ssh
show running-config | include ^username|^aaa
show interfaces status
show spanning-tree summary
show logging | include %
```

Then, from your management workstation, **open a second SSH session before
touching anything else.** Confirm you can log in and reach enable.

If AAA is configured, verify both paths: a TACACS/RADIUS account *and* the local
account (test the local fallback by an account the AAA server does not know).

### 6.6 Commit

Only once a second session is confirmed working:

```
reload cancel
write memory
```

`reload cancel` first, then save. Reversing the order defeats the safety net.

---

## 7. Rollback

**Before `write memory`:** `reload` (or let the armed `reload in` fire). The
switch returns to the last saved configuration.

**After `write memory`:** you need a saved copy of the previous config. Take one
before every change:

```
copy running-config flash:pre-change-YYYYMMDD.cfg
```

To roll back:

```
configure replace flash:pre-change-YYYYMMDD.cfg
```

`configure replace` computes and applies the difference — it is far safer than
pasting an old file over a running config, which only adds commands and never
removes them.

---

## 8. Routine operations

**Adding a switch to an existing site:** add a row to Devices (Site = the
existing `sites/<name>.yaml`), add its ports to Interfaces, regenerate.
Existing devices' files are rewritten identically — regeneration is
deterministic for unchanged input.

**Adding a new site:** copy `sites/site-a.yaml` to `sites/<new-site>.yaml`,
fill in its VLANs/ACLs/NTP/DNS/SNMP/AAA/banner/credentials, run
`python scripts/generate_workbook.py` so the Devices sheet's Site dropdown and
the Site Reference sheet pick it up, then add device rows using it. **Do this
before** copying `workbook_template.xlsx` for the new deployment — the Site
dropdown is a snapshot of `sites/` taken at generation time, baked into that
one `.xlsx` file, not a live lookup. A workbook copied earlier keeps the old
list, and Excel's dropdown validation blocks typing a site name that isn't on
it (a "stop" error, not a warning) — so an in-progress workbook can't pick up
a new site without being regenerated from a fresh template copy.

**Changing a site's shared settings:** edit `sites/<name>.yaml` directly and
regenerate — every device at that site picks up the change. No workbook edit
needed.

**Changing the house standard:** edit `packs/<name>/settings.yaml`, regenerate
everything, and diff the output against the previous run before deploying. See
[RUNBOOK-PACK-AUTHORING.md](RUNBOOK-PACK-AUTHORING.md).

**Adding a switch model or uplink module:** edit
`packs/<name>/hardware_catalog.yaml`, then regenerate the workbook template so
the Model dropdown includes it:

```bash
python scripts/generate_workbook.py
```

**Regenerating the workbook template** after any change to `hardware_catalog.yaml`,
`port_profiles.yaml` or `features.yaml` — those three files drive its dropdowns
and its Feature Selection sheet.

---

## 9. Verify the tool itself

```bash
pytest
```

Run this after changing a pack or upgrading the tool. It renders real configs
through the full pipeline and asserts on the IOS output, so it catches template
breakage as well as Python errors.
