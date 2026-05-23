from __future__ import annotations

import tempfile
import os
from pathlib import Path

import pytest
from jinja2 import Environment, DictLoader

from cisco_config_generator.rendering.engine import create_jinja_env, render_template
from cisco_config_generator.rendering.registry import TemplateRegistry
from cisco_config_generator.rendering.writers import write_config
from cisco_config_generator.workbook.models import ACLEntry, Device, VLAN, Interface, GlobalSettings


class TestEngine:
    def test_render_simple_template(self):
        env = Environment(loader=DictLoader({"test.j2": "hostname {{ device.hostname }}"}))
        device = Device(
            hostname="SW-01",
            mgmt_ip="10.0.0.1",
            mgmt_vlan=1,
            default_gateway="10.0.0.254",
            model="C9200-48P",
            uplink_module="NM-4X",
        )
        result = render_template(env, "test.j2", {"device": device})
        assert result == "hostname SW-01"

    def test_render_vlan_list(self):
        env = Environment(
            loader=DictLoader({"vlans.j2": "{% for v in vlans %}vlan {{ v.vlan_id }}\n{% endfor %}"}),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        vlans = [VLAN(10, "MGMT"), VLAN(20, "DATA")]
        result = render_template(env, "vlans.j2", {"vlans": vlans})
        assert "vlan 10" in result
        assert "vlan 20" in result

    def test_render_acl_template(self):
        templates_dir = Path(__file__).resolve().parents[1] / "packs" / "default" / "templates"
        env = create_jinja_env(templates_dir)
        acls = [
            ACLEntry("ACL_VTY_ACCESS", "Management network", "permit", "10.0.0.0", "0.0.0.255"),
            ACLEntry("ACL_VTY_ACCESS", "Deny all others", "deny", "any", ""),
        ]
        result = render_template(env, "acls.j2", {"acls": acls})
        assert "ip access-list standard ACL_VTY_ACCESS" in result
        assert "remark Management network" in result
        assert "permit 10.0.0.0 0.0.0.255" in result
        assert "deny any" in result

    def test_render_tengig_portchannel_template(self):
        templates_dir = Path(__file__).resolve().parents[1] / "packs" / "default" / "templates"
        env = create_jinja_env(templates_dir)
        interfaces = [
            Interface(
                device_name="SW-01",
                interface_name="TenGigabitEthernet1/1/1",
                port_profile="trunk-uplink-portchannel",
                description="Uplink to Core",
                native_vlan=99,
                allowed_vlans="10,20,99",
                port_channel_number=1,
                template_hint="interfaces_trunk_portchannel",
            ),
            Interface(
                device_name="SW-01",
                interface_name="TenGigabitEthernet1/1/2",
                port_profile="trunk-uplink-portchannel",
                description="Uplink to Core",
                native_vlan=99,
                allowed_vlans="10,20,99",
                port_channel_number=1,
                template_hint="interfaces_trunk_portchannel",
            ),
        ]

        result = render_template(
            env,
            "interfaces_trunk_portchannel.j2",
            {"interfaces": interfaces, "settings": {"defaults": {"native_vlan": 1}}},
        )

        assert "interface Port-channel1" in result
        assert "switchport trunk allowed vlan 10,20,99" in result
        assert "switchport trunk native vlan 99" in result
        assert result.count("storm-control broadcast level 0.10 0.07") == 3
        assert result.count("storm-control multicast level 0.10 0.07") == 3
        assert "interface Port-channel1\n description Uplink to Core\n switchport mode trunk\n switchport trunk allowed vlan 10,20,99\n switchport trunk native vlan 99\n switchport nonegotiate\n load-interval 30\n storm-control broadcast level 0.10 0.07\n storm-control multicast level 0.10 0.07\n ip dhcp snooping trust\n!" in result

    def test_render_gig_portchannel_template(self):
        templates_dir = Path(__file__).resolve().parents[1] / "packs" / "default" / "templates"
        env = create_jinja_env(templates_dir)
        interfaces = [
            Interface(
                device_name="SW-01",
                interface_name="GigabitEthernet1/0/47",
                port_profile="trunk-uplink-portchannel",
                description="Server Uplink",
                native_vlan=99,
                allowed_vlans="all",
                port_channel_number=7,
                template_hint="interfaces_trunk_portchannel",
            ),
            Interface(
                device_name="SW-01",
                interface_name="GigabitEthernet1/0/48",
                port_profile="trunk-uplink-portchannel",
                description="Server Uplink",
                native_vlan=99,
                allowed_vlans="all",
                port_channel_number=7,
                template_hint="interfaces_trunk_portchannel",
            ),
        ]

        result = render_template(
            env,
            "interfaces_trunk_portchannel.j2",
            {"interfaces": interfaces, "settings": {"defaults": {"native_vlan": 1}}},
        )

        assert "interface Port-channel7" in result
        assert result.count("storm-control broadcast level 1.00 0.70") == 3
        assert result.count("storm-control multicast level 1.00 0.70") == 3
        assert "no shutdown\n!\ninterface Port-channel7" in result

    def test_render_custom_storm_control_override(self):
        templates_dir = Path(__file__).resolve().parents[1] / "packs" / "default" / "templates"
        env = create_jinja_env(templates_dir)
        interfaces = [
            Interface(
                device_name="SW-01",
                interface_name="TenGigabitEthernet1/1/1",
                port_profile="trunk-uplink-portchannel",
                description="Uplink to Core",
                native_vlan=99,
                allowed_vlans="10,20,99",
                storm_control_broadcast="1.00 0.70",
                storm_control_multicast="1.00 0.70",
                port_channel_number=1,
                template_hint="interfaces_trunk_portchannel",
            ),
            Interface(
                device_name="SW-01",
                interface_name="TenGigabitEthernet1/1/2",
                port_profile="trunk-uplink-portchannel",
                description="Uplink to Core",
                native_vlan=99,
                allowed_vlans="10,20,99",
                storm_control_broadcast="1.00 0.70",
                storm_control_multicast="1.00 0.70",
                port_channel_number=1,
                template_hint="interfaces_trunk_portchannel",
            ),
        ]

        result = render_template(
            env,
            "interfaces_trunk_portchannel.j2",
            {"interfaces": interfaces, "settings": {"defaults": {"native_vlan": 1}}},
        )

        assert result.count("storm-control broadcast level 1.00 0.70") == 3
        assert result.count("storm-control multicast level 1.00 0.70") == 3
        assert "storm-control broadcast level 0.10 0.07" not in result
        assert "storm-control multicast level 0.10 0.07" not in result


class TestRegistry:
    def test_resolve_known_hint(self):
        template_map = {
            "interfaces_access": {"template": "interfaces_access.j2", "order": 30}
        }
        registry = TemplateRegistry(template_map=template_map, templates_dir=Path("."))
        tmpl, order = registry.resolve("interfaces_access")
        assert tmpl == "interfaces_access.j2"
        assert order == 30

    def test_resolve_unknown_hint_raises(self):
        registry = TemplateRegistry(template_map={}, templates_dir=Path("."))
        with pytest.raises(KeyError):
            registry.resolve("does-not-exist")


class TestWriters:
    def test_write_config_creates_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = write_config(tmpdir, "SW-TEST-01", "hostname SW-TEST-01\n")
            assert path.exists()
            assert path.read_text() == "hostname SW-TEST-01\n"

    def test_write_config_filename(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = write_config(tmpdir, "MY-SWITCH", "content")
            assert path.name == "MY-SWITCH.cfg"

    def test_write_config_strips_path_traversal(self):
        """Hostnames with path separators should be sanitised — output stays in the chosen directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = write_config(tmpdir, "../escaped", "content")
            assert path.parent.resolve() == Path(tmpdir).resolve()
            assert path.name == "escaped.cfg"

    def test_write_config_strips_subdirectory_component(self):
        """A hostname like 'subdir/switch-01' should write switch-01.cfg inside the output dir."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = write_config(tmpdir, "subdir/switch-01", "content")
            assert path.name == "switch-01.cfg"
            assert path.parent.resolve() == Path(tmpdir).resolve()
