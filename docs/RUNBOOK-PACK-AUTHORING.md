# RUNBOOK — Pack authoring

A pack is the house standard: how configurations are shaped, as opposed to what
this particular deployment's or site's values are. The workbook and the site
YAML hold intent; the pack holds policy.

See [RUNBOOK.md](RUNBOOK.md) for the operational procedure.

---

## 1. Creating a pack

```bash
cp -r packs/default packs/acme
```

Then select it with `--pack acme`, or by absolute path with `--pack
/etc/ccg/packs/acme`.

```
packs/acme/
├─ settings.yaml          # policy defaults — the knobs below
├─ hardware_catalog.yaml  # switch models and uplink modules
├─ port_profiles.yaml     # port profile definitions
├─ template_map.yaml      # profile/feature → template, and render order
├─ features.yaml          # the Feature Selection list
└─ templates/*.j2
```

All five YAML files and the `templates/` directory are required; the loader
refuses a pack that is missing any of them.

**Prefer changing `settings.yaml` over editing a template.** Every opinionated
choice in the shipped templates is already a setting.

---

## 2. How settings resolve

Every pack file is validated against a schema defined in
`cisco_config_generator/pack_schema.py` (`SettingsFile`, `HardwareCatalogFile`,
`PortProfilesFile`, `TemplateMapFile`, `FeaturesFile`). Keys you omit from
`defaults:` fall back to the `PackDefaults` defaults, and nested blocks fall back
key by key, so overriding `aaa.authorization.commands` keeps every sibling under
`aaa`. That is why a pack written against an earlier schema keeps rendering.

Templates read them as `settings.defaults.<key>` — by convention bound to `d` at
the top of each template.

`schema_version` is checked on load: this release supports schema `1.x`.

The loader **refuses to load** a pack with a problem, and reports every problem
at once, each naming the file and key:

- **A key it does not recognise** — usually a typo. The message suggests the
  closest real key: `settings.yaml: defaults.ssh_timout is not a recognised
  setting. Did you mean 'ssh_timeout'?` Before this check, a misspelt key was
  silently ignored and the default applied instead.
- **A value of the wrong type or outside its range** — VLANs 1–4094, privilege
  levels 0–15, `ssh_timeout` 1–120, choice settings such as `ntp_mode` or
  `spanning_tree_mode` limited to the values IOS accepts.
- **Files that disagree** — a port profile whose `template_hint` is not in
  `template_map.yaml`, a `template_map` entry whose `.j2` file does not exist,
  a missing `acls` / `vlans` / `base_config` / `port_channels` section, or no
  `unused` profile.

### Settings for your own templates

A custom template that needs a knob of its own reads it from `defaults.custom`,
which is passed through unchecked:

```yaml
defaults:
  custom:
    site_code: LON1
```

```jinja
! site code {{ d.custom.site_code }}
```

Keys anywhere else under `defaults:` must be settings the core knows about.

### Editor support

`schemas/` holds a JSON schema for each pack file. The shipped YAML files start
with a comment that points at theirs:

```yaml
# yaml-language-server: $schema=../../schemas/settings.schema.json
```

With the Red Hat YAML extension in VS Code, that gives autocomplete for every
key, the allowed values for choice settings, and inline errors as you type. The
relative path works for any pack under `packs/`; for a pack stored elsewhere,
point the comment at the schema's absolute path.

After changing `pack_schema.py`, regenerate the schemas — the test suite fails
if they drift:

```bash
python scripts/export_pack_schemas.py
```

---

## 3. Settings reference

### VLANs

| Key | Default | Effect |
|---|---|---|
| `unused_vlan` | `999` | Access VLAN for ports not listed in the workbook |
| `native_vlan` | `1` | Trunk native VLAN when the workbook leaves it blank |
| `shutdown_vlan1` | `true` | Emits the `interface Vlan1 … shutdown` block |

### Device fallbacks

The last tier of a three-tier fallback: a device's own Timezone/Mgmt Subnet
cell, then its site's `timezone`/`mgmt_subnet` (in `sites/<name>.yaml`), then
these pack defaults.

| Key | Default | Effect |
|---|---|---|
| `timezone` | `GMT` | Used when both the Devices sheet cell and the site leave Timezone blank |
| `mgmt_subnet` | `255.255.255.0` | Used when both the Devices sheet cell and the site leave Mgmt Subnet blank |

### Global services

| Key | Default | Effect |
|---|---|---|
| `service_internal` | `false` | Undocumented Cisco-internal debug commands. Unsupported in production — leave off unless TAC asked |
| `service_call_home` | `false` | `false` emits `no service call-home` |
| `service_compress_config` | `true` | |
| `service_pad` | `false` | `false` emits `no service pad` |

### DNS

| Key | Default | Effect |
|---|---|---|
| `domain_lookup` | `false` | `false` emits `no ip domain lookup`, so a mistyped command is not resolved as a hostname. `true` emits `ip domain lookup` plus a source interface, and only makes sense with `dns_servers` set |

### Logging

| Key | Default | Effect |
|---|---|---|
| `logging_buffer_size` | `128000` | |
| `logging_console_level` | `""` | Empty emits `no logging console` — console logging can wedge the console on a busy switch. Set a level name (e.g. `informational`) to log to console |
| `logging_monitor_level` | `informational` | |
| `logging_trap_level` | `informational` | |
| `logging_source_interface` | `true` | Source syslog from the management SVI |

### Errdisable

| Key | Default | Effect |
|---|---|---|
| `errdisable_recovery_causes` | `[bpduguard, storm-control, udld, gbic-invalid, link-flap, psecure-violation]` | One `errdisable recovery cause` line each |
| `errdisable_recovery_interval` | `1800` | Seconds |

Note: the `storm-control` cause only ever fires when `storm_control_action` is
`shutdown`. With the default `trap`, storm control filters traffic rather than
err-disabling the port.

### SSH and crypto

| Key | Default | Effect |
|---|---|---|
| `ssh_key_label` | `SEC2048` | Key pair label, referenced by `ip ssh rsa keypair-name` |
| `ssh_key_modulus` | `2048` | |
| `ssh_version` | `2` | |
| `ssh_dh_min_size` | `2048` | |
| `ssh_timeout` | `15` | |
| `emit_crypto_key_command` | `false` | `crypto key generate rsa` is an EXEC command and is rejected in config mode. Left `false`, it is emitted as a documented post-apply step in the file header. Set `true` to emit it as a live line anyway |
| `ssh_mac_algorithms` | `hmac-sha2-512 hmac-sha2-256` | Empty keeps the platform default set |
| `ssh_encryption_algorithms` | `aes256-ctr aes192-ctr aes128-ctr` | Empty keeps the platform default set |
| `ssh_kex_algorithms` | `""` | |

### Credentials

| Key | Default | Effect |
|---|---|---|
| `password_hash_type` | `scrypt` | `scrypt` (type 9), `sha256` (type 8) or `md5` (type 5) |
| `local_user_privilege` | `15` | Privilege level on the `username` line |

`password_hash_type` applies **only when the site YAML holds a plaintext value**.
The generator then emits `enable algorithm-type scrypt secret <plaintext>` and
lets the switch hash it. Writing `enable secret 9 <plaintext>` would be rejected
by IOS, because type 9 expects a scrypt hash rather than a password.

A site value that is already hashed is detected by its prefix and passed
through with the matching type number:

| Site value | Rendered as |
|---|---|
| `MyPassw0rd` | `algorithm-type scrypt secret MyPassw0rd` |
| `$9$…` | `secret 9 $9$…` |
| `$8$…` | `secret 8 $8$…` |
| `$1$…` | `secret 5 $1$…` |

### NTP

| Key | Default | Effect |
|---|---|---|
| `ntp_mode` | `server` | `server` is client mode — correct for an access switch polling upstream. `peer` is symmetric active, which offers time back to the far end, and suits only mutually redundant time servers |
| `ntp_source_interface` | `true` | Emits `ntp source Vlan<mgmt>` |

### SNMP

| Key | Default | Effect |
|---|---|---|
| `snmp_source_interface` | `true` | Emits `snmp-server source-interface traps Vlan<mgmt>` |
| `snmp_priv_aes_key_length` | `256` | Appended only when the site's `snmp_priv_protocol` is AES |

### Spanning tree

| Key | Default | Effect |
|---|---|---|
| `spanning_tree_mode` | `rapid-pvst` | |
| `spanning_tree_portfast_bpduguard_default` | `true` | Global `spanning-tree portfast bpduguard default` |

### QoS

| Key | Default | Effect |
|---|---|---|
| `qos_enabled` | `false` | See below |
| `qos_trust_uplinks` | `true` | Only relevant when `qos_enabled` is on |

Catalyst 9000 (IOS-XE) trusts DSCP by default and needs no global command;
profiles with `qos_trust_dscp` get `auto qos trust dscp` regardless of this
setting.

Catalyst 2960-X (IOS 15.x) needs global `mls qos` before any interface `mls qos
trust` does anything — so with `qos_enabled: false` neither is emitted, and DSCP
passes through untouched. Turning it on emits the global command, trust on the
profiles that ask for it, and (via `qos_trust_uplinks`) trust on uplinks so
upstream marking is not remarked to 0.

### Storm control

| Key | Default | Effect |
|---|---|---|
| `storm_control_broadcast` | `1.00 0.70` | Rising and falling thresholds |
| `storm_control_multicast` | `1.00 0.70` | |
| `storm_control_broadcast_uplink` | `0.10 0.07` | Applied to interfaces matching `uplink_interface_prefixes` |
| `storm_control_multicast_uplink` | `0.10 0.07` | |
| `uplink_interface_prefixes` | `[TenGigabit, TwentyFiveGig, FortyGigabit, HundredGig]` | Interface-name prefixes treated as uplink speed |
| `storm_control_action` | `trap` | `trap`, `shutdown`, or `""` for filter only |

Workbook values on a port always win over these.

### Banners

| Key | Default | Effect |
|---|---|---|
| `banner_delimiter` | `^` | |
| `aaa_fail_message_delimiter` | `#` | |

The delimiter must not appear inside the message text or the switch ends the
banner early and parses the remainder as commands. Validation rejects that.

### Lines

| Key | Default |
|---|---|
| `exec_timeout` | `15 0` |
| `vty_length` | `20` |
| `console_stopbits` | `1` |
| `escape_character` | `3` |

### DHCP snooping

| Key | Default | Effect |
|---|---|---|
| `dhcp_snooping_vlans` | `1-4094` | |
| `dhcp_snooping_information_option` | `false` | `false` emits `no ip dhcp snooping information option` |

---

## 4. AAA policy

The site YAML says *who* — `aaa_protocol`, `aaa_servers`, `aaa_key`,
`aaa_key_type`, `aaa_group_name`, `aaa_fail_message`. The pack says *how*.

Each method list is a string emitted verbatim after the command it belongs to,
with `{group}` substituted for the site's group name:

```yaml
aaa:
  source_interface: true
  authorization_console: true
  session_id: common
  radius_auth_port: 1812
  radius_acct_port: 1813
  prompts:
    username: "Local-Login-Name:"
    password: "Local-Password:"
  authentication:
    login:  "group {group} local"
    enable: "group {group} enable"
  authorization:
    exec: "group {group} local"
    commands: [15]
    commands_methods: "group {group} local"
  accounting:
    exec: "start-stop group {group}"
    commands: [15]
    commands_methods: "start-stop group {group}"
  local_only:
    login: "local"
    exec: "local if-authenticated"
```

Set a method string to `""` to omit that line. Set a `commands` list to `[]` to
omit command authorization or accounting entirely.

Common variations:

| Goal | Change |
|---|---|
| Local-first ordering | `authentication.login: "local group {group}"` |
| No command authorization | `authorization.commands: []` |
| Also authorize level 1 | `authorization.commands: [1, 15]` |
| No accounting at all | `accounting: {exec: "", commands: []}` |
| Console exempt from authorization | `authorization_console: false` |
| RADIUS instead of TACACS+ | Set `aaa_protocol: radius` in the **site YAML** |

`local_only` is used when AAA is enabled but the site defines no servers.

### Guard rails

The pack **fails to load** if `authentication.login` or
`authorization.commands_methods` has no fallback method (`local`,
`if-authenticated`, `none`, `enable`). Without one, unreachable AAA servers deny
every login or every command.

Privilege levels outside 0–15 are rejected.

---

## 5. Render order

`template_map.yaml` sets the order each section is emitted, so a generated file
can be pasted top to bottom without forward references:

| Order | Section | Why here |
|---|---|---|
| 5 | `acls` | Before the `access-class` and `snmp-server group … access` lines that apply them |
| 10 | `vlans` | Before the base config creates the management SVI |
| 15 | `base_config` | |
| 25 | `port_channels` | Before the members that join with `channel-group` |
| 30 | `interfaces_*` | Physical ports |

Sections sharing an order render in grouping order, which is fine — they are
independent.

---

## 6. Hardware catalogue

`hardware_catalog.yaml` has two blocks. `switch_models` drives the access-port
inventory; `uplink_modules` drives the uplink inventory. Between them they
determine which ports the generator will emit as unused when the workbook does
not list them.

```yaml
switch_models:
  C9200-48P:
    description: "Catalyst 9200 48-port PoE+"
    access_ports: 48
    interface_prefix: "GigabitEthernet1/0/"
    access_port_start: 1

uplink_modules:
  NM-4X:
    description: "4-port 10G SFP+ uplink module"
    uplink_ports: 4
    interface_prefix: "TenGigabitEthernet1/1/"
    uplink_port_start: 1
```

Keep a `NONE` entry with `uplink_ports: 0` for switches with no module.

After editing, regenerate the workbook template so the dropdowns match:

```bash
python scripts/generate_workbook.py
```

---

## 7. Port profiles

`port_profiles.yaml` maps a profile name to a template and its validation rules.

```yaml
  access-voip:
    description: "Client/phone port (data + voice VLAN, QoS DSCP trust)"
    requires_vlan: true
    requires_voice_vlan: true
    qos_trust_dscp: true
    template_hint: interfaces_access
```

| Key | Effect |
|---|---|
| `requires_vlan` | Validation error if Access VLAN is blank |
| `requires_voice_vlan` | Validation error if Voice VLAN is blank |
| `requires_native_vlan` | Validation error if Native VLAN is blank |
| `requires_port_channel` | Validation error if Port Channel No. is blank |
| `qos_trust_dscp` | Emits the platform's QoS trust command on the port |
| `template_hint` | Key into `template_map.yaml` |

A new profile needs an entry here, an entry in `template_map.yaml`, and a
template — then regenerate the workbook template so the dropdown includes it.
The loader checks the first two line up.

The `unused` profile is required: every port the workbook does not list is
rendered with it.

---

## 8. Platform gating

These are emitted only for models whose name contains `C92` or `C93`, because
IOS classic (2960-X) rejects them:

`no platform punt-keepalive disable-kernel-core`, `vrf definition Mgmt-vrf`,
`no device-tracking logging theft`, `boot system flash:packages.conf`,
`license boot level …`, `redundancy / mode sso`.

If you add a Catalyst 9000 model whose name does not contain `C92`/`C93`, adjust
the `is_iosxe` expression at the top of the affected templates.

---

## 9. Editing templates

Templates receive:

```python
{
  "device":     Device,           # hostname, mgmt_ip, model, timezone, site…
  "vlans":      [VLAN],           # this device's site's VLANs (sites/<name>.yaml)
  "interfaces": [Interface],      # this device's ports, filtered per template group
  "port_channels": [PortChannel],
  "global":     GlobalSettings,   # this device's site's NTP/DNS/SNMP/AAA/banner/credentials
  "hardware":   HardwareProfile,
  "acls":       [ACLEntry],       # this device's site's ACLs
  "features":   FeatureSelection,
  "settings":   {"defaults": PackDefaults} # settings.defaults, with fallbacks filled in
}
```

`vlans`, `global` and `acls` all come from the site YAML the device's Site
column points at (see [RUNBOOK.md](RUNBOOK.md#31-the-site-yaml)) — each device
in a multi-site workbook renders against its own site's values.

Filters available:

| Filter | Purpose |
|---|---|
| `cisco_secret(hash_type)` | Renders the secret portion of `enable` / `username` |
| `is_hashed_secret` | True when a value is already an IOS hash |
| `starts_with_any(prefixes)` | True when a string starts with any listed prefix |

Jinja runs with `StrictUndefined`, `trim_blocks` and `lstrip_blocks`. Strict
undefined means a typo in a settings key is a hard render error rather than a
silently blank line — which is why every key a template reads must be a field
of `PackDefaults`, or live under `defaults.custom`.

After editing any template, run `pytest` — the suite renders real configs and
asserts on the IOS output.
