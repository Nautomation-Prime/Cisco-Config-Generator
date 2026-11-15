from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError as PydanticValidationError

from cisco_config_generator.field_types import friendly_message
from cisco_config_generator.pack_schema import PortProfile, SwitchModel, UplinkModule
from cisco_config_generator.workbook.models import (
    ACLEntry, Device, GlobalSettings, Interface, PortChannel, Site, VLAN,
)
from cisco_config_generator.workbook.validators import validate_intent, ValidationError
from tests.test_workbook import make_device, make_vlan, make_site, make_intent

HARDWARE = {
    "C9200-48P": SwitchModel(access_ports=48, interface_prefix="GigabitEthernet1/0/"),
}
UPLINK = {
    "NM-4X": UplinkModule(uplink_ports=4, interface_prefix="TenGigabitEthernet1/1/"),
    "NONE": UplinkModule(uplink_ports=0),
}
PROFILES = {
    "access-user": PortProfile(requires_vlan=True, template_hint="interfaces_access"),
    "access-voip": PortProfile(
        requires_vlan=True, requires_voice_vlan=True, qos_trust_dscp=True, template_hint="interfaces_access"
    ),
    "trunk-uplink": PortProfile(template_hint="interfaces_trunk"),
    "unused": PortProfile(template_hint="interfaces_unused"),
}


def _validate(intent, sites: dict[str, Site] | None = None, **kwargs) -> list[str]:
    sites = sites if sites is not None else {"TESTSITE": make_site()}
    return validate_intent(
        intent, HARDWARE, UPLINK, PROFILES,
        sites=sites, available_sites=sorted(sites.keys()), **kwargs,
    )


class TestValidation:
    def test_valid_intent_passes(self):
        intent = make_intent()
        errors = _validate(intent)
        assert errors == []

    def test_unknown_model(self):
        d = make_device(model="UNKNOWN-MODEL")
        intent = make_intent(devices=[d])
        errors = _validate(intent)
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
        errors = _validate(intent)
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
        errors = _validate(intent)
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
        errors = _validate(intent)
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
        errors = _validate(intent)
        assert any("no member interfaces" in e for e in errors)

    def test_validation_error_exception(self):
        with pytest.raises(ValidationError) as exc_info:
            raise ValidationError(["error one", "error two"])
        assert len(exc_info.value.errors) == 2

    def test_missing_vty_acl_definition(self):
        intent = make_intent()
        sites = {"TESTSITE": make_site(acls=[])}
        errors = _validate(intent, sites)
        assert any("VTY ACL" in e for e in errors)

    def test_missing_snmp_ro_acl_definition(self):
        intent = make_intent()
        sites = {"TESTSITE": make_site(
            global_settings=GlobalSettings(enable_secret="EXAMPLE-enable-secret", snmp_ro_user="ROUSER"),
            acls=[ACLEntry(acl_name="ACL_VTY_ACCESS", action="permit", network="10.0.0.0")],
        )}
        errors = _validate(intent, sites)
        assert any("SNMP RO ACL" in e for e in errors)

    def test_voice_vlan_not_in_vlans(self):
        iface = Interface(
            device_name="SW-TEST-01",
            interface_name="GigabitEthernet1/0/2",
            port_profile="access-voip",
            access_vlan=20,
            voice_vlan=888,  # not defined at the site
            template_hint="interfaces_access",
        )
        intent = make_intent(interfaces=[iface])
        errors = _validate(intent)
        assert any("voice VLAN 888" in e for e in errors)

    def test_snmp_host_requires_snmp_user(self):
        intent = make_intent()
        sites = {"TESTSITE": make_site(
            global_settings=GlobalSettings(enable_secret="EXAMPLE-enable-secret", snmp_host="10.0.1.20")
        )}
        errors = _validate(intent, sites)
        assert any("snmp_host" in e for e in errors)

    def test_duplicate_hostnames_rejected(self):
        devices = [make_device(), make_device()]  # both hostname SW-TEST-01
        intent = make_intent(devices=devices)
        errors = _validate(intent)
        assert any("Duplicate hostname" in e for e in errors)

    def test_duplicate_vlan_ids_rejected(self):
        intent = make_intent()
        sites = {"TESTSITE": make_site(vlans=[make_vlan(10, "MGMT"), make_vlan(20, "DATA"), make_vlan(20, "AGAIN")])}
        assert "Site 'TESTSITE': Duplicate VLAN ID: 20" in _validate(intent, sites)

    def test_placeholder_enable_secret_rejected(self):
        intent = make_intent()
        sites = {"TESTSITE": make_site(global_settings=GlobalSettings(enable_secret="changeme"))}
        errors = _validate(intent, sites)
        assert any("enable_secret" in e for e in errors)

    def test_placeholder_local_password_rejected(self):
        intent = make_intent()
        sites = {"TESTSITE": make_site(global_settings=GlobalSettings(
            enable_secret="EXAMPLE-enable-secret",
            local_username="admin",
            local_password="changeme",
        ))}
        errors = _validate(intent, sites)
        assert any("local_password" in e for e in errors)

    def test_placeholder_local_password_ignored_without_username(self):
        """local_password placeholder is only flagged when a local_username is also set."""
        intent = make_intent()
        sites = {"TESTSITE": make_site(
            global_settings=GlobalSettings(enable_secret="EXAMPLE-enable-secret", local_username="")
        )}
        errors = _validate(intent, sites)
        assert not any("local_password" in e for e in errors)

    def test_hardening_warnings_do_not_block_when_not_strict(self):
        """strict_validation: false downgrades placeholder-credential checks to warnings."""
        intent = make_intent()
        sites = {"TESTSITE": make_site(global_settings=GlobalSettings(enable_secret="changeme"))}
        errors = _validate(intent, sites, strict=False)
        assert not any("enable_secret" in e for e in errors)

    def test_structural_errors_still_block_when_not_strict(self):
        """strict_validation: false never hides errors that would break rendering."""
        intent = make_intent()
        sites = {"TESTSITE": make_site(acls=[])}  # undefined vty_acl reference
        errors = _validate(intent, sites, strict=False)
        assert any("VTY ACL" in e for e in errors)


class TestSiteValidation:
    def test_device_with_no_site_is_rejected(self):
        intent = make_intent(devices=[make_device(site="")])
        errors = _validate(intent)
        assert any("has no Site" in e for e in errors)

    def test_device_referencing_unknown_site_is_rejected(self):
        intent = make_intent(devices=[make_device(site="NOPE")])
        errors = _validate(intent)
        assert any("site 'NOPE' was not found" in e for e in errors)

    def test_available_sites_are_listed_in_the_hint(self):
        intent = make_intent(devices=[make_device(site="NOPE")])
        errors = _validate(intent)
        assert any("TESTSITE" in e for e in errors)


class TestCrossReferences:
    def test_management_vlan_must_exist_at_the_site(self):
        """An SVI on an undefined VLAN never comes up - catch it before deployment."""
        intent = make_intent(devices=[make_device(mgmt_vlan=77)])
        errors = _validate(intent)
        assert any("management VLAN 77" in e for e in errors)

    def test_aaa_servers_without_a_key_is_rejected(self):
        intent = make_intent()
        sites = {"TESTSITE": make_site(global_settings=GlobalSettings(
            enable_secret="EXAMPLE-enable-secret",
            aaa_servers=["10.0.1.40"],
            local_username="netadmin",
            local_password="EXAMPLE-local-password",
        ))}
        errors = _validate(intent, sites)
        assert any("empty shared secret" in e for e in errors)

    def test_aaa_servers_without_a_local_account_warns_but_does_not_block_when_not_strict(self):
        """No local user means no way back in when the AAA servers are unreachable - a
        hardening recommendation, not something that breaks rendering."""
        intent = make_intent()
        sites = {"TESTSITE": make_site(global_settings=GlobalSettings(
            enable_secret="EXAMPLE-enable-secret",
            aaa_servers=["10.0.1.40"],
            aaa_key="EXAMPLE-tacacs-key",
        ))}
        errors = _validate(intent, sites)
        assert any("no fallback" in e for e in errors)
        assert not any("no fallback" in e for e in _validate(intent, sites, strict=False))


# ---------------------------------------------------------------------------
# Single-row rules, enforced by the workbook models as each row loads
# ---------------------------------------------------------------------------
def _row_errors(model: type[BaseModel], /, **values) -> list[str]:
    """The messages a single workbook row would produce, keyed by field."""
    try:
        model.model_validate(values)
    except PydanticValidationError as exc:
        return [f"{'.'.join(map(str, e['loc']))}: {friendly_message(e, model)}" for e in exc.errors()]
    return []


DEVICE_ROW = dict(
    hostname="SW-TEST-01",
    mgmt_ip="10.0.10.2",
    mgmt_vlan=10,
    default_gateway="10.0.10.1",
    model="C9200-48P",
    uplink_module="NM-4X",
)
TRUNK_ROW = dict(
    device_name="SW-TEST-01",
    interface_name="TenGigabitEthernet1/1/1",
    port_profile="trunk-uplink",
    native_vlan=10,
)


class TestDeviceRow:
    def test_valid_row_passes(self):
        assert _row_errors(Device, **DEVICE_ROW) == []

    def test_missing_hostname(self):
        row = {k: v for k, v in DEVICE_ROW.items() if k != "hostname"}
        assert _row_errors(Device, **row) == ["hostname: is required."]

    def test_invalid_hostname(self):
        errors = _row_errors(Device, **{**DEVICE_ROW, "hostname": "SW TEST 01"})
        assert any("valid IOS hostname" in e for e in errors)

    def test_invalid_management_ip(self):
        errors = _row_errors(Device, **{**DEVICE_ROW, "mgmt_ip": "10.0.10.999"})
        assert errors == ["mgmt_ip: '10.0.10.999' is not a valid IPv4 address."]

    def test_invalid_default_gateway(self):
        errors = _row_errors(Device, **{**DEVICE_ROW, "default_gateway": "not-an-ip"})
        assert errors == ["default_gateway: 'not-an-ip' is not a valid IPv4 address."]

    def test_management_vlan_out_of_range(self):
        errors = _row_errors(Device, **{**DEVICE_ROW, "mgmt_vlan": 5000})
        assert errors == ["mgmt_vlan: VLAN 5000 is out of range. Valid range: 1 to 4094."]

    def test_non_numeric_management_vlan(self):
        errors = _row_errors(Device, **{**DEVICE_ROW, "mgmt_vlan": "ten"})
        assert errors == ["mgmt_vlan: expected a whole number, got 'ten'."]

    def test_non_contiguous_subnet_mask(self):
        errors = _row_errors(Device, **{**DEVICE_ROW, "mgmt_subnet": "255.255.0.255"})
        assert any("subnet mask" in e for e in errors)

    def test_valid_subnet_masks_pass(self):
        for mask in ("255.255.255.0", "255.255.254.0", "255.255.255.252", "255.0.0.0"):
            assert _row_errors(Device, **{**DEVICE_ROW, "mgmt_subnet": mask}) == [], mask

    def test_timezone_hours_offset_out_of_range(self):
        errors = _row_errors(Device, **{**DEVICE_ROW, "timezone_hours_offset": 24})
        assert any("Timezone hours offset 24 is out of range" in e for e in errors)

    def test_timezone_minutes_offset_out_of_range(self):
        errors = _row_errors(Device, **{**DEVICE_ROW, "timezone_minutes_offset": 60})
        assert any("Timezone minutes offset 60 is out of range" in e for e in errors)

    def test_every_problem_in_a_row_is_reported(self):
        errors = _row_errors(Device, **{**DEVICE_ROW, "mgmt_ip": "x", "default_gateway": "y", "mgmt_vlan": 0})
        assert len(errors) == 3


class TestVlanRow:
    def test_vlan_id_out_of_range(self):
        assert _row_errors(VLAN, vlan_id=9999, vlan_name="BAD") == [
            "vlan_id: VLAN 9999 is out of range. Valid range: 1 to 4094."
        ]

    def test_vlan_name_is_required(self):
        assert _row_errors(VLAN, vlan_id=10) == ["vlan_name: is required."]

    def test_vlan_name_longer_than_ios_allows(self):
        assert any("1 to 32 characters" in e for e in _row_errors(VLAN, vlan_id=10, vlan_name="X" * 33))


class TestInterfaceRow:
    def test_invalid_storm_control_broadcast_format(self):
        errors = _row_errors(Interface, **TRUNK_ROW, storm_control_broadcast="high")
        assert any(e.startswith("storm_control_broadcast:") and "two numeric values" in e for e in errors)

    def test_invalid_storm_control_multicast_format(self):
        errors = _row_errors(Interface, **TRUNK_ROW, storm_control_multicast="high")
        assert any(e.startswith("storm_control_multicast:") and "two numeric values" in e for e in errors)

    def test_allowed_vlans_spaces_are_removed(self):
        """IOS rejects 'switchport trunk allowed vlan 10, 20'."""
        assert Interface(**TRUNK_ROW, allowed_vlans="10, 20, 30-40").allowed_vlans == "10,20,30-40"

    def test_allowed_vlans_keywords_are_accepted(self):
        assert Interface(**TRUNK_ROW, allowed_vlans="ALL").allowed_vlans == "all"
        assert Interface(**TRUNK_ROW, allowed_vlans="none").allowed_vlans == "none"

    def test_allowed_vlans_must_be_a_vlan_list(self):
        errors = _row_errors(Interface, **TRUNK_ROW, allowed_vlans="10;20")
        assert any("not a valid VLAN list" in e for e in errors)

    def test_allowed_vlans_out_of_range(self):
        errors = _row_errors(Interface, **TRUNK_ROW, allowed_vlans="10,5000")
        assert any("contains VLAN 5000, which is out of range" in e for e in errors)

    def test_backwards_vlan_range(self):
        errors = _row_errors(Interface, **TRUNK_ROW, allowed_vlans="40-30")
        assert any("backwards range '40-30'" in e for e in errors)

    def test_port_channel_number_out_of_range(self):
        errors = _row_errors(Interface, **TRUNK_ROW, port_channel_number=0)
        assert any("Port-channel number 0 is out of range" in e for e in errors)


class TestAclRow:
    def test_entry_requires_action_and_network(self):
        errors = _row_errors(ACLEntry, acl_name="ACL_VTY_ACCESS", action="permit")
        assert any("Action and Network/Host" in e for e in errors)

    def test_empty_entry(self):
        errors = _row_errors(ACLEntry, acl_name="ACL_VTY_ACCESS")
        assert any("ACL entry is empty" in e for e in errors)

    def test_invalid_action(self):
        errors = _row_errors(ACLEntry, acl_name="A", action="allow", network="10.0.0.1")
        assert errors == ["action: is 'allow'. Valid values: 'permit', 'deny' or ''."]

    def test_action_is_case_insensitive(self):
        assert ACLEntry(acl_name="A", action="PERMIT", network="10.0.0.1").action == "permit"

    def test_invalid_network(self):
        errors = _row_errors(ACLEntry, acl_name="A", action="permit", network="10.1O.1.5")
        assert any("'10.1O.1.5' is not a valid Network/Host" in e for e in errors)

    def test_any_and_host_forms_are_accepted(self):
        assert _row_errors(ACLEntry, acl_name="A", action="deny", network="ANY") == []
        assert _row_errors(ACLEntry, acl_name="A", action="permit", network="host 10.0.0.1") == []

    def test_truncated_wildcard(self):
        errors = _row_errors(ACLEntry, acl_name="A", action="permit", network="10.10.0.0", wildcard="0.0.255")
        assert any("'0.0.255' is not a valid wildcard mask" in e for e in errors)

    def test_subnet_mask_in_the_wildcard_column(self):
        errors = _row_errors(
            ACLEntry, acl_name="A", action="permit", network="10.10.0.0", wildcard="255.255.255.0"
        )
        assert any("is a subnet mask, but ACLs take a wildcard mask" in e for e in errors)

    def test_wildcard_with_any_is_rejected(self):
        errors = _row_errors(ACLEntry, acl_name="A", action="deny", network="any", wildcard="0.0.0.255")
        assert any("does not take one" in e for e in errors)


class TestGlobalSettingsRow:
    def test_invalid_aaa_key_type(self):
        assert _row_errors(GlobalSettings, aaa_key_type="9") == [
            "aaa_key_type: is '9'. Valid values: '0', '6' or '7'."
        ]

    def test_numeric_aaa_key_type_cell(self):
        assert GlobalSettings(aaa_key_type=7).aaa_key_type == "7"

    def test_invalid_aaa_protocol(self):
        errors = _row_errors(GlobalSettings, aaa_protocol="diameter")
        assert any(e.startswith("aaa_protocol: is 'diameter'") for e in errors)

    def test_invalid_aaa_server_address(self):
        errors = _row_errors(GlobalSettings, aaa_servers="10.0.1.40, 10.0.1.oops")
        assert errors == ["aaa_servers.1: '10.0.1.oops' is not a valid IPv4 address."]

    def test_invalid_global_server_address(self):
        errors = _row_errors(GlobalSettings, ntp_servers=["10.0.0.1", "10.0.0.oops"])
        assert any(e.startswith("ntp_servers") for e in errors)

    def test_invalid_snmp_host(self):
        assert any(e.startswith("snmp_host") for e in _row_errors(GlobalSettings, snmp_host="nms.local"))

    def test_invalid_snmp_auth_protocol(self):
        errors = _row_errors(GlobalSettings, snmp_auth_protocol="sha256")
        assert any(e.startswith("snmp_auth_protocol") for e in errors)

    def test_misspelt_setting_suggests_the_real_one(self):
        errors = _row_errors(GlobalSettings, ntp_server="10.0.0.1")
        assert errors == [
            "ntp_server: is not a recognised setting. Did you mean 'ntp_servers'? "
            "Check the spelling, or remove it."
        ]


# ---------------------------------------------------------------------------
# ACL entries that can never take effect
# ---------------------------------------------------------------------------
def _acl(*entries: tuple[str, str, str]) -> list[ACLEntry]:
    return [
        ACLEntry(acl_name="ACL_VTY_ACCESS", action=action, network=network, wildcard=wildcard)
        for action, network, wildcard in entries
    ]


class TestAclShadowing:
    def _errors(self, acls: list[ACLEntry]) -> list[str]:
        sites = {"TESTSITE": make_site(acls=acls)}
        return [e for e in _validate(make_intent(), sites) if "never take effect" in e]

    def test_permit_after_deny_any_is_reported(self):
        errors = self._errors(_acl(
            ("permit", "10.10.0.0", "0.0.0.255"),
            ("deny", "any", ""),
            ("permit", "10.20.0.0", "0.0.0.255"),
        ))
        assert errors == [
            "Site 'TESTSITE': ACL 'ACL_VTY_ACCESS': 'permit 10.20.0.0 0.0.0.255' can never take "
            "effect - the earlier entry 'deny any' already matches every address it covers. Move it "
            "above that entry, or remove it."
        ]

    def test_deny_for_a_host_inside_an_earlier_permit_is_reported(self):
        errors = self._errors(_acl(
            ("permit", "10.10.0.0", "0.0.0.255"),
            ("deny", "10.10.0.5", ""),
        ))
        assert len(errors) == 1
        assert "'deny 10.10.0.5'" in errors[0]

    def test_host_keyword_is_understood(self):
        errors = self._errors(_acl(
            ("permit", "10.10.0.0", "0.0.0.255"),
            ("deny", "host 10.10.0.5", ""),
        ))
        assert len(errors) == 1

    def test_correct_order_is_accepted(self):
        assert self._errors(_acl(
            ("deny", "10.10.0.5", ""),
            ("permit", "10.10.0.0", "0.0.0.255"),
            ("deny", "any", ""),
        )) == []

    def test_partially_overlapping_entries_are_accepted(self):
        """A /24 deny does not shadow a /16 permit - the permit still matches the rest."""
        assert self._errors(_acl(
            ("deny", "10.10.1.0", "0.0.0.255"),
            ("permit", "10.10.0.0", "0.0.255.255"),
        )) == []

    def test_redundant_entry_with_the_same_action_is_accepted(self):
        assert self._errors(_acl(
            ("permit", "10.0.0.0", "0.255.255.255"),
            ("permit", "10.10.0.0", "0.0.0.255"),
        )) == []

    def test_non_contiguous_wildcard(self):
        """0.0.255.0 matches 10.10.x.5 for any x - so it shadows a deny for 10.10.7.5."""
        errors = self._errors(_acl(
            ("permit", "10.10.0.5", "0.0.255.0"),
            ("deny", "10.10.7.5", ""),
        ))
        assert len(errors) == 1

    def test_separate_acls_do_not_shadow_each_other(self):
        acls = [
            ACLEntry(acl_name="ACL_VTY_ACCESS", action="deny", network="any"),
            ACLEntry(acl_name="ACL_SNMP_RO_ACCESS", action="permit", network="10.0.0.1"),
        ]
        assert self._errors(acls) == []
