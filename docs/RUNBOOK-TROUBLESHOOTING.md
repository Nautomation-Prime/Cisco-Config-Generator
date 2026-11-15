# RUNBOOK — Troubleshooting

Failure modes, what they mean, and what to do. See [RUNBOOK.md](RUNBOOK.md) for
the normal procedure.

---

## 1. Where to look first

`logs/debug.log` holds a full DEBUG-level trace of the last run, including which
pack was loaded and which template rendered each section. The console shows
INFO and above.

Validation is **all-or-nothing**: when it fails, nothing is written. A failed
run never leaves a partially generated output directory, so you can rerun freely.

---

## 2. Startup and pack errors

### `Pack '<name>' not found. Expected a folder under packs/ or an absolute path.`

`--pack` named something that is not a directory under `packs/` and is not an
absolute path to one. Check spelling, and remember the argument is a directory
name, not a file.

### `Pack at '<path>' is invalid: Missing required file: <name>.yaml`

A pack must contain all of `settings.yaml`, `hardware_catalog.yaml`,
`port_profiles.yaml`, `template_map.yaml`, `features.yaml`, and a `templates/`
directory. Most often seen after copying a pack with a filter that skipped a file.

### `settings.yaml: schema_version is '<x>', but this release supports schema 1.x.`

The pack was written for a different major schema. Either update the pack or use
a matching release of the tool.

Every pack file is checked against its schema on load, and every problem is
listed at once. Each line names the file and the key path, for example
`settings.yaml: defaults.aaa.authorization.commands[0]`.

### `<file>: <key> is not a recognised setting. Did you mean '<key>'?`

Almost always a typo — the suggestion is the closest real key. If the key is
genuinely yours, read only by a custom template, move it under
`defaults.custom` (see
[RUNBOOK-PACK-AUTHORING.md](RUNBOOK-PACK-AUTHORING.md#settings-for-your-own-templates)).

### `<file>: <key> is required.`

A required key is missing — `access_ports` and `interface_prefix` for a switch
model, `uplink_ports` for a module, `template_hint` for a port profile,
`template` for a template_map entry. Often appears alongside a "not recognised"
error for the same key misspelt.

### `settings.yaml: defaults.<key> is '<value>'. Valid values: …`

A setting that only accepts specific values got something else — for example
`ntp_mode`, `password_hash_type`, `spanning_tree_mode`, `storm_control_action`,
`ssh_version`, `ssh_dh_min_size`, or a logging level.

### `<file>: <key>: <Thing> <n> is out of range. Valid range: <a> to <b>.`

A number outside what IOS accepts — VLANs, privilege levels, `ssh_timeout`,
`vty_length`, port counts and so on.

### `<file>: <key> expected a whole number, got '<value>'.`

A number setting holds text. Check for quotes or units (`"15s"`).

### `settings.yaml: defaults.aaa.authentication.login is '…', which has no fallback method.`

The method list ends without `local`, `none`, `enable` or `if-authenticated`. If
the AAA servers become unreachable, nobody can log in. Append a fallback.

The same check applies to `defaults.aaa.authorization.commands_methods`, where a
missing fallback denies *every command* rather than every login.

### `hardware_catalog.yaml: uplink_modules.<name> has <n> uplink port(s) but no interface_prefix`

Set the prefix, e.g. `TenGigabitEthernet1/1/`, or set `uplink_ports: 0`.

### `port_profiles.yaml: profiles.<name>.template_hint is '<x>', which is not defined in template_map.yaml.`

Add the hint to `template_map.yaml`, or correct the spelling.

### `port_profiles.yaml: profiles has no 'unused' profile.`

Every port the workbook leaves out is rendered with the `unused` profile. Without
it those ports would get no configuration at all, so the pack is refused.

### `template_map.yaml: template_map.<hint>.template is '<x>.j2', which does not exist in the pack's templates/ folder.`

The file is missing or the name is misspelt.

### `<file>: not valid YAML - …`

A syntax error — usually indentation, or an unclosed bracket or quote. The
message includes the line and column.

### `jinja2.exceptions.UndefinedError: '…PackDefaults object' has no attribute '<key>'`

A template reads `settings.defaults.<key>` that does not exist. Templates run
with `StrictUndefined`, so this is a hard error rather than a blank line. Either
the key is misspelled in the template, or a custom template reads a setting of
its own — put that under `defaults.custom` and read it as `d.custom.<key>`.

---

## 3. Workbook structure errors

### `Sheet '<name>' is missing required column(s): '<col>'. Found: [...]`

Headers are read from row 1 and normalised — lowercased, spaces to underscores.
A renamed, merged or blank header cell causes this. The `Found:` list shows
exactly what was parsed, which usually makes the culprit obvious.

Required columns: Devices needs hostname, mgmt_ip, mgmt_vlan, default_gateway,
model, uplink_module, site. Interfaces needs device_name, interface_name,
port_profile. Port-Channels needs device_name, port_channel_no.

### `Sheet '<name>', row <n>, column '<column>' …`

Every cell is checked as the workbook loads, and **every** bad cell in every
sheet is listed at once, each with its sheet, row and column. Fix them all,
then rerun. The individual messages are listed in section 4.

`… expected a whole number, got '<value>'` means a VLAN, port-channel number
or timezone offset cell holds text. Watch for Excel storing the value as text
after a paste.

### `Sheet 'Feature Selection', feature '<x>' …`

`is not a recognised feature` — a misspelt feature name. `expected Yes/No (or
true/false), got ''` — the Enabled cell is blank. A blank cell used to mean
"No"; it is now an error, so a section is never switched off by accident.

### `No devices found in the Devices sheet.`

Every row was skipped because the Hostname cell was empty. Rows without a
hostname are ignored by design — check you have not left the header in row 1 and
data starting somewhere unexpected.

---

## 4. Validation errors

These all stop the run with exit code 1.

There are two passes. The first checks each workbook cell and each site-file
entry on its own as it loads; workbook messages start `Sheet '<name>', row <n>,
column '<column>'`, site messages start `Site '<name>' (<file>.yaml): <key>`.
Once everything loads, the second pass checks rows against each other, their
site and the pack; those messages name the device, interface, site or ACL
instead.

Messages common to the workbook and site files:

| Message | Fix |
|---|---|
| `… is required.` | A required cell or key is blank |
| `… expected a whole number, got '<x>'.` | A number holds text |
| `… '<x>' is not a valid IPv4 address.` | Check for typos — a letter O for a zero, a missing octet |
| `… VLAN <n> is out of range. Valid range: 1 to 4094.` | Any VLAN: Mgmt VLAN, Access / Voice / Native VLAN, a site's `vlan_id` |

### Devices

| Message | Fix |
|---|---|
| `column 'Hostname': '<x>' is not a valid IOS hostname` | Letters, digits and hyphens only, starting with a letter or digit, ≤63 characters. Spaces and underscores are the usual cause |
| `column 'Mgmt Subnet': '<x>' is not a valid dotted-decimal subnet mask` | Must be contiguous — `255.255.254.0` is valid, `255.255.0.255` is not |
| `Timezone hours offset <n> is out of range` | -23 to 23. Minutes: 0 to 59 |
| `Duplicate hostname '<name>'` | Each device needs a unique hostname — the output filename is derived from it |
| `management VLAN <n> is not defined in site '<site>'` | Add it to that site's `vlans:` list. An SVI on a VLAN the switch does not have never comes up |
| `model '<x>' not found in hardware catalog` | Use a value from the Model dropdown, or add the model to the pack |
| `uplink module '<x>' not found in hardware catalog` | Use `NONE` if there is no module |
| `has no Site` | Set the Site column to a `sites/<name>.yaml` file's name |
| `site '<x>' was not found under sites/. Available sites: …` | Fix the spelling, or create `sites/<x>.yaml` (copy `sites/site-a.yaml`) |

### Interfaces

| Message | Fix |
|---|---|
| `column 'Allowed VLANs': '<x>' is not a valid VLAN list` | VLAN IDs and ranges separated by commas, e.g. `10,20,30-40`, or `all` / `none`. Spaces are fine — they are removed, because IOS rejects them |
| `contains the backwards range '<a>-<b>'` | Write ranges low to high |
| `column 'Storm Control …': '<x>' must contain two numeric values` | Format is rising then falling, e.g. `1.00 0.70` |
| `Port-channel number <n> is out of range` | 1 to 128 |
| `references unknown device '<name>'` | Device Name must match a Hostname in the Devices sheet exactly |
| `unknown port profile '<x>'` | Use a value from the dropdown |
| `requires an access VLAN, but none is set` | The chosen profile needs Access VLAN filled in |
| `requires a voice VLAN, but none is set` | Typically `access-voip` |
| `requires a native VLAN, but none is set` | Typically `access-ap-trunk` |
| `requires a Port Channel No., but none is set` | Typically `trunk-uplink-portchannel` |
| `access/voice/native VLAN <n> is not defined in its site's VLANs` | Add it to that device's site's `vlans:` list |

### Port-channels

| Message | Fix |
|---|---|
| `has no member interfaces referencing it` | Either add member ports with that Port Channel No. in the Interfaces sheet, or delete the row |
| `Duplicate Port-channel <n> on device '<name>'` | One row per port-channel per device |
| `references unknown device '<name>'` | Device Name must match a Hostname in the Devices sheet exactly. `SW-OFFICE-01` here means the workbook was copied from an older template whose example rows were never read before — delete them |
| `native VLAN <n> is not defined in its site's VLANs` | Add it to that device's site's `vlans:` list |

### Site YAML — the file itself

Each is prefixed `Site '<name>' (<file>.yaml): ` and names the key, e.g.
`vlans[1].vlan_id` for the second VLAN entry. Every problem in the file is
listed at once.

| Message | Fix |
|---|---|
| `could not parse <file>.yaml: …` | YAML syntax — usually indentation, or an unclosed bracket or quote |
| `<key> is not a recognised setting. Did you mean '<y>'?` | A misspelt key. Before this check it was silently ignored and the default applied |
| `aaa_key_type is '<x>'` | `0` plaintext, `6` or `7` already encrypted |
| `aaa_protocol is '<x>'` | `tacacs+` or `radius` |
| `snmp_auth_protocol / snmp_priv_protocol is '<x>'` | Auth: `SHA` or `MD5`. Priv: `AES`, `DES` or `3DES` |
| `<field>[<n>]: '<x>' is not a valid IPv4 address` | Applies to `ntp_servers`, `dns_servers`, `syslog_server`, `aaa_servers` — check the list/comma separation. `snmp_host` is a single address |
| `mgmt_subnet: '<x>' is not a valid dotted-decimal subnet mask` | Must be contiguous |
| `vlans[<n>].vlan_name: '<x>' must be 1 to 32 characters long.` | IOS limits VLAN names to 32 characters |
| `acls[<n>].action is '<x>'` | `permit` or `deny` |
| `acls[<n>].network: '<x>' is not a valid Network/Host` | An IPv4 address, `host <address>`, or `any` |
| `acls[<n>].wildcard: '<x>' is not a valid wildcard mask` | Four octets, e.g. `0.0.0.255` |
| `acls[<n>].wildcard: '<x>' is a subnet mask, but ACLs take a wildcard mask` | Use the inverse: `255.255.255.0` → `0.0.0.255` |
| `acls[<n>]: ACL entry has Wildcard '<x>', but Network/Host '<y>' does not take one` | Remove `wildcard` from `any` and `host` entries |
| `acls[<n>]: ACL entry must include both Action and Network/Host together` | An entry is half-filled |
| `acls[<n>]: ACL entry is empty` | Populate `remark`, or `action` + `network` |

### Site YAML — checks across entries

All prefixed `Site '<name>': ` in the actual error message.

| Message | Fix |
|---|---|
| `Duplicate VLAN ID: <n>` | Remove the duplicate entry in that site's `vlans:` list |
| `'enable_secret' is the default placeholder value` | Replace `changeme` before deploying. **Warning only** (does not block generation) when the pack sets `strict_validation: false` |
| `'local_password' is the default placeholder value` | As above |
| `AAA servers are defined but 'aaa_key' is empty` | The switch would send an empty shared secret |
| `AAA servers are defined but no 'local_username' is set` | Without a local account there is no way in when the AAA servers are unreachable. Set `local_username` and `local_password`. **Warning only** when `strict_validation: false` |
| `sets snmp_host but no SNMPv3 user is defined` | Set `snmp_ro_user` or `snmp_rw_user`, or clear `snmp_host` |
| `contains the delimiter character '<c>'` | The banner or fail message contains the character used to terminate it. Remove it, or change `banner_delimiter` / `aaa_fail_message_delimiter` in the pack |
| `references VTY ACL '<name>' but it is not defined in this site's ACLs` | Add the ACL to that site's `acls:` list, or correct `vty_acl` |
| `ACL '<name>': '<entry>' can never take effect - the earlier entry '<entry>' already matches every address it covers` | An earlier entry with the opposite action catches all of this entry's traffic first — typically a `permit` placed after `deny any`, or a `deny` for one host placed after the `permit` for its subnet. Move the entry above the one named, or remove it. A redundant entry with the *same* action is harmless and not reported |

---

## 5. Output problems

### A port I configured came out as `unused`

The interface name in the workbook does not exactly match the name the generator
derives from the model and uplink module. `GigabitEthernet1/0/5` and `Gi1/0/5`
are not the same string — the generator does not expand abbreviations. Check
`interface_prefix` for the model in `hardware_catalog.yaml`.

### Ports beyond the switch's real port count appear

`access_ports` in the hardware catalogue is wrong for that model, or the wrong
model is selected in the Devices sheet.

### An interface I listed does not appear at all

If the interface name is outside the derived inventory it is still rendered, but
grouped at the end. If it is missing entirely, its `template_hint` did not
resolve — check `logs/debug.log` for `Unknown template hint '<x>', skipping`.

### The config is missing a whole section

Check Feature Selection. Also note that some sections need data: NTP renders
only when `ntp_servers` is populated, SNMP only when an SNMPv3 user is defined,
syslog only when `syslog_server` is set.

### `Hostname '<x>' resolved to a path outside the output directory.`

A hostname containing path separators. Fix the hostname — this is the path
traversal guard in the writer.

---

## 6. Deployment problems

### SSH does not work after applying the config

Almost always the missing key pair. `crypto key generate rsa` is not in the
config file because IOS rejects it in configuration mode. From privileged EXEC:

```
crypto key generate rsa label SEC2048 general-keys modulus 2048
```

Then `show ip ssh` should report SSH Enabled with version 2. If it still fails,
check `ip ssh rsa keypair-name` matches the label you generated.

### `% Invalid input detected` while pasting

Note the line. Common causes:

- **An IOS-XE command on a 2960-X.** Confirm the Model in the Devices sheet
  matches the actual hardware — platform gating keys off the model name.
- **`crypto key generate rsa`** — only if `emit_crypto_key_command` was set
  `true` in the pack. It cannot work in config mode; set it back to `false`.
- **A command your IOS train does not have.** `ip ssh server algorithm mac
  hmac-sha2-…` needs a reasonably recent 15.2(7)E or IOS-XE. Set
  `ssh_mac_algorithms: ""` to keep the platform default set.

### Locked out over SSH after applying

The VTY ACL does not permit your source. Get on the console and either correct
the ACL or `no access-class <name> in vrf-also` on the vty lines while you fix
the workbook.

If you armed `reload in 15` as the runbook says, waiting is the safe option.

### Locked out because AAA servers are unreachable

Log in with the local account — this is why validation refuses an AAA
configuration with no `local_username`. If command authorization is also denying
you, get on the console; `authorization_console: false` in the pack exempts the
console for future builds.

### The management SVI stays down

`show vlan brief` — the VLAN must exist and have at least one active access port
or an allowed trunk. The generated config defines VLANs before the SVI, so if
the VLAN is present, check that an uplink trunk allows it.

### Trunk comes up but some VLANs do not pass

Compare `switchport trunk allowed vlan` at both ends, and check the native VLAN
matches. A mismatch logs a CDP native VLAN error.

### Port-channel members do not bundle

`show etherchannel summary`. Members must agree on speed, duplex, mode, native
VLAN and allowed VLAN list. The generator renders the Port-channel interface
before its members so they inherit correctly, but a hand-edit either side can
break that.

---

## 7. Tool problems

### `pytest` collects hundreds of unrelated tests

Run it from the repository root so it picks up `[tool.pytest.ini_options]` in
`pyproject.toml`, which limits collection to `tests/`.

### `ModuleNotFoundError` on startup

Reinstall the dependencies: `pip install -e .` on Linux, or delete
`python_runtime\` and rerun `setup.bat` on Windows.

### Generated output changed unexpectedly after an upgrade

Diff the pack against the shipped `packs/default`. New settings take their
built-in default, which may differ from the previous hard-coded behaviour. The
settings reference in
[RUNBOOK-PACK-AUTHORING.md](RUNBOOK-PACK-AUTHORING.md#3-settings-reference)
lists every default.

Always regenerate and diff before deploying after a tool upgrade.
