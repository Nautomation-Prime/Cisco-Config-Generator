from __future__ import annotations

import pytest
from cisco_config_generator.workbook.models import (
    ACLEntry, Device, VLAN, Interface, PortChannel, GlobalSettings, FeatureSelection, Intent, Site
)


def make_device(**kwargs) -> Device:
    defaults = dict(
        hostname="SW-TEST-01",
        mgmt_ip="10.0.10.2",
        mgmt_vlan=10,
        default_gateway="10.0.10.1",
        model="C9200-48P",
        uplink_module="NM-4X",
        site="TESTSITE",
    )
    defaults.update(kwargs)
    return Device(**defaults)


def make_vlan(vlan_id=10, vlan_name="MGMT") -> VLAN:
    return VLAN(vlan_id=vlan_id, vlan_name=vlan_name)


def make_site(**kwargs) -> Site:
    """A default site, keyed 'TESTSITE' by callers, matching make_device()'s default site."""
    defaults = dict(
        name="TESTSITE",
        global_settings=GlobalSettings(enable_secret="EXAMPLE-enable-secret"),
        vlans=[make_vlan(10, "MGMT"), make_vlan(20, "DATA")],
        acls=[
            ACLEntry(
                acl_name="ACL_VTY_ACCESS",
                action="permit",
                network="10.0.0.0",
                wildcard="0.0.0.255",
            )
        ],
    )
    defaults.update(kwargs)
    return Site(**defaults)


def make_intent(**kwargs) -> Intent:
    intent = Intent(
        devices=[make_device()],
        interfaces=[
            Interface(
                device_name="SW-TEST-01",
                interface_name="GigabitEthernet1/0/1",
                port_profile="access-user",
                access_vlan=20,
                template_hint="interfaces_access",
            )
        ],
        feature_selection=FeatureSelection(),
    )
    for k, v in kwargs.items():
        setattr(intent, k, v)
    return intent


class TestDeviceModel:
    def test_device_defaults(self):
        """Blank Timezone / Mgmt Subnet are filled later, from the site and then the pack."""
        d = make_device()
        assert d.timezone == ""
        assert d.timezone_hours_offset == 0
        assert d.timezone_minutes_offset == 0
        assert d.mgmt_subnet == ""

    def test_device_required_fields(self):
        d = make_device(hostname="SW-01")
        assert d.hostname == "SW-01"


class TestVLANModel:
    def test_vlan_id(self):
        v = make_vlan(100, "SERVERS")
        assert v.vlan_id == 100
        assert v.vlan_name == "SERVERS"


class TestSiteModel:
    def test_site_has_vlans_and_acls(self):
        site = make_site()
        assert any(v.vlan_id == 20 for v in site.vlans)
        assert site.acls[0].acl_name == "ACL_VTY_ACCESS"

    def test_site_defaults(self):
        site = Site(name="EMPTY")
        assert site.vlans == []
        assert site.acls == []
        assert site.timezone == ""
        assert site.mgmt_subnet == ""


class TestIntentModel:
    def test_intent_has_devices(self):
        intent = make_intent()
        assert len(intent.devices) == 1
        assert intent.devices[0].hostname == "SW-TEST-01"

    def test_feature_selection_defaults(self):
        fs = FeatureSelection()
        assert fs.base_config is True
        assert fs.vlans is True
        assert fs.interfaces is True
        assert fs.acls is True


# ---------------------------------------------------------------------------
# Loading a real workbook: every problem, with its sheet, row and column
# ---------------------------------------------------------------------------
from pathlib import Path

import openpyxl

from cisco_config_generator.pack_loader import load_pack
from cisco_config_generator.workbook.loader import load_workbook
from cisco_config_generator.workbook.validators import ValidationError
from tests.test_orchestrator_integration import _create_test_workbook

PACK = load_pack(str(Path(__file__).resolve().parents[1] / "packs" / "default"))


def _load(path: Path):
    return load_workbook(
        path,
        port_profiles=PACK.port_profiles,
        hardware_catalog=PACK.hardware_catalog,
        uplink_modules=PACK.uplink_modules,
    )


def _workbook(tmp_path: Path, edits: dict[tuple[str, str], object] | None = None, **kwargs) -> Path:
    """The standard test workbook, with {(sheet, cell): value} overwritten."""
    path = tmp_path / "intent.xlsx"
    _create_test_workbook(path, **kwargs)
    if edits:
        wb = openpyxl.load_workbook(path)
        for (sheet, cell), value in edits.items():
            wb[sheet][cell] = value
        wb.save(path)
    return path


def _load_errors(path: Path) -> list[str]:
    with pytest.raises(ValidationError) as exc_info:
        _load(path)
    return exc_info.value.errors


class TestWorkbookLoading:
    def test_standard_workbook_loads(self, tmp_path):
        intent = _load(_workbook(tmp_path))
        assert intent.devices[0].hostname == "SW-TEST-01"
        assert intent.devices[0].site == "test-site"

    def test_errors_name_the_sheet_row_and_column(self, tmp_path):
        path = _workbook(tmp_path, {("Devices", "B2"): "10.0.10.999"})
        assert _load_errors(path) == [
            "Sheet 'Devices', row 2, column 'Mgmt IP': '10.0.10.999' is not a valid IPv4 address."
        ]

    def test_every_problem_across_sheets_is_reported_at_once(self, tmp_path):
        """The old loader stopped at the first bad number."""
        path = _workbook(tmp_path, {
            ("Devices", "C2"): "ten",
            ("Devices", "I2"): 30,
            ("Interfaces", "E2"): "twenty",
            ("Interfaces", "I3"): "high",
        })
        assert _load_errors(path) == [
            "Sheet 'Devices', row 2, column 'Mgmt VLAN' expected a whole number, got 'ten'.",
            "Sheet 'Devices', row 2, column 'Timezone Hours': Timezone hours offset 30 is out of range. "
            "Valid range: -23 to 23.",
            "Sheet 'Interfaces', row 2, column 'Access VLAN' expected a whole number, got 'twenty'.",
            "Sheet 'Interfaces', row 3, column 'Storm Control Broadcast': 'high' must contain two "
            "numeric values (rising and falling), for example '1.00 0.70'.",
        ]

    def test_misspelt_feature_is_reported(self, tmp_path):
        path = _workbook(tmp_path, features=[("base_config", "Yes"), ("acl", "Yes")])
        assert _load_errors(path) == [
            "Sheet 'Feature Selection', feature 'acl' is not a recognised feature. "
            "Did you mean 'acls'? Check the spelling, or remove it."
        ]

    def test_blank_feature_flag_is_reported_rather_than_read_as_no(self, tmp_path):
        path = _workbook(tmp_path, features=[("base_config", "Yes"), ("acls", "")])
        assert _load_errors(path) == [
            "Sheet 'Feature Selection', feature 'acls' expected Yes/No (or true/false), got ''."
        ]

    def test_allowed_vlans_typed_with_spaces_render_without_them(self, tmp_path):
        path = _workbook(tmp_path, {("Interfaces", "H3"): "10, 20"})
        trunk = next(i for i in _load(path).interfaces if i.interface_name == "TenGigabitEthernet1/1/1")
        assert trunk.allowed_vlans == "10,20"

    def test_blank_device_cells_stay_blank_until_the_site_is_known(self, tmp_path):
        path = _workbook(tmp_path, {("Devices", "H2"): None, ("Devices", "K2"): None})
        device = _load(path).devices[0]
        assert device.timezone == ""
        assert device.mgmt_subnet == ""

    def test_missing_required_cell_is_reported(self, tmp_path):
        path = _workbook(tmp_path, {("Devices", "E2"): None})
        assert _load_errors(path) == ["Sheet 'Devices', row 2, column 'Model' is required."]


class TestPortChannelsSheet:
    """The sheet used to be looked up as 'port channels' and never found."""

    TRUNK = ["SW-TEST-01", "", "trunk-uplink-portchannel", "Uplink", "", "", 10, "10,20", "", "", 0]

    def _trunk(self, interface: str, po: int) -> list[object]:
        row = list(self.TRUNK)
        row[1], row[10] = interface, po
        return row

    def _port_channels(self, tmp_path, rows, **kwargs):
        return {pc.port_channel_number: pc for pc in _load(_workbook(tmp_path, port_channel_rows=rows, **kwargs)).port_channels}

    def test_row_overrides_only_the_cells_it_fills_in(self, tmp_path):
        pcs = self._port_channels(tmp_path, [["SW-TEST-01", 1, "Core bundle", None, "10,20,30", None, None]])
        assert pcs[1].description == "Core bundle"
        assert pcs[1].allowed_vlans == "10,20,30"
        # Blank cells keep the members' values.
        assert pcs[1].native_vlan == 10
        assert pcs[1].storm_control_broadcast == "1.00 0.70"

    def test_port_channels_without_a_row_are_still_derived(self, tmp_path):
        pcs = self._port_channels(
            tmp_path,
            [["SW-TEST-01", 2, "Server bundle", None, None, None, None]],
            interface_rows=[
                self._trunk("TenGigabitEthernet1/1/1", 1),
                self._trunk("TenGigabitEthernet1/1/2", 1),
                self._trunk("TenGigabitEthernet1/1/3", 2),
                self._trunk("TenGigabitEthernet1/1/4", 2),
            ],
        )
        assert sorted(pcs) == [1, 2]
        assert pcs[1].description == "Uplink"
        assert pcs[2].description == "Server bundle"

    def test_sheet_is_found_under_other_spellings(self, tmp_path):
        path = _workbook(tmp_path, port_channel_rows=[["SW-TEST-01", 1, "Core bundle", None, None, None, None]])
        wb = openpyxl.load_workbook(path)
        wb["Port-Channels"].title = "port_channels"
        wb.save(path)
        assert _load(path).port_channels[0].description == "Core bundle"

    def test_bad_cell_is_reported_with_its_location(self, tmp_path):
        path = _workbook(tmp_path, port_channel_rows=[["SW-TEST-01", 1, None, None, "10;20", None, None]])
        errors = _load_errors(path)
        assert len(errors) == 1
        assert errors[0].startswith("Sheet 'Port-Channels', row 2, column 'Allowed VLANs'")

    def test_row_without_members_is_kept_for_validation(self, tmp_path):
        """validate_intent reports it - the loader must not drop it."""
        pcs = self._port_channels(tmp_path, [["SW-TEST-01", 9, "Orphan", None, None, None, None]])
        assert sorted(pcs) == [1, 9]

    def test_duplicate_rows_are_kept_for_validation(self, tmp_path):
        path = _workbook(tmp_path, port_channel_rows=[
            ["SW-TEST-01", 1, "First", None, None, None, None],
            ["SW-TEST-01", 1, "Second", None, None, None, None],
        ])
        port_channels = _load(path).port_channels
        assert [pc.description for pc in port_channels] == ["First", "Second"]

    def test_instruction_row_with_blank_device_name_is_skipped(self, tmp_path):
        path = _workbook(tmp_path, port_channel_rows=[[None, "OPTIONAL: notes for the reader", None, None, None, None, None]])
        assert [pc.description for pc in _load(path).port_channels] == ["Uplink to Core"]
