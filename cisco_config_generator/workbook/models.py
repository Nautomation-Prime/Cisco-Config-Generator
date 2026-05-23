from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ACLEntry:
    acl_name: str
    remark: str = ""
    action: str = ""
    network: str = ""
    wildcard: str = ""


@dataclass
class VLAN:
    vlan_id: int
    vlan_name: str
    description: str = ""


@dataclass
class Device:
    hostname: str
    mgmt_ip: str
    mgmt_vlan: int
    default_gateway: str
    model: str
    uplink_module: str
    site: str = ""
    timezone: str = "GMT"
    timezone_hours_offset: int = 0
    timezone_minutes_offset: int = 0
    mgmt_subnet: str = "255.255.255.0"


@dataclass
class Interface:
    device_name: str
    interface_name: str
    port_profile: str
    description: str = ""
    access_vlan: int | None = None
    voice_vlan: int | None = None
    native_vlan: int | None = None
    allowed_vlans: str = ""
    storm_control_broadcast: str = ""
    storm_control_multicast: str = ""
    port_channel_number: int | None = None
    qos_trust_dscp: bool = False
    template_hint: str = ""


@dataclass
class GlobalSettings:
    domain_name: str = ""
    ntp_servers: list[str] = field(default_factory=list)
    dns_servers: list[str] = field(default_factory=list)
    summer_time_config: str = ""
    # AAA / TACACS+
    aaa_group_name: str = "TACACS_SERVERS"
    tacacs_server_1: str = ""
    tacacs_server_2: str = ""
    tacacs_key: str = ""
    aaa_fail_message: str = ""
    # SNMPv3 — shared protocol settings
    snmp_auth_protocol: str = "SHA"
    snmp_priv_protocol: str = "AES"
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
    snmp_host: str = ""
    snmp_location: str = ""
    snmp_contact: str = ""
    # VTY / SNMP ACL names — bodies defined in the ACLs workbook sheet
    vty_acl: str = "ACL_VTY_ACCESS"
    snmp_ro_acl: str = "ACL_SNMP_RO_ACCESS"
    snmp_rw_acl: str = "ACL_SNMP_RW_ACCESS"
    # Logging / misc
    syslog_server: str = ""
    banner_motd: str = "AUTHORISED ACCESS ONLY. Disconnect immediately if not authorised."
    enable_secret: str = "changeme"
    local_username: str = ""
    local_password: str = "changeme"


@dataclass
class FeatureSelection:
    base_config: bool = True
    vlans: bool = True
    interfaces: bool = True
    acls: bool = True
    aaa: bool = True
    snmp: bool = True
    ntp: bool = True
    dhcp_snooping: bool = True
    spanning_tree: bool = True
    banner: bool = True


@dataclass
class HardwareProfile:
    model: str
    access_ports: int
    access_interface_prefix: str
    access_port_start: int
    uplink_module: str
    uplink_ports: int
    uplink_interface_prefix: str
    uplink_port_start: int


@dataclass
class Intent:
    devices: list[Device] = field(default_factory=list)
    vlans: list[VLAN] = field(default_factory=list)
    interfaces: list[Interface] = field(default_factory=list)
    global_settings: GlobalSettings = field(default_factory=GlobalSettings)
    feature_selection: FeatureSelection = field(default_factory=FeatureSelection)
    acls: list[ACLEntry] = field(default_factory=list)
