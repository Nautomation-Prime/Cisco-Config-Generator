from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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
    template_hint: str = ""


@dataclass
class GlobalSettings:
    domain_name: str = ""
    ntp_servers: list[str] = field(default_factory=list)
    dns_servers: list[str] = field(default_factory=list)
    snmp_community: str = ""
    snmp_host: str = ""
    syslog_server: str = ""
    banner_motd: str = "AUTHORISED ACCESS ONLY. Disconnect immediately if not authorised."
    enable_secret: str = "changeme"
    local_username: str = ""
    local_password: str = "changeme"
    aaa_server: str = ""
    aaa_key: str = ""


@dataclass
class FeatureSelection:
    base_config: bool = True
    vlans: bool = True
    interfaces: bool = True


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
