from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml
from openpyxl import Workbook

from cisco_config_generator.orchestrator import Orchestrator
from cisco_config_generator.workbook.validators import ValidationError

DEFAULT_SITE_DATA: dict[str, object] = {
    "domain_name": "example.local",
    "ntp_servers": ["10.0.1.1", "10.0.1.2"],
    "dns_servers": ["10.0.1.5"],
    "syslog_server": ["10.0.1.30", "10.0.1.31"],
    "aaa_protocol": "tacacs+",
    "aaa_servers": ["10.0.1.40", "10.0.1.41"],
    "aaa_key": "EXAMPLE-tacacs-key",
    "local_username": "netadmin",
    "local_password": "EXAMPLE-local-password",
    "snmp_auth_protocol": "SHA",
    "snmp_priv_protocol": "AES",
    "snmp_ro_group": "SNMPv3_RO",
    "snmp_ro_user": "ro-user",
    "snmp_ro_auth_password": "authpass",
    "snmp_ro_priv_password": "privpass",
    "snmp_host": "10.0.1.20",
    "enable_secret": "EXAMPLE-enable-secret",
    "vty_acl": "ACL_VTY_ACCESS",
    "snmp_ro_acl": "ACL_SNMP_RO_ACCESS",
    "banner_motd": "TEST BANNER",
    "vlans": [
        {"vlan_id": 10, "vlan_name": "MGMT", "description": "Management VLAN"},
        {"vlan_id": 20, "vlan_name": "DATA", "description": "User Data VLAN"},
    ],
    "acls": [
        {"acl_name": "ACL_VTY_ACCESS", "remark": "Management subnet", "action": "permit", "network": "10.0.0.0", "wildcard": "0.0.0.255"},
        {"acl_name": "ACL_VTY_ACCESS", "remark": "Deny all others", "action": "deny", "network": "any"},
        {"acl_name": "ACL_SNMP_RO_ACCESS", "remark": "NMS subnet", "action": "permit", "network": "10.0.1.0", "wildcard": "0.0.0.255"},
        {"acl_name": "ACL_SNMP_RO_ACCESS", "remark": "Deny all others", "action": "deny", "network": "any"},
    ],
}


def _write_site(sites_dir: Path, site_name: str, overrides: list[tuple[str, object]] | None = None) -> None:
    sites_dir.mkdir(parents=True, exist_ok=True)
    data = dict(DEFAULT_SITE_DATA)
    for key, value in overrides or []:
        data[key] = value
    (sites_dir / f"{site_name}.yaml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _create_test_workbook(
    path: Path,
    *,
    model: str = "C9200-48P",
    uplink_module: str = "NM-4X",
    interface_rows: list[list[object]] | None = None,
    port_channel_rows: list[list[object]] | None = None,
    global_overrides: list[tuple[str, object]] | None = None,
    features: list[tuple[str, str]] | None = None,
    site_name: str = "test-site",
    sites_dir: Path | None = None,
    timezone: object = "CET",
    timezone_hours: object = 1,
    timezone_minutes: object = 0,
) -> None:
    """Build a minimal intent workbook plus its matching sites/<site_name>.yaml.

    ``sites_dir`` defaults to ``path.parent / "sites"`` — pass that same
    directory as Orchestrator(sites_dir=...) in the test.
    """
    wb = Workbook()

    devices_ws = wb.active
    devices_ws.title = "Devices"
    devices_ws.append(
        [
            "Hostname",
            "Mgmt IP",
            "Mgmt VLAN",
            "Default Gateway",
            "Model",
            "Uplink Module",
            "Site",
            "Timezone",
            "Timezone Hours",
            "Timezone Minutes",
            "Mgmt Subnet",
        ]
    )
    devices_ws.append(
        [
            "SW-TEST-01",
            "10.0.10.2",
            10,
            "10.0.10.1",
            model,
            uplink_module,
            site_name,
            timezone,
            timezone_hours,
            timezone_minutes,
            "255.255.255.0",
        ]
    )

    interfaces_ws = wb.create_sheet("Interfaces")
    interfaces_ws.append(
        [
            "Device Name",
            "Interface Name",
            "Port Profile",
            "Description",
            "Access VLAN",
            "Voice VLAN",
            "Native VLAN",
            "Allowed VLANs",
            "Storm Control Broadcast",
            "Storm Control Multicast",
            "Port Channel No.",
        ]
    )
    rows = interface_rows or [
        [
            "SW-TEST-01",
            "GigabitEthernet1/0/1",
            "access-user",
            "Client Port",
            20,
            "",
            "",
            "",
            "",
            "",
            "",
        ],
        [
            "SW-TEST-01",
            "TenGigabitEthernet1/1/1",
            "trunk-uplink-portchannel",
            "Uplink to Core",
            "",
            "",
            10,
            "10,20",
            "1.00 0.70",
            "1.00 0.70",
            1,
        ],
        [
            "SW-TEST-01",
            "TenGigabitEthernet1/1/2",
            "trunk-uplink-portchannel",
            "Uplink to Core",
            "",
            "",
            10,
            "10,20",
            "1.00 0.70",
            "1.00 0.70",
            1,
        ],
    ]
    for row in rows:
        interfaces_ws.append(row)

    port_channels_ws = wb.create_sheet("Port-Channels")
    port_channels_ws.append([
        "Device Name",
        "Port Channel No.",
        "Description",
        "Native VLAN",
        "Allowed VLANs",
        "Storm Control Broadcast",
        "Storm Control Multicast",
    ])
    # Empty by default: the default interface rows derive Po1 from its members.
    for row in port_channel_rows or []:
        port_channels_ws.append(row)

    features_ws = wb.create_sheet("Feature Selection")
    features_ws.append(["Feature", "Enabled", "Description"])
    for name, enabled in features or [
        ("base_config", "Yes"),
        ("vlans", "Yes"),
        ("interfaces", "Yes"),
        ("acls", "Yes"),
    ]:
        features_ws.append([name, enabled, ""])

    wb.save(path)

    _write_site(sites_dir or path.parent / "sites", site_name, global_overrides)


class TestOrchestratorIntegration:
    def test_orchestrator_renders_full_config_from_workbook(self):
        repo_root = Path(__file__).resolve().parents[1]
        pack_path = repo_root / "packs" / "default"

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            workbook_path = tmp_path / "intent.xlsx"
            output_dir = tmp_path / "output"
            _create_test_workbook(workbook_path)

            orchestrator = Orchestrator(
                pack_path=pack_path,
                workbook_path=workbook_path,
                output_dir=output_dir,
                sites_dir=tmp_path / "sites",
            )

            written = orchestrator.run()

            assert len(written) == 1
            output_path = written[0]
            assert output_path.exists()
            assert output_path.name == "SW-TEST-01.cfg"

            config = output_path.read_text()

            assert "ip access-list standard ACL_VTY_ACCESS" in config
            assert "permit 10.0.0.0 0.0.0.255" in config
            assert "hostname SW-TEST-01" in config
            assert "clock timezone CET 1 0" in config
            assert "snmp-server group SNMPv3_RO v3 priv read VIEWALL access ACL_SNMP_RO_ACCESS" in config
            assert "snmp-server host 10.0.1.20 version 3 priv ro-user" in config
            assert "access-class ACL_VTY_ACCESS in vrf-also" in config
            assert "vlan 20" in config
            assert "interface GigabitEthernet1/0/1" in config
            assert "switchport access vlan 20" in config
            assert "interface Port-channel1" in config
            assert config.count("interface Port-channel1") == 1
            assert "switchport trunk allowed vlan 10,20" in config
            assert config.count("storm-control broadcast level 1.00 0.70") == 4
            assert config.count("storm-control multicast level 1.00 0.70") == 4
            assert "storm-control broadcast level 0.10 0.07" not in config
            assert "storm-control multicast level 0.10 0.07" not in config
            assert "banner motd ^" in config
            # Section order must let the file be pasted top to bottom without
            # forward references: ACLs before the lines that apply them, VLANs
            # before the management SVI, and the Port-channel before the
            # members that join it.
            assert config.index("ip access-list standard ACL_VTY_ACCESS") < config.index("access-class ACL_VTY_ACCESS in vrf-also")
            assert config.index("vlan 10") < config.index("interface Vlan10")
            assert config.index("interface Port-channel1") < config.index("channel-group 1 mode active")
            assert config.index("hostname SW-TEST-01") < config.index("interface GigabitEthernet1/0/1")

    def test_orchestrator_derives_missing_interfaces_from_selected_hardware(self):
        repo_root = Path(__file__).resolve().parents[1]
        pack_path = repo_root / "packs" / "default"

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            workbook_path = tmp_path / "intent.xlsx"
            output_dir = tmp_path / "output"
            _create_test_workbook(
                workbook_path,
                model="C9200-24P",
                uplink_module="NM-4X",
                interface_rows=[
                    [
                        "SW-TEST-01",
                        "GigabitEthernet1/0/1",
                        "access-user",
                        "Client Port",
                        20,
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                    ],
                ],
            )

            orchestrator = Orchestrator(
                pack_path=pack_path,
                workbook_path=workbook_path,
                output_dir=output_dir,
                sites_dir=tmp_path / "sites",
            )

            written = orchestrator.run()

            assert len(written) == 1
            config = written[0].read_text()

            assert "interface GigabitEthernet1/0/1" in config
            assert "switchport access vlan 20" in config
            assert config.count("default interface ") == 27
            assert "default interface GigabitEthernet1/0/2" in config
            assert "default interface GigabitEthernet1/0/24" in config
            assert "default interface TenGigabitEthernet1/1/1" in config
            assert "default interface TenGigabitEthernet1/1/4" in config
            assert "default interface GigabitEthernet1/0/25" not in config

    def test_orchestrator_reports_unknown_site_as_a_validation_error(self):
        repo_root = Path(__file__).resolve().parents[1]
        pack_path = repo_root / "packs" / "default"

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            workbook_path = tmp_path / "intent.xlsx"
            _create_test_workbook(workbook_path, site_name="ghost-site")
            # Only write the workbook's referenced site under a *different* name,
            # so "ghost-site" is never actually created.
            (tmp_path / "sites" / "ghost-site.yaml").unlink()

            orchestrator = Orchestrator(
                pack_path=pack_path,
                workbook_path=workbook_path,
                output_dir=tmp_path / "output",
                sites_dir=tmp_path / "sites",
            )
            with pytest.raises(ValidationError, match="ghost-site"):
                orchestrator.run()



class TestPortChannelsSheet:
    """A filled-in Port-Channels sheet now reaches the rendered config."""

    def _run(self, tmp_path: Path, port_channel_rows: list[list[object]]) -> str:
        workbook_path = tmp_path / "intent.xlsx"
        _create_test_workbook(workbook_path, port_channel_rows=port_channel_rows)
        orchestrator = Orchestrator(
            pack_path=Path(__file__).resolve().parents[1] / "packs" / "default",
            workbook_path=workbook_path,
            output_dir=tmp_path / "output",
            sites_dir=tmp_path / "sites",
        )
        return orchestrator.run()[0].read_text()

    def test_override_is_rendered_on_the_port_channel_only(self, tmp_path):
        config = self._run(tmp_path, [["SW-TEST-01", 1, "Core bundle", None, "10,20,30", None, None]])
        port_channel = config.split("interface Port-channel1\n", 1)[1].split("!", 1)[0]
        assert " description Core bundle" in port_channel
        assert " switchport trunk allowed vlan 10,20,30" in port_channel
        assert " switchport trunk native vlan 10" in port_channel  # inherited from the members
        # The member ports keep their own values.
        member = config.split("interface TenGigabitEthernet1/1/1\n", 1)[1].split("!", 1)[0]
        assert " description Uplink to Core" in member

    def test_row_without_members_stops_the_run(self, tmp_path):
        with pytest.raises(ValidationError, match="Port-channel 9 on 'SW-TEST-01' has no member interfaces"):
            self._run(tmp_path, [["SW-TEST-01", 9, "Orphan", None, None, None, None]])

    def test_row_for_an_unknown_device_stops_the_run(self, tmp_path):
        """What a workbook copied from an older template, with its example rows still in, now reports."""
        with pytest.raises(ValidationError, match="references unknown device 'SW-OFFICE-01'"):
            self._run(tmp_path, [["SW-OFFICE-01", 1, "Uplink to Core - Po1", 10, "10,20,30", "1.00 0.70", "1.00 0.70"]])

    def test_duplicate_rows_stop_the_run(self, tmp_path):
        with pytest.raises(ValidationError, match="Duplicate Port-channel 1 on device 'SW-TEST-01'"):
            self._run(tmp_path, [
                ["SW-TEST-01", 1, "First", None, None, None, None],
                ["SW-TEST-01", 1, "Second", None, None, None, None],
            ])

class TestSiteAwareRendering:
    """Coverage for the core site-aware behaviour: one workbook, devices split
    across different sites/<name>.yaml files, each supplying its own
    NTP/DNS/SNMP/AAA/banner, VLANs and ACLs."""

    def _build_two_site_workbook(self, tmp_path: Path) -> Path:
        workbook_path = tmp_path / "intent.xlsx"
        wb = Workbook()

        devices_ws = wb.active
        devices_ws.title = "Devices"
        devices_ws.append(
            ["Hostname", "Mgmt IP", "Mgmt VLAN", "Default Gateway", "Model", "Uplink Module",
             "Site", "Timezone", "Timezone Hours", "Timezone Minutes", "Mgmt Subnet"]
        )
        devices_ws.append(["SW-SITE-A-01", "10.0.10.2", 10, "10.0.10.1", "C9200-48P", "NM-4X",
                            "site-alpha", "", "", "", ""])
        devices_ws.append(["SW-SITE-B-01", "10.0.20.2", 10, "10.0.20.1", "C9200-48P", "NM-4X",
                            "site-beta", "", "", "", ""])

        interfaces_ws = wb.create_sheet("Interfaces")
        interfaces_ws.append(
            ["Device Name", "Interface Name", "Port Profile", "Description", "Access VLAN",
             "Voice VLAN", "Native VLAN", "Allowed VLANs", "Storm Control Broadcast",
             "Storm Control Multicast", "Port Channel No."]
        )
        interfaces_ws.append(["SW-SITE-A-01", "GigabitEthernet1/0/1", "access-user", "PC", 20,
                               "", "", "", "", "", ""])
        interfaces_ws.append(["SW-SITE-B-01", "GigabitEthernet1/0/1", "access-user", "PC", 200,
                               "", "", "", "", "", ""])

        features_ws = wb.create_sheet("Feature Selection")
        features_ws.append(["Feature", "Enabled", "Description"])
        for name in ("base_config", "vlans", "interfaces", "acls"):
            features_ws.append([name, "Yes", ""])

        wb.save(workbook_path)

        sites_dir = tmp_path / "sites"
        _write_site(sites_dir, "site-alpha", [
            ("timezone", "GMT"),
            ("banner_motd", "SITE ALPHA BANNER"),
            ("vlans", [{"vlan_id": 10, "vlan_name": "MGMT"}, {"vlan_id": 20, "vlan_name": "DATA"}]),
        ])
        _write_site(sites_dir, "site-beta", [
            ("timezone", "CET"),
            ("banner_motd", "SITE BETA BANNER"),
            ("vlans", [{"vlan_id": 10, "vlan_name": "MGMT"}, {"vlan_id": 200, "vlan_name": "GUEST"}]),
        ])
        return workbook_path

    def test_each_device_renders_with_its_own_sites_vlans_and_banner(self, tmp_path):
        repo_root = Path(__file__).resolve().parents[1]
        pack_path = repo_root / "packs" / "default"
        workbook_path = self._build_two_site_workbook(tmp_path)

        orchestrator = Orchestrator(
            pack_path=pack_path,
            workbook_path=workbook_path,
            output_dir=tmp_path / "output",
            sites_dir=tmp_path / "sites",
        )
        written = {p.stem: p.read_text() for p in orchestrator.run()}

        assert "SITE ALPHA BANNER" in written["SW-SITE-A-01"]
        assert "SITE BETA BANNER" not in written["SW-SITE-A-01"]
        assert "vlan 20\n" in written["SW-SITE-A-01"]
        assert "vlan 200\n" not in written["SW-SITE-A-01"]

        assert "SITE BETA BANNER" in written["SW-SITE-B-01"]
        assert "SITE ALPHA BANNER" not in written["SW-SITE-B-01"]
        assert "vlan 200\n" in written["SW-SITE-B-01"]
        assert "vlan 20\n" not in written["SW-SITE-B-01"]

    def test_blank_timezone_and_mgmt_subnet_inherit_from_the_site(self, tmp_path):
        repo_root = Path(__file__).resolve().parents[1]
        pack_path = repo_root / "packs" / "default"
        workbook_path = self._build_two_site_workbook(tmp_path)

        orchestrator = Orchestrator(
            pack_path=pack_path,
            workbook_path=workbook_path,
            output_dir=tmp_path / "output",
            sites_dir=tmp_path / "sites",
        )
        written = {p.stem: p.read_text() for p in orchestrator.run()}

        # Neither device sets Timezone/Mgmt Subnet in the workbook - each
        # inherits its own site's value.
        assert "clock timezone GMT 0 0" in written["SW-SITE-A-01"]
        assert "clock timezone CET 0 0" in written["SW-SITE-B-01"]
        assert "ip address 10.0.10.2 255.255.255.0" in written["SW-SITE-A-01"]

    def test_blank_timezone_falls_back_to_pack_default_when_site_omits_it(self, tmp_path):
        repo_root = Path(__file__).resolve().parents[1]
        pack_path = repo_root / "packs" / "default"
        workbook_path = tmp_path / "intent.xlsx"
        _create_test_workbook(
            workbook_path,
            interface_rows=[["SW-TEST-01", "GigabitEthernet1/0/1", "access-user", "PC", 20,
                              "", "", "", "", "", ""]],
            timezone="", timezone_hours="", timezone_minutes="",
        )
        # DEFAULT_SITE_DATA has no 'timezone' key, so the pack's "GMT" default applies.
        orchestrator = Orchestrator(
            pack_path=pack_path,
            workbook_path=workbook_path,
            output_dir=tmp_path / "output",
            sites_dir=tmp_path / "sites",
        )
        config = orchestrator.run()[0].read_text()
        assert "clock timezone GMT 0 0" in config
