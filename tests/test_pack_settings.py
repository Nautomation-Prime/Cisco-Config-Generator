"""Tests for pack policy settings and the IOS grammar they drive."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from cisco_config_generator.orchestrator import Orchestrator
from cisco_config_generator.pack_loader import InvalidPackError, load_pack
from cisco_config_generator.pack_schema import PackDefaults
from cisco_config_generator.rendering.engine import create_jinja_env, render_template
from cisco_config_generator.rendering.filters import cisco_secret, is_hashed_secret
from tests.test_orchestrator_integration import _create_test_workbook

REPO_ROOT = Path(__file__).resolve().parents[1]
PACK_PATH = REPO_ROOT / "packs" / "default"
TEMPLATES_DIR = PACK_PATH / "templates"


def _render(model: str = "C9200-48P", uplink_module: str = "NM-4X", **workbook_kwargs) -> str:
    """Render a single-device config through the full pipeline and return the text."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        workbook_path = tmp_path / "intent.xlsx"
        _create_test_workbook(workbook_path, model=model, uplink_module=uplink_module, **workbook_kwargs)
        orchestrator = Orchestrator(
            pack_path=PACK_PATH,
            workbook_path=workbook_path,
            output_dir=tmp_path / "output",
            sites_dir=tmp_path / "sites",
        )
        return orchestrator.run()[0].read_text()


class TestSecretFilter:
    def test_plaintext_is_hashed_by_the_switch(self):
        """'secret 9 <plaintext>' is rejected by IOS - hand it algorithm-type instead."""
        assert cisco_secret("MyPassw0rd", "scrypt") == "algorithm-type scrypt secret MyPassw0rd"

    def test_hash_type_is_configurable(self):
        assert cisco_secret("MyPassw0rd", "sha256") == "algorithm-type sha256 secret MyPassw0rd"
        assert cisco_secret("MyPassw0rd", "md5") == "algorithm-type md5 secret MyPassw0rd"

    def test_existing_hash_passes_through_with_its_own_type(self):
        assert cisco_secret("$9$saltsalt$hashhash", "scrypt") == "secret 9 $9$saltsalt$hashhash"
        assert cisco_secret("$8$saltsalt$hashhash", "scrypt") == "secret 8 $8$saltsalt$hashhash"
        assert cisco_secret("$1$salt$hash", "scrypt") == "secret 5 $1$salt$hash"

    def test_unknown_hash_type_raises(self):
        with pytest.raises(ValueError, match="password_hash_type"):
            cisco_secret("MyPassw0rd", "bcrypt")

    def test_is_hashed_secret(self):
        assert is_hashed_secret("$9$abc")
        assert not is_hashed_secret("MyPassw0rd")


class TestCredentialRendering:
    def test_plaintext_workbook_secret_renders_algorithm_type(self):
        config = _render()
        assert "enable algorithm-type scrypt secret EXAMPLE-enable-secret" in config
        assert "enable secret 9 EXAMPLE-enable-secret" not in config

    def test_aaa_key_type_defaults_to_plaintext(self):
        """key 7 expects an already-encrypted string; plaintext must go in as key 0."""
        from cisco_config_generator.workbook.models import GlobalSettings

        assert GlobalSettings().aaa_key_type == "0"


class TestPlatformGating:
    IOSXE_ONLY = [
        "no platform punt-keepalive disable-kernel-core",
        "vrf definition Mgmt-vrf",
        "no device-tracking logging theft",
        "boot system flash:packages.conf",
        "license boot level",
        "redundancy",
    ]

    def test_iosxe_only_commands_are_omitted_on_ios_classic(self):
        config = _render(model="C2960X-48FPS-L", uplink_module="NONE")
        leaked = [line for line in self.IOSXE_ONLY if line in config]
        assert leaked == [], f"IOS-XE-only commands emitted for a 2960-X: {leaked}"

    def test_iosxe_only_commands_are_present_on_catalyst_9000(self):
        config = _render(model="C9200-48P")
        for line in self.IOSXE_ONLY:
            assert line in config


class TestQosSettings:
    ACCESS_VOIP_ROW = [
        ["SW-TEST-01", "GigabitEthernet1/0/1", "access-voip", "Phone", 20, 10, "", "", "", "", ""]
    ]

    def test_no_global_qos_leaves_interface_trust_off_on_ios_classic(self):
        """'mls qos trust' is inert without global 'mls qos', so neither is emitted."""
        config = _render(
            model="C2960X-48FPS-L", uplink_module="NONE", interface_rows=self.ACCESS_VOIP_ROW
        )
        assert "mls qos" not in config

    def test_enabling_qos_emits_global_command_and_interface_trust(self, tmp_path):
        pack_path = _copy_pack_with_settings(tmp_path, {"qos_enabled": True})
        with tempfile.TemporaryDirectory() as tmpdir:
            workbook_path = Path(tmpdir) / "intent.xlsx"
            _create_test_workbook(
                workbook_path,
                model="C2960X-48FPS-L",
                uplink_module="NONE",
                interface_rows=self.ACCESS_VOIP_ROW,
            )
            config = Orchestrator(
                pack_path=pack_path,
                workbook_path=workbook_path,
                output_dir=Path(tmpdir) / "out",
                sites_dir=Path(tmpdir) / "sites",
            ).run()[0].read_text()
        assert "\nmls qos\n" in config
        assert " mls qos trust dscp" in config


class TestSettingsAreHonoured:
    def test_ntp_mode_default_is_client_mode(self):
        assert PackDefaults().ntp_mode == "server"
        config = _render()
        assert "ntp server " in config
        assert "ntp peer " not in config

    def test_ntp_mode_can_be_switched_to_peer(self, tmp_path):
        pack_path = _copy_pack_with_settings(tmp_path, {"ntp_mode": "peer"})
        with tempfile.TemporaryDirectory() as tmpdir:
            workbook_path = Path(tmpdir) / "intent.xlsx"
            _create_test_workbook(workbook_path)
            config = Orchestrator(
                pack_path=pack_path,
                workbook_path=workbook_path,
                output_dir=Path(tmpdir) / "out",
                sites_dir=Path(tmpdir) / "sites",
            ).run()[0].read_text()
        assert "ntp peer " in config

    def test_service_internal_is_off_by_default(self):
        assert PackDefaults().service_internal is False
        assert "service internal" not in _render()

    def test_crypto_key_generation_is_documented_not_configured(self):
        config = _render()
        assert "POST-APPLY STEP" in config
        assert "\ncrypto key generate rsa" not in config

    def test_ssh_macs_default_to_sha2(self):
        config = _render()
        assert "ip ssh server algorithm mac hmac-sha2-512 hmac-sha2-256" in config
        assert "hmac-sha1" not in config

    def test_storm_control_action_is_emitted(self):
        assert " storm-control action trap" in _render()

    def test_management_svi_sources_logging_ntp_and_snmp(self):
        config = _render()
        assert "logging source-interface Vlan10" in config
        assert "ntp source Vlan10" in config
        assert "snmp-server source-interface traps Vlan10" in config


class TestPackSettingsValidation:
    def test_shipped_pack_is_valid(self):
        load_pack(str(PACK_PATH))

    def test_invalid_choice_is_reported(self, tmp_path):
        pack_path = _copy_pack_with_settings(tmp_path, {"ntp_mode": "broadcast"})
        with pytest.raises(InvalidPackError, match=r"defaults\.ntp_mode is 'broadcast'\. Valid values: 'server' or 'peer'"):
            load_pack(str(pack_path))

    def test_pack_with_invalid_setting_fails_to_load(self, tmp_path):
        pack_path = _copy_pack_with_settings(tmp_path, {"password_hash_type": "bcrypt"})
        with pytest.raises(InvalidPackError, match="password_hash_type"):
            load_pack(str(pack_path))

    def test_pack_omitting_a_key_falls_back_to_the_built_in_default(self, tmp_path):
        """A settings.yaml written against an older schema must still render."""
        pack_path = tmp_path / "minimal-pack"
        _copy_tree(PACK_PATH, pack_path)
        (pack_path / "settings.yaml").write_text(
            'schema_version: "1.0"\nlog_level: INFO\nstrict_validation: true\n'
            "defaults:\n  unused_vlan: 999\n  native_vlan: 1\n",
            encoding="utf-8",
        )
        pack = load_pack(str(pack_path))
        assert pack.settings.ntp_mode == "server"
        assert pack.settings.storm_control_broadcast == "1.00 0.70"


class TestSyslogList:
    def test_each_syslog_server_gets_its_own_logging_host_line(self):
        templates_dir = TEMPLATES_DIR
        env = create_jinja_env(templates_dir)
        template = env.from_string(
            "{% for syslog in global.syslog_server %}logging host {{ syslog }}\n{% endfor %}"
        )
        from cisco_config_generator.workbook.models import GlobalSettings

        rendered = template.render(global_=None, **{
            "global": GlobalSettings(syslog_server=["10.0.0.1", "10.0.0.2"])
        })
        assert rendered == "logging host 10.0.0.1\nlogging host 10.0.0.2\n"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _copy_tree(src: Path, dst: Path) -> None:
    import shutil

    shutil.copytree(src, dst)


def _render_with_pack(pack_path: Path, **workbook_kwargs) -> str:
    """Render the standard test workbook against a specific pack."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workbook_path = Path(tmpdir) / "intent.xlsx"
        _create_test_workbook(workbook_path, **workbook_kwargs)
        return Orchestrator(
            pack_path=pack_path,
            workbook_path=workbook_path,
            output_dir=Path(tmpdir) / "out",
            sites_dir=Path(tmpdir) / "sites",
        ).run()[0].read_text()


def _merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base, so a test can change one nested key."""
    merged = dict(base)
    for key, value in override.items():
        if isinstance(merged.get(key), dict) and isinstance(value, dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _copy_pack_with_settings(tmp_path: Path, overrides: dict) -> Path:
    """Copy the default pack, overriding keys in its settings.yaml defaults block."""
    import yaml

    pack_path = tmp_path / "custom-pack"
    _copy_tree(PACK_PATH, pack_path)
    settings_file = pack_path / "settings.yaml"
    settings = yaml.safe_load(settings_file.read_text(encoding="utf-8"))
    settings["defaults"] = _merge(settings.get("defaults", {}), overrides)
    settings_file.write_text(yaml.safe_dump(settings, sort_keys=False), encoding="utf-8")
    return pack_path


class TestAaaPolicy:
    def test_default_method_lists_render(self):
        config = _render()
        assert "aaa new-model" in config
        assert "aaa group server tacacs+ TACACS_SERVERS" in config
        assert "aaa authentication login default group TACACS_SERVERS local" in config
        assert "aaa authentication enable default group TACACS_SERVERS enable" in config
        assert "aaa authorization exec default group TACACS_SERVERS local" in config
        assert "aaa authorization console" in config
        assert "aaa authorization commands 15 default group TACACS_SERVERS local" in config
        assert "aaa accounting exec default start-stop group TACACS_SERVERS" in config
        assert "aaa accounting commands 15 default start-stop group TACACS_SERVERS" in config
        assert "aaa session-id common" in config

    def test_every_server_in_the_list_is_rendered(self):
        """The old template capped out at two servers."""
        config = _render()
        assert " server-private 10.0.1.40 key 0 EXAMPLE-tacacs-key" in config
        assert " server-private 10.0.1.41 key 0 EXAMPLE-tacacs-key" in config
        assert " ip tacacs source-interface Vlan10" in config

    def test_command_authorization_can_be_turned_off(self, tmp_path):
        pack_path = _copy_pack_with_settings(
            tmp_path, {"aaa": {"authorization": {"commands": []}}}
        )
        config = _render_with_pack(pack_path)
        assert "aaa authorization commands" not in config
        # Sibling defaults survive the nested override.
        assert "aaa authorization exec default group TACACS_SERVERS local" in config

    def test_extra_privilege_levels_are_emitted(self, tmp_path):
        pack_path = _copy_pack_with_settings(
            tmp_path, {"aaa": {"authorization": {"commands": [1, 15]}}}
        )
        config = _render_with_pack(pack_path)
        assert "aaa authorization commands 1 default group TACACS_SERVERS local" in config
        assert "aaa authorization commands 15 default group TACACS_SERVERS local" in config

    def test_console_authorization_can_be_turned_off(self, tmp_path):
        pack_path = _copy_pack_with_settings(tmp_path, {"aaa": {"authorization_console": False}})
        assert "aaa authorization console" not in _render_with_pack(pack_path)

    def test_local_first_method_order_is_possible(self, tmp_path):
        pack_path = _copy_pack_with_settings(
            tmp_path, {"aaa": {"authentication": {"login": "local group {group}"}}}
        )
        assert "aaa authentication login default local group TACACS_SERVERS" in _render_with_pack(pack_path)

    def test_accounting_can_be_disabled_entirely(self, tmp_path):
        pack_path = _copy_pack_with_settings(
            tmp_path, {"aaa": {"accounting": {"exec": "", "commands": []}}}
        )
        assert "aaa accounting" not in _render_with_pack(pack_path)

    def test_radius_group_uses_radius_grammar(self, tmp_path):
        config = _render(global_overrides=[("aaa_protocol", "radius")])
        assert "aaa group server radius TACACS_SERVERS" in config
        assert "auth-port 1812 acct-port 1813" in config
        assert " ip radius source-interface Vlan10" in config

    def test_local_only_path_when_no_servers_defined(self):
        config = _render(global_overrides=[("aaa_servers", "")])
        assert "aaa new-model" in config
        assert "aaa group server" not in config
        assert "aaa authentication login default local" in config
        assert "aaa authorization exec default local if-authenticated" in config

    def test_method_list_without_a_fallback_is_refused(self, tmp_path):
        """No fallback means unreachable AAA servers lock everyone out."""
        pack_path = _copy_pack_with_settings(
            tmp_path, {"aaa": {"authorization": {"commands_methods": "group {group}"}}}
        )
        with pytest.raises(InvalidPackError, match="no fallback method"):
            load_pack(str(pack_path))

    def test_login_without_a_fallback_is_refused(self, tmp_path):
        pack_path = _copy_pack_with_settings(
            tmp_path, {"aaa": {"authentication": {"login": "group {group}"}}}
        )
        with pytest.raises(InvalidPackError, match="nobody can log in"):
            load_pack(str(pack_path))

    def test_invalid_privilege_level_is_refused(self, tmp_path):
        pack_path = _copy_pack_with_settings(
            tmp_path, {"aaa": {"authorization": {"commands": [16]}}}
        )
        with pytest.raises(InvalidPackError, match="Privilege level 16 is out of range"):
            load_pack(str(pack_path))

    def test_aaa_feature_off_falls_back_to_line_login_local(self):
        config = _render(features=[("base_config", "Yes"), ("aaa", "No")])
        assert "aaa new-model" not in config
        assert config.count(" login local") == 3  # con 0 plus both vty ranges


class TestMinorSettings:
    def test_uplink_storm_control_uses_the_prefix_list(self):
        """A 25G uplink should get the uplink levels, not the access-port ones."""
        pack_path = PACK_PATH
        config = _render_with_pack(pack_path, interface_rows=[
            ["SW-TEST-01", "TenGigabitEthernet1/1/1", "trunk-uplink", "Uplink", "", "", 10, "10,20", "", "", ""],
        ])
        assert "storm-control broadcast level 0.10 0.07" in config

    def test_prefix_list_is_configurable(self, tmp_path):
        pack_path = _copy_pack_with_settings(
            tmp_path, {"uplink_interface_prefixes": []}
        )
        config = _render_with_pack(pack_path, interface_rows=[
            ["SW-TEST-01", "TenGigabitEthernet1/1/1", "trunk-uplink", "Uplink", "", "", 10, "10,20", "", "", ""],
        ])
        # With no prefixes registered, the interface falls back to access levels.
        assert "storm-control broadcast level 1.00 0.70" in config
        assert "storm-control broadcast level 0.10 0.07" not in config

    def test_banner_containing_its_delimiter_is_rejected(self):
        import pytest as _pytest
        from cisco_config_generator.workbook.validators import ValidationError

        with _pytest.raises(ValidationError, match="delimiter character"):
            _render(global_overrides=[("banner_motd", "AUTHORISED ^ ACCESS ONLY")])

    def test_fail_message_containing_its_delimiter_is_rejected(self):
        import pytest as _pytest
        from cisco_config_generator.workbook.validators import ValidationError

        with _pytest.raises(ValidationError, match="delimiter character"):
            _render(global_overrides=[("aaa_fail_message", "Denied # try again")])

    def test_delimiters_are_configurable(self, tmp_path):
        pack_path = _copy_pack_with_settings(tmp_path, {"banner_delimiter": "%"})
        config = _render_with_pack(pack_path, global_overrides=[("banner_motd", "Contains ^ caret")])
        assert "banner motd %" in config
        assert "Contains ^ caret" in config

    def test_incompatible_schema_version_is_refused(self, tmp_path):
        import yaml

        pack_path = tmp_path / "future-pack"
        _copy_tree(PACK_PATH, pack_path)
        settings_file = pack_path / "settings.yaml"
        settings = yaml.safe_load(settings_file.read_text(encoding="utf-8"))
        settings["schema_version"] = "2.0"
        settings_file.write_text(yaml.safe_dump(settings, sort_keys=False), encoding="utf-8")
        with pytest.raises(InvalidPackError, match="schema_version"):
            load_pack(str(pack_path))

    def test_current_schema_version_loads(self):
        assert load_pack(str(PACK_PATH)).settings.ntp_mode == "server"


class TestPackSchema:
    """Mistakes that used to load silently and render a wrong config."""

    def test_misspelt_setting_is_refused_with_a_suggestion(self, tmp_path):
        pack_path = _copy_pack_with_settings(tmp_path, {"ssh_timout": 60})
        with pytest.raises(InvalidPackError) as exc_info:
            load_pack(str(pack_path))
        assert (
            "settings.yaml: defaults.ssh_timout is not a recognised setting. "
            "Did you mean 'ssh_timeout'?"
        ) in str(exc_info.value)

    def test_misspelt_nested_aaa_setting_is_refused(self, tmp_path):
        pack_path = _copy_pack_with_settings(tmp_path, {"aaa": {"authorisation": {"commands": []}}})
        with pytest.raises(InvalidPackError, match="Did you mean 'authorization'"):
            load_pack(str(pack_path))

    def test_misspelt_top_level_key_is_refused(self, tmp_path):
        pack_path = tmp_path / "pack"
        _copy_tree(PACK_PATH, pack_path)
        settings_file = pack_path / "settings.yaml"
        settings_file.write_text(
            settings_file.read_text(encoding="utf-8").replace("strict_validation:", "strict_validaton:"),
            encoding="utf-8",
        )
        with pytest.raises(InvalidPackError, match="Did you mean 'strict_validation'"):
            load_pack(str(pack_path))

    def test_invalid_spanning_tree_mode_is_refused(self, tmp_path):
        pack_path = _copy_pack_with_settings(tmp_path, {"spanning_tree_mode": "rapid-pvts"})
        with pytest.raises(InvalidPackError, match="spanning_tree_mode is 'rapid-pvts'"):
            load_pack(str(pack_path))

    def test_out_of_range_vlan_is_refused(self, tmp_path):
        pack_path = _copy_pack_with_settings(tmp_path, {"unused_vlan": 5000})
        with pytest.raises(InvalidPackError, match="defaults.unused_vlan: VLAN 5000 is out of range"):
            load_pack(str(pack_path))

    def test_wrong_type_is_refused(self, tmp_path):
        pack_path = _copy_pack_with_settings(tmp_path, {"ssh_timeout": "fifteen"})
        with pytest.raises(InvalidPackError, match="ssh_timeout expected a whole number, got 'fifteen'"):
            load_pack(str(pack_path))

    def test_every_error_is_reported_at_once(self, tmp_path):
        pack_path = _copy_pack_with_settings(
            tmp_path, {"ntp_mode": "broadcast", "ssh_version": 3, "banner_delimiter": "^^"}
        )
        with pytest.raises(InvalidPackError) as exc_info:
            load_pack(str(pack_path))
        message = str(exc_info.value)
        assert "ntp_mode" in message
        assert "ssh_version" in message
        assert "banner_delimiter" in message

    def test_misspelt_hardware_key_is_refused(self, tmp_path):
        """'acess_ports' used to leave every port on the switch unconfigured."""
        pack_path = tmp_path / "pack"
        _copy_tree(PACK_PATH, pack_path)
        catalog = pack_path / "hardware_catalog.yaml"
        catalog.write_text(
            catalog.read_text(encoding="utf-8").replace("access_ports: 48", "acess_ports: 48", 1),
            encoding="utf-8",
        )
        with pytest.raises(InvalidPackError) as exc_info:
            load_pack(str(pack_path))
        message = str(exc_info.value)
        assert "hardware_catalog.yaml: switch_models.C9200-48P.acess_ports is not a recognised setting" in message
        assert "Did you mean 'access_ports'?" in message
        assert "switch_models.C9200-48P.access_ports is required." in message

    def test_uplink_module_with_ports_needs_a_prefix(self, tmp_path):
        import yaml

        pack_path = tmp_path / "pack"
        _copy_tree(PACK_PATH, pack_path)
        catalog_file = pack_path / "hardware_catalog.yaml"
        catalog = yaml.safe_load(catalog_file.read_text(encoding="utf-8"))
        catalog["uplink_modules"]["NM-4X"]["interface_prefix"] = ""
        catalog_file.write_text(yaml.safe_dump(catalog), encoding="utf-8")
        with pytest.raises(InvalidPackError, match="uplink_modules.NM-4X has 4 uplink port"):
            load_pack(str(pack_path))

    def test_profile_template_hint_must_exist_in_the_template_map(self, tmp_path):
        pack_path = tmp_path / "pack"
        _copy_tree(PACK_PATH, pack_path)
        profiles = pack_path / "port_profiles.yaml"
        profiles.write_text(
            profiles.read_text(encoding="utf-8").replace(
                "template_hint: interfaces_access_server", "template_hint: interfaces_acess_server"
            ),
            encoding="utf-8",
        )
        with pytest.raises(InvalidPackError, match="'interfaces_acess_server', which is not defined in template_map.yaml"):
            load_pack(str(pack_path))

    def test_unused_profile_is_required(self, tmp_path):
        import yaml

        pack_path = tmp_path / "pack"
        _copy_tree(PACK_PATH, pack_path)
        profiles_file = pack_path / "port_profiles.yaml"
        profiles = yaml.safe_load(profiles_file.read_text(encoding="utf-8"))
        del profiles["profiles"]["unused"]
        profiles_file.write_text(yaml.safe_dump(profiles), encoding="utf-8")
        with pytest.raises(InvalidPackError, match="no 'unused' profile"):
            load_pack(str(pack_path))

    def test_template_file_must_exist(self, tmp_path):
        pack_path = tmp_path / "pack"
        _copy_tree(PACK_PATH, pack_path)
        (pack_path / "templates" / "vlans.j2").unlink()
        with pytest.raises(InvalidPackError, match="'vlans.j2', which does not exist"):
            load_pack(str(pack_path))

    def test_broken_yaml_names_the_file(self, tmp_path):
        pack_path = tmp_path / "pack"
        _copy_tree(PACK_PATH, pack_path)
        (pack_path / "features.yaml").write_text("features: [unclosed\n", encoding="utf-8")
        with pytest.raises(InvalidPackError, match="features.yaml: not valid YAML"):
            load_pack(str(pack_path))


def _schema_shape(schema: dict) -> dict:
    """What a pack author relies on: the keys, which are required, and the allowed values.

    Compared instead of the raw text, because pydantic's JSON formatting
    shifts slightly between releases without the schema meaning anything new.
    """
    def constraints(node: object) -> list[str]:
        found: list[str] = []
        if isinstance(node, dict):
            for key in ("minimum", "maximum", "pattern", "$ref"):
                if key in node:
                    found.append(f"{key}={node[key]!r}")
            # A single allowed value may be written as const, enum, or both.
            values = [*node.get("enum", []), *([node["const"]] if "const" in node else [])]
            found.extend(f"value={value!r}" for value in values)
            for key in ("anyOf", "items", "additionalProperties"):
                child = node.get(key)
                for item in child if isinstance(child, list) else [child]:
                    found.extend(constraints(item))
        return sorted(set(found))

    definitions = {"<root>": schema, **schema.get("$defs", {})}
    return {
        name: {
            "required": sorted(definition.get("required", [])),
            "properties": {key: constraints(value) for key, value in definition.get("properties", {}).items()},
            "extra_keys_allowed": definition.get("additionalProperties", True),
        }
        for name, definition in definitions.items()
    }


class TestPublishedSchemas:
    def test_committed_json_schemas_match_the_models(self):
        """Regenerate with: python scripts/export_pack_schemas.py"""
        import json

        from cisco_config_generator.pack_schema import json_schemas

        schema_dir = REPO_ROOT / "schemas"
        for name, text in json_schemas().items():
            committed = schema_dir / name
            assert committed.exists(), f"schemas/{name} is missing"
            assert _schema_shape(json.loads(committed.read_text(encoding="utf-8"))) == _schema_shape(
                json.loads(text)
            ), f"schemas/{name} is out of date - run scripts/export_pack_schemas.py"

    def test_schema_check_notices_a_new_setting(self):
        """Guard for the comparison above: a model change must show up in the shape."""
        import json

        from cisco_config_generator.pack_schema import json_schemas

        current = json.loads(json_schemas()["settings.schema.json"])
        changed = json.loads(json_schemas()["settings.schema.json"])
        changed["$defs"]["PackDefaults"]["properties"]["new_knob"] = {"type": "string"}
        assert _schema_shape(current) != _schema_shape(changed)
        changed = json.loads(json_schemas()["settings.schema.json"])
        changed["$defs"]["PackDefaults"]["properties"]["ntp_mode"]["enum"].append("broadcast")
        assert _schema_shape(current) != _schema_shape(changed)

    def test_shipped_site_files_point_at_the_site_schema(self):
        for site_file in (REPO_ROOT / "sites").glob("*.yaml"):
            first_line = site_file.read_text(encoding="utf-8").splitlines()[0]
            assert first_line == "# yaml-language-server: $schema=../schemas/site.schema.json", site_file.name

    def test_default_pack_files_point_at_their_schema(self):
        for filename in ("settings", "hardware_catalog", "port_profiles", "template_map", "features"):
            first_line = (PACK_PATH / f"{filename}.yaml").read_text(encoding="utf-8").splitlines()[0]
            assert first_line == f"# yaml-language-server: $schema=../../schemas/{filename}.schema.json"


class TestCustomSettings:
    def test_custom_values_reach_the_templates(self, tmp_path):
        """A pack's own templates need knobs the core does not know about."""
        pack_path = _copy_pack_with_settings(tmp_path, {"custom": {"site_code": "LON1"}})
        base = pack_path / "templates" / "base.j2"
        base.write_text(
            base.read_text(encoding="utf-8") + "! site code {{ d.custom.site_code }}\n", encoding="utf-8"
        )
        assert "! site code LON1" in _render_with_pack(pack_path)

    def test_unknown_key_points_at_custom(self, tmp_path):
        pack_path = _copy_pack_with_settings(tmp_path, {"site_code": "LON1"})
        with pytest.raises(InvalidPackError, match="belong under defaults.custom"):
            load_pack(str(pack_path))
