from __future__ import annotations

import pytest
from cisco_config_generator.workbook.validators import validate_intent, ValidationError
from tests.test_workbook import make_device, make_vlan, make_intent
from cisco_config_generator.workbook.models import ACLEntry, GlobalSettings, Interface, PortChannel

HARDWARE = {
    "C9200-48P": {"access_ports": 48, "interface_prefix": "GigabitEthernet1/0/", "access_port_start": 1},
}
UPLINK = {
    "NM-4X": {"uplink_ports": 4, "interface_prefix": "TenGigabitEthernet1/1/", "uplink_port_start": 1},
    "NONE": {"uplink_ports": 0, "interface_prefix": "", "uplink_port_start": 1},
}
PROFILES = {
    "access-user": {"requires_vlan": True, "template_hint": "interfaces_access"},
    "access-voip": {"requires_vlan": True, "requires_voice_vlan": True, "qos_trust_dscp": True, "template_hint": "interfaces_access"},
    "trunk-uplink": {"requires_vlan": False, "template_hint": "interfaces_trunk"},
    "unused": {"requires_vlan": False, "template_hint": "interfaces_unused"},
}


class TestValidation:
    def test_valid_intent_passes(self):
        intent = make_intent()
        errors = validate_intent(intent, HARDWARE, UPLINK, PROFILES)
        assert errors == []

    def test_missing_hostname(self):
        d = make_device(hostname="")
        intent = make_intent(devices=[d])
        errors = validate_intent(intent, HARDWARE, UPLINK, PROFILES)
        assert any("hostname" in e for e in errors)

    def test_unknown_model(self):
        d = make_device(model="UNKNOWN-MODEL")
        intent = make_intent(devices=[d])
        errors = validate_intent(intent, HARDWARE, UPLINK, PROFILES)
        assert any("model" in e for e in errors)

    def test_unknown_port_profile(self):
        iface = Interface(
            device_name="SW-TEST-01",
            interface_name="GigabitEthernet1/0/1",
            port_profile="bad-profile",
            access_vlan=20,
            template_hint="interfaces_access",
        )
        intent = make_intent(interfaces=[iface])
        errors = validate_intent(intent, HARDWARE, UPLINK, PROFILES)
        assert any("port profile" in e for e in errors)

    def test_access_vlan_not_in_vlans(self):
        iface = Interface(
            device_name="SW-TEST-01",
            interface_name="GigabitEthernet1/0/1",
            port_profile="access-user",
            access_vlan=999,  # not defined
            template_hint="interfaces_access",
        )
        intent = make_intent(interfaces=[iface])
        errors = validate_intent(intent, HARDWARE, UPLINK, PROFILES)
        assert any("999" in e for e in errors)

    def test_missing_access_vlan(self):
        iface = Interface(
            device_name="SW-TEST-01",
            interface_name="GigabitEthernet1/0/1",
            port_profile="access-user",
            access_vlan=None,
            template_hint="interfaces_access",
        )
        intent = make_intent(interfaces=[iface])
        errors = validate_intent(intent, HARDWARE, UPLINK, PROFILES)
        assert any("access VLAN" in e for e in errors)

    def test_port_channel_requires_member(self):
        intent = make_intent(
            port_channels=[
                PortChannel(
                    device_name="SW-TEST-01",
                    port_channel_number=7,
                    description="Orphaned bundle",
                )
            ]
        )
        errors = validate_intent(intent, HARDWARE, UPLINK, PROFILES)
        assert any("no member interfaces" in e for e in errors)

    def test_validation_error_exception(self):
        with pytest.raises(ValidationError) as exc_info:
            raise ValidationError(["error one", "error two"])
        assert len(exc_info.value.errors) == 2

    def test_missing_vty_acl_definition(self):
        intent = make_intent(acls=[])
        errors = validate_intent(intent, HARDWARE, UPLINK, PROFILES)
        assert any("VTY ACL" in e for e in errors)

    def test_missing_snmp_ro_acl_definition(self):
        global_settings = GlobalSettings(snmp_ro_user="ROUSER")
        intent = make_intent(
            global_settings=global_settings,
            acls=[ACLEntry(acl_name="ACL_VTY_ACCESS", action="permit", network="10.0.0.0")],
        )
        errors = validate_intent(intent, HARDWARE, UPLINK, PROFILES)
        assert any("SNMP RO ACL" in e for e in errors)

    def test_acl_entry_requires_action_and_network(self):
        intent = make_intent(
            acls=[ACLEntry(acl_name="ACL_VTY_ACCESS", action="permit", network="")]
        )
        errors = validate_intent(intent, HARDWARE, UPLINK, PROFILES)
        assert any("Action and Network/Host" in e for e in errors)

    def test_voice_vlan_not_in_vlans(self):
        iface = Interface(
            device_name="SW-TEST-01",
            interface_name="GigabitEthernet1/0/2",
            port_profile="access-voip",
            access_vlan=20,
            voice_vlan=888,  # not defined in VLANs sheet
            template_hint="interfaces_access",
        )
        intent = make_intent(interfaces=[iface])
        errors = validate_intent(intent, HARDWARE, UPLINK, PROFILES)
        assert any("voice VLAN 888" in e for e in errors)

    def test_snmp_host_requires_snmp_user(self):
        global_settings = GlobalSettings(snmp_host="10.0.1.20")
        intent = make_intent(global_settings=global_settings)
        errors = validate_intent(intent, HARDWARE, UPLINK, PROFILES)
        assert any("snmp_host" in e for e in errors)

    def test_timezone_hours_offset_out_of_range(self):
        device = make_device(timezone_hours_offset=24)
        intent = make_intent(devices=[device])
        errors = validate_intent(intent, HARDWARE, UPLINK, PROFILES)
        assert any("timezone hours offset" in e for e in errors)

    def test_timezone_minutes_offset_out_of_range(self):
        device = make_device(timezone_minutes_offset=60)
        intent = make_intent(devices=[device])
        errors = validate_intent(intent, HARDWARE, UPLINK, PROFILES)
        assert any("timezone minutes offset" in e for e in errors)

    def test_invalid_storm_control_broadcast_format(self):
        iface = Interface(
            device_name="SW-TEST-01",
            interface_name="TenGigabitEthernet1/1/1",
            port_profile="trunk-uplink",
            native_vlan=10,
            storm_control_broadcast="high",
            template_hint="interfaces_trunk",
        )
        intent = make_intent(interfaces=[iface])
        errors = validate_intent(intent, HARDWARE, UPLINK, PROFILES)
        assert any("Storm Control Broadcast" in e for e in errors)

    def test_invalid_storm_control_multicast_format(self):
        iface = Interface(
            device_name="SW-TEST-01",
            interface_name="TenGigabitEthernet1/1/1",
            port_profile="trunk-uplink",
            native_vlan=10,
            storm_control_multicast="high",
            template_hint="interfaces_trunk",
        )
        intent = make_intent(interfaces=[iface])
        errors = validate_intent(intent, HARDWARE, UPLINK, PROFILES)
        assert any("Storm Control Multicast" in e for e in errors)

    def test_duplicate_hostnames_rejected(self):
        devices = [make_device(), make_device()]  # both hostname SW-TEST-01
        intent = make_intent(devices=devices)
        errors = validate_intent(intent, HARDWARE, UPLINK, PROFILES)
        assert any("Duplicate hostname" in e for e in errors)

    def test_placeholder_enable_secret_rejected(self):
        global_settings = GlobalSettings(enable_secret="changeme")
        intent = make_intent(global_settings=global_settings)
        errors = validate_intent(intent, HARDWARE, UPLINK, PROFILES)
        assert any("enable_secret" in e for e in errors)

    def test_placeholder_local_password_rejected(self):
        global_settings = GlobalSettings(
            enable_secret="StrongSecret99!",
            local_username="admin",
            local_password="changeme",
        )
        intent = make_intent(global_settings=global_settings)
        errors = validate_intent(intent, HARDWARE, UPLINK, PROFILES)
        assert any("local_password" in e for e in errors)

    def test_placeholder_local_password_ignored_without_username(self):
        """local_password placeholder is only flagged when a local_username is also set."""
        global_settings = GlobalSettings(enable_secret="StrongSecret99!", local_username="")
        intent = make_intent(global_settings=global_settings)
        errors = validate_intent(intent, HARDWARE, UPLINK, PROFILES)
        assert not any("local_password" in e for e in errors)
