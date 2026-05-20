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
