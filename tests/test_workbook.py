from __future__ import annotations

import pytest
from cisco_config_generator.workbook.models import (
    ACLEntry, Device, VLAN, Interface, GlobalSettings, FeatureSelection, Intent
)


def make_device(**kwargs) -> Device:
    defaults = dict(
        hostname="SW-TEST-01",
        mgmt_ip="10.0.10.2",
        mgmt_vlan=10,
        default_gateway="10.0.10.1",
        model="C9200-48P",
        uplink_module="NM-4X",
    )
    defaults.update(kwargs)
    return Device(**defaults)


def make_vlan(vlan_id=10, vlan_name="MGMT") -> VLAN:
    return VLAN(vlan_id=vlan_id, vlan_name=vlan_name)


def make_intent(**kwargs) -> Intent:
    intent = Intent(
        devices=[make_device()],
        vlans=[make_vlan(10, "MGMT"), make_vlan(20, "DATA")],
        interfaces=[
            Interface(
                device_name="SW-TEST-01",
                interface_name="GigabitEthernet1/0/1",
                port_profile="access-user",
                access_vlan=20,
                template_hint="interfaces_access",
            )
        ],
        acls=[
            ACLEntry(
                acl_name="ACL_VTY_ACCESS",
                action="permit",
                network="10.0.0.0",
                wildcard="0.0.0.255",
            )
        ],
        global_settings=GlobalSettings(),
        feature_selection=FeatureSelection(),
    )
    for k, v in kwargs.items():
        setattr(intent, k, v)
    return intent


class TestDeviceModel:
    def test_device_defaults(self):
        d = make_device()
        assert d.timezone == "GMT"
        assert d.mgmt_subnet == "255.255.255.0"

    def test_device_required_fields(self):
        d = make_device(hostname="SW-01")
        assert d.hostname == "SW-01"


class TestVLANModel:
    def test_vlan_id(self):
        v = make_vlan(100, "SERVERS")
        assert v.vlan_id == 100
        assert v.vlan_name == "SERVERS"


class TestIntentModel:
    def test_intent_has_devices(self):
        intent = make_intent()
        assert len(intent.devices) == 1
        assert intent.devices[0].hostname == "SW-TEST-01"

    def test_intent_has_vlans(self):
        intent = make_intent()
        assert any(v.vlan_id == 20 for v in intent.vlans)

    def test_feature_selection_defaults(self):
        fs = FeatureSelection()
        assert fs.base_config is True
        assert fs.vlans is True
        assert fs.interfaces is True
        assert fs.acls is True
