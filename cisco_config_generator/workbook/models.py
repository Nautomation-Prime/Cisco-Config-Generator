"""Typed models for the intent workbook and the site files.

Each model checks everything that can be judged from a single row or entry:
types, ranges, address formats and allowed values. Checks that compare rows
with each other, with a site or with the pack (duplicate hostnames, VLAN
references, unknown models) live in validators.py.
"""

from __future__ import annotations

import ipaddress
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field, model_validator

from cisco_config_generator.field_types import (
    Hostname,
    IPv4,
    IPv4List,
    OptionalIPv4,
    OptionalStormControlLevel,
    OptionalSubnetMask,
    VlanId,
    AllowedVlans,
    is_contiguous_mask,
    ranged_int,
)

DEFAULT_BANNER = "AUTHORISED ACCESS ONLY. Disconnect immediately if not authorised."

PortChannelNumber = ranged_int(1, 128, "Port-channel number")


def _lower(value: Any) -> Any:
    return value.strip().lower() if isinstance(value, str) else value


def _upper(value: Any) -> Any:
    return value.strip().upper() if isinstance(value, str) else value


def _as_text(value: Any) -> Any:
    """A cell holding 7 is the key type '7', not the number seven."""
    return str(value).strip() if isinstance(value, (int, str)) and not isinstance(value, bool) else value


def _check_vlan_name(value: str) -> str:
    if not 1 <= len(value) <= 32:
        raise ValueError(f"'{value}' must be 1 to 32 characters long.")
    return value


VlanName = Annotated[str, AfterValidator(_check_vlan_name)]


def _check_acl_address(value: str) -> str:
    """'any', a host or network address, or 'host <address>'."""
    if not value:
        return value
    if value.lower() == "any":
        return "any"
    address = value[5:].strip() if value.lower().startswith("host ") else value
    try:
        ipaddress.IPv4Address(address)
    except (ipaddress.AddressValueError, ValueError):
        raise ValueError(
            f"'{value}' is not a valid Network/Host. Use an IPv4 address, or 'any'."
        ) from None
    return value


def _check_wildcard(value: str) -> str:
    if not value:
        return value
    try:
        ipaddress.IPv4Address(value)
    except (ipaddress.AddressValueError, ValueError):
        raise ValueError(f"'{value}' is not a valid wildcard mask, for example 0.0.0.255.") from None
    # 255.255.255.0 as a wildcard matches one host number in every subnet -
    # almost always a subnet mask typed into the wrong column.
    if is_contiguous_mask(value) and value not in ("0.0.0.0", "255.255.255.255"):
        raise ValueError(
            f"'{value}' is a subnet mask, but ACLs take a wildcard mask - the inverse. "
            "For a /24, use 0.0.0.255."
        )
    return value


AclAddress = Annotated[str, AfterValidator(_check_acl_address)]
Wildcard = Annotated[str, AfterValidator(_check_wildcard)]


class _WorkbookModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        coerce_numbers_to_str=True,
    )


class ACLEntry(_WorkbookModel):
    acl_name: str
    remark: str = ""
    action: Annotated[Literal["permit", "deny", ""], BeforeValidator(_lower)] = ""
    network: AclAddress = ""
    wildcard: Wildcard = ""

    @model_validator(mode="after")
    def _entry_shape(self) -> ACLEntry:
        has_action = bool(self.action)
        has_network = bool(self.network)
        if has_action != has_network:
            raise ValueError("ACL entry must include both Action and Network/Host together.")
        if not self.remark and not has_action:
            raise ValueError("ACL entry is empty. Populate Remark or Action + Network/Host.")
        if self.wildcard and (self.network == "any" or self.network.lower().startswith("host ")):
            raise ValueError(
                f"ACL entry has Wildcard '{self.wildcard}', but Network/Host '{self.network}' "
                "does not take one. Clear the Wildcard cell."
            )
        if self.wildcard and not has_network:
            raise ValueError("ACL entry has a Wildcard but no Network/Host.")
        return self


class VLAN(_WorkbookModel):
    vlan_id: VlanId
    vlan_name: VlanName
    description: str = ""


class Device(_WorkbookModel):
    hostname: Hostname
    mgmt_ip: IPv4
    mgmt_vlan: VlanId
    default_gateway: IPv4
    model: str
    uplink_module: str
    site: str = ""
    # Timezone and Mgmt Subnet stay blank when the cell is empty - the
    # orchestrator fills them from the device's site, then the pack.
    timezone: str = ""
    timezone_hours_offset: ranged_int(-23, 23, "Timezone hours offset") = 0
    timezone_minutes_offset: ranged_int(0, 59, "Timezone minutes offset") = 0
    mgmt_subnet: OptionalSubnetMask = ""


class Interface(_WorkbookModel):
    device_name: str
    interface_name: str
    port_profile: str
    description: str = ""
    access_vlan: VlanId | None = None
    voice_vlan: VlanId | None = None
    native_vlan: VlanId | None = None
    allowed_vlans: AllowedVlans = ""
    storm_control_broadcast: OptionalStormControlLevel = ""
    storm_control_multicast: OptionalStormControlLevel = ""
    port_channel_number: PortChannelNumber | None = None
    # Filled from the port profile by the loader, not read from the sheet.
    qos_trust_dscp: bool = False
    template_hint: str = ""


class PortChannel(_WorkbookModel):
    device_name: str
    port_channel_number: PortChannelNumber
    description: str = ""
    native_vlan: VlanId | None = None
    allowed_vlans: AllowedVlans = ""
    storm_control_broadcast: OptionalStormControlLevel = ""
    storm_control_multicast: OptionalStormControlLevel = ""
    template_hint: str = "port_channels"


class GlobalSettings(_WorkbookModel):
    domain_name: str = ""
    ntp_servers: IPv4List = Field(default_factory=list)
    dns_servers: IPv4List = Field(default_factory=list)
    summer_time_config: str = ""
    # AAA
    aaa_group_name: str = "TACACS_SERVERS"
    # tacacs+ or radius - selects both the server-group type and the
    # 'ip <protocol> source-interface' command.
    aaa_protocol: Annotated[Literal["tacacs+", "radius"], BeforeValidator(_lower)] = "tacacs+"
    # Any number of servers.
    aaa_servers: IPv4List = Field(default_factory=list)
    aaa_key: str = ""
    # 0 = plaintext (the switch encrypts it), 6 or 7 = already encrypted
    aaa_key_type: Annotated[Literal["0", "6", "7"], BeforeValidator(_as_text)] = "0"
    aaa_fail_message: str = ""
    # SNMPv3 — shared protocol settings
    snmp_auth_protocol: Annotated[Literal["SHA", "MD5"], BeforeValidator(_upper)] = "SHA"
    snmp_priv_protocol: Annotated[Literal["AES", "DES", "3DES"], BeforeValidator(_upper)] = "AES"
    # SNMPv3 — read-only user/group
    snmp_ro_group: str = "SNMPv3_RO"
    snmp_ro_user: str = ""
    snmp_ro_auth_password: str = ""
    snmp_ro_priv_password: str = ""
    # SNMPv3 — read-write user/group
    snmp_rw_group: str = "SNMPv3_RW"
    snmp_rw_user: str = ""
    snmp_rw_auth_password: str = ""
    snmp_rw_priv_password: str = ""
    snmp_host: OptionalIPv4 = ""
    snmp_location: str = ""
    snmp_contact: str = ""
    # VTY / SNMP ACL names — bodies defined in the site's acls list
    vty_acl: str = "ACL_VTY_ACCESS"
    snmp_ro_acl: str = "ACL_SNMP_RO_ACCESS"
    snmp_rw_acl: str = "ACL_SNMP_RW_ACCESS"
    # Logging / misc
    syslog_server: IPv4List = Field(default_factory=list)
    banner_motd: str = DEFAULT_BANNER
    enable_secret: str = "changeme"
    local_username: str = ""
    local_password: str = "changeme"


class FeatureSelection(_WorkbookModel):
    base_config: bool = True
    vlans: bool = True
    interfaces: bool = True
    port_channels: bool = True
    acls: bool = True
    aaa: bool = True
    snmp: bool = True
    ntp: bool = True
    dhcp_snooping: bool = True
    spanning_tree: bool = True
    banner: bool = True


class HardwareProfile(BaseModel):
    """The resolved hardware for one device, as handed to the templates."""

    model: str
    access_ports: int
    access_interface_prefix: str
    access_port_start: int
    uplink_module: str
    uplink_ports: int
    uplink_interface_prefix: str
    uplink_port_start: int


class Intent(BaseModel):
    """Everything parsed from the intent workbook.

    Site-scoped data (global settings, VLANs, ACLs) is deliberately not part
    of Intent — the workbook only says which site each device belongs to
    (Device.site). The orchestrator resolves that into a Site (see
    cisco_config_generator.site_loader) once devices are known.
    """
    devices: list[Device] = Field(default_factory=list)
    interfaces: list[Interface] = Field(default_factory=list)
    port_channels: list[PortChannel] = Field(default_factory=list)
    feature_selection: FeatureSelection = Field(default_factory=FeatureSelection)


class Site(BaseModel):
    """Everything a site YAML file defines: shared policy, VLANs, and ACLs.

    One Site is loaded per distinct value in the workbook's Devices.Site
    column, from sites/<site>.yaml (see cisco_config_generator.site_loader).
    """
    name: str
    global_settings: GlobalSettings = Field(default_factory=GlobalSettings)
    vlans: list[VLAN] = Field(default_factory=list)
    acls: list[ACLEntry] = Field(default_factory=list)
    # Device-column fallbacks: used when a device's own Timezone/Mgmt Subnet
    # cell is blank, before falling back further to the pack's defaults.
    timezone: str = ""
    mgmt_subnet: OptionalSubnetMask = ""
