"""Schema for the YAML files in a pack.

One model per file. Every model rejects keys it does not know, so a misspelt
setting is reported instead of silently falling back to the built-in default.
The field defaults below are the fallback policy for anything a pack's
settings.yaml leaves out, so packs written against an older schema keep
rendering.

scripts/export_pack_schemas.py turns these models into the JSON schemas under
schemas/, which give pack authors autocomplete and inline errors in their editor.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

from cisco_config_generator.field_types import (
    PrivilegeLevel,
    StormControlLevel,
    SubnetMask,
    TcpUdpPort,
    VlanId,
    VlanList,
    ranged_int,
)


class _PackModel(BaseModel):
    model_config = ConfigDict(extra="forbid", coerce_numbers_to_str=True)


SyslogLevelName = Literal[
    "emergencies", "alerts", "critical", "errors",
    "warnings", "notifications", "informational", "debugging",
]
SyslogLevel = Union[SyslogLevelName, ranged_int(0, 7, "Syslog level")]


def _single_character(value: str) -> str:
    if len(value) != 1 or value.isspace():
        raise ValueError(f"'{value}' must be a single, non-space character.")
    return value


Delimiter = Annotated[str, AfterValidator(_single_character)]

_ExecTimeout = Annotated[str, Field(pattern=r"^\d+(\s+\d+)?$")]

# Methods reachable without the AAA servers. A login or command-authorization
# list must end in one of these, or unreachable servers lock everyone out.
_FALLBACK_METHODS = {"local", "none", "enable", "if-authenticated"}


def has_fallback_method(methods: str) -> bool:
    """True when a method list contains something reachable without the AAA servers."""
    return any(token in _FALLBACK_METHODS for token in methods.split())


# ---------------------------------------------------------------------------
# settings.yaml - defaults.aaa
# ---------------------------------------------------------------------------
class AaaPrompts(_PackModel):
    username: str = "Local-Login-Name:"
    password: str = "Local-Password:"


class AaaAuthentication(_PackModel):
    login: str = "group {group} local"
    enable: str = "group {group} enable"

    @field_validator("login")
    @classmethod
    def _login_needs_a_fallback(cls, value: str) -> str:
        if value and not has_fallback_method(value):
            raise ValueError(
                f"is '{value}', which has no fallback method. If the AAA servers become "
                "unreachable, nobody can log in. Append 'local' or 'none'."
            )
        return value


class AaaAuthorization(_PackModel):
    exec: str = "group {group} local"
    commands: list[PrivilegeLevel] = Field(default_factory=lambda: [15])
    commands_methods: str = "group {group} local"

    @field_validator("commands_methods")
    @classmethod
    def _commands_need_a_fallback(cls, value: str, info: ValidationInfo) -> str:
        if info.data.get("commands") and value and not has_fallback_method(value):
            raise ValueError(
                f"is '{value}', which has no fallback method. If the AAA servers become "
                "unreachable, every command is denied. Append 'local', 'if-authenticated' "
                "or 'none'."
            )
        return value


class AaaAccounting(_PackModel):
    exec: str = "start-stop group {group}"
    commands: list[PrivilegeLevel] = Field(default_factory=lambda: [15])
    commands_methods: str = "start-stop group {group}"


class AaaLocalOnly(_PackModel):
    """Method lists used when AAA is on but the workbook defines no server group."""

    login: str = "local"
    exec: str = "local if-authenticated"


class AaaPolicy(_PackModel):
    """AAA method-list policy.

    Each method string is emitted verbatim after the command it belongs to,
    with {group} replaced by the server-group name from the workbook. An empty
    string omits that line; an empty commands list omits command
    authorization/accounting entirely.
    """

    source_interface: bool = True
    authorization_console: bool = True
    session_id: Literal["common", "unique"] = "common"
    radius_auth_port: TcpUdpPort = 1812
    radius_acct_port: TcpUdpPort = 1813
    prompts: AaaPrompts = Field(default_factory=AaaPrompts)
    authentication: AaaAuthentication = Field(default_factory=AaaAuthentication)
    authorization: AaaAuthorization = Field(default_factory=AaaAuthorization)
    accounting: AaaAccounting = Field(default_factory=AaaAccounting)
    local_only: AaaLocalOnly = Field(default_factory=AaaLocalOnly)


# ---------------------------------------------------------------------------
# settings.yaml - defaults
# ---------------------------------------------------------------------------
class PackDefaults(_PackModel):
    """Every policy knob the templates read as settings.defaults.<key>."""

    # VLANs
    unused_vlan: VlanId = 999
    native_vlan: VlanId = 1
    shutdown_vlan1: bool = True
    # Device fallbacks, used when the workbook cell is left blank
    timezone: str = "GMT"
    mgmt_subnet: SubnetMask = "255.255.255.0"
    # Global services
    service_internal: bool = False
    service_call_home: bool = False
    service_compress_config: bool = True
    service_pad: bool = False
    # DNS
    domain_lookup: bool = False
    # Logging. An empty console level emits 'no logging console'.
    logging_buffer_size: ranged_int(4096, 2147483647, "Logging buffer size") = 128000
    logging_console_level: Union[SyslogLevel, Literal[""]] = ""
    logging_monitor_level: SyslogLevel = "informational"
    logging_trap_level: SyslogLevel = "informational"
    logging_source_interface: bool = True
    # Errdisable
    errdisable_recovery_interval: ranged_int(30, 86400, "Interval") = 1800
    errdisable_recovery_causes: list[str] = Field(default_factory=lambda: [
        "bpduguard",
        "storm-control",
        "udld",
        "gbic-invalid",
        "link-flap",
        "psecure-violation",
    ])
    # SSH / crypto
    ssh_key_label: str = "SEC2048"
    ssh_key_modulus: ranged_int(512, 4096, "RSA modulus") = 2048
    ssh_timeout: ranged_int(1, 120, "SSH timeout") = 15
    ssh_version: Literal[1, 2] = 2
    ssh_dh_min_size: Literal[1024, 2048, 4096] = 2048
    emit_crypto_key_command: bool = False
    ssh_mac_algorithms: str = "hmac-sha2-512 hmac-sha2-256"
    ssh_encryption_algorithms: str = "aes256-ctr aes192-ctr aes128-ctr"
    ssh_kex_algorithms: str = ""
    # Credentials
    password_hash_type: Literal["scrypt", "sha256", "md5"] = "scrypt"
    local_user_privilege: PrivilegeLevel = 15
    # NTP
    ntp_mode: Literal["server", "peer"] = "server"
    ntp_source_interface: bool = True
    # SNMP
    snmp_source_interface: bool = True
    snmp_priv_aes_key_length: Literal[128, 192, 256] = 256
    # Spanning tree
    spanning_tree_mode: Literal["rapid-pvst", "pvst", "mst"] = "rapid-pvst"
    spanning_tree_portfast_bpduguard_default: bool = True
    # QoS
    qos_enabled: bool = False
    qos_trust_uplinks: bool = True
    # Storm control
    storm_control_broadcast: StormControlLevel = "1.00 0.70"
    storm_control_multicast: StormControlLevel = "1.00 0.70"
    storm_control_broadcast_uplink: StormControlLevel = "0.10 0.07"
    storm_control_multicast_uplink: StormControlLevel = "0.10 0.07"
    storm_control_action: Literal["trap", "shutdown", ""] = "trap"
    # Interface-name prefixes treated as uplink speed for the storm-control
    # defaults above. Add 25G/40G/100G names here rather than editing templates.
    uplink_interface_prefixes: list[str] = Field(default_factory=lambda: [
        "TenGigabit",
        "TwentyFiveGig",
        "FortyGigabit",
        "HundredGig",
    ])
    # Banners. The delimiter must not appear inside the message text.
    banner_delimiter: Delimiter = "^"
    aaa_fail_message_delimiter: Delimiter = "#"
    # Lines
    exec_timeout: _ExecTimeout = "15 0"
    vty_length: ranged_int(0, 512, "Terminal length") = 20
    console_stopbits: Literal[1, 1.5, 2] = 1
    escape_character: Union[int, str] = 3
    # DHCP snooping
    dhcp_snooping_vlans: VlanList = "1-4094"
    dhcp_snooping_information_option: bool = False
    # AAA method-list policy
    aaa: AaaPolicy = Field(default_factory=AaaPolicy)
    # Free-form values for a pack's own templates, read as d.custom.<key>.
    # Everything above is checked; nothing in here is.
    custom: dict[str, Any] = Field(default_factory=dict)


class SettingsFile(_PackModel):
    """settings.yaml"""

    schema_version: str | None = None
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    strict_validation: bool = True
    defaults: PackDefaults = Field(default_factory=PackDefaults)


# ---------------------------------------------------------------------------
# hardware_catalog.yaml
# ---------------------------------------------------------------------------
class SwitchModel(_PackModel):
    description: str = ""
    access_ports: ranged_int(0, 1024, "Port count")
    interface_prefix: str
    access_port_start: ranged_int(0, 1024, "Port number") = 1


class UplinkModule(_PackModel):
    description: str = ""
    uplink_ports: ranged_int(0, 1024, "Port count")
    interface_prefix: str = ""
    uplink_port_start: ranged_int(0, 1024, "Port number") = 1

    @model_validator(mode="after")
    def _ports_need_a_prefix(self) -> UplinkModule:
        if self.uplink_ports and not self.interface_prefix:
            raise ValueError(
                f"has {self.uplink_ports} uplink port(s) but no interface_prefix, "
                "so their interface names cannot be built."
            )
        return self


class HardwareCatalogFile(_PackModel):
    """hardware_catalog.yaml"""

    switch_models: dict[str, SwitchModel]
    uplink_modules: dict[str, UplinkModule]


# ---------------------------------------------------------------------------
# port_profiles.yaml
# ---------------------------------------------------------------------------
class PortProfile(_PackModel):
    description: str = ""
    requires_vlan: bool = False
    requires_voice_vlan: bool = False
    requires_native_vlan: bool = False
    requires_port_channel: bool = False
    qos_trust_dscp: bool = False
    template_hint: str


class PortProfilesFile(_PackModel):
    """port_profiles.yaml"""

    profiles: dict[str, PortProfile]


# ---------------------------------------------------------------------------
# template_map.yaml
# ---------------------------------------------------------------------------
class TemplateEntry(_PackModel):
    template: str
    order: int = 99


class TemplateMapFile(_PackModel):
    """template_map.yaml"""

    template_map: dict[str, TemplateEntry]


# ---------------------------------------------------------------------------
# features.yaml
# ---------------------------------------------------------------------------
class FeatureEntry(_PackModel):
    name: str
    description: str = ""
    enabled_by_default: bool = True


class FeaturesFile(_PackModel):
    """features.yaml"""

    features: list[FeatureEntry]


# File name -> model, in the order the loader validates them.
PACK_FILES: dict[str, type[_PackModel]] = {
    "settings.yaml": SettingsFile,
    "hardware_catalog.yaml": HardwareCatalogFile,
    "port_profiles.yaml": PortProfilesFile,
    "template_map.yaml": TemplateMapFile,
    "features.yaml": FeaturesFile,
}


def json_schemas() -> dict[str, str]:
    """Published JSON schema text for each pack file and for a site file, keyed by schema file name."""
    import json

    # Imported here: site_loader depends on the workbook models, which the
    # pack schema otherwise has no need for.
    from cisco_config_generator.site_loader import SiteFile

    models: dict[str, type[BaseModel]] = {
        filename.replace(".yaml", ".schema.json"): model for filename, model in PACK_FILES.items()
    }
    models["site.schema.json"] = SiteFile
    return {
        name: json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n"
        for name, model in models.items()
    }
