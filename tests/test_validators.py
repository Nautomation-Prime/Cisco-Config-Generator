from __future__ import annotations

import pytest
from cisco_config_generator.workbook.validators import validate_intent, ValidationError
from tests.test_workbook import make_device, make_vlan, make_intent
from cisco_config_generator.workbook.models import ACLEntry, GlobalSettings, Interface

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
