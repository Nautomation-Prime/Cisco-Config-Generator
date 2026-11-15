from __future__ import annotations

from pathlib import Path

import pytest

from cisco_config_generator.site_loader import (
    InvalidSiteError,
    SiteNotFoundError,
    list_available_sites,
    load_site,
    load_sites,
    resolve_site_path,
)


def _write(tmp_path: Path, name: str, content: str) -> Path:
    sites_dir = tmp_path / "sites"
    sites_dir.mkdir(exist_ok=True)
    path = sites_dir / f"{name}.yaml"
    path.write_text(content, encoding="utf-8")
    return sites_dir


class TestResolveSitePath:
    def test_exact_match(self, tmp_path):
        sites_dir = _write(tmp_path, "site-a", "domain_name: example.com\n")
        assert resolve_site_path("site-a", sites_dir).name == "site-a.yaml"

    def test_case_insensitive_match(self, tmp_path):
        sites_dir = _write(tmp_path, "site-a", "domain_name: example.com\n")
        assert resolve_site_path("Site-A", sites_dir).name == "site-a.yaml"

    def test_missing_site_raises(self, tmp_path):
        sites_dir = tmp_path / "sites"
        sites_dir.mkdir()
        with pytest.raises(SiteNotFoundError):
            resolve_site_path("nope", sites_dir)

    def test_missing_sites_dir_raises(self, tmp_path):
        with pytest.raises(SiteNotFoundError):
            resolve_site_path("nope", tmp_path / "does-not-exist")


class TestListAvailableSites:
    def test_lists_yaml_files(self, tmp_path):
        sites_dir = tmp_path / "sites"
        sites_dir.mkdir()
        (sites_dir / "site-a.yaml").write_text("domain_name: a.example.com\n")
        (sites_dir / "site-b.yaml").write_text("domain_name: b.example.com\n")
        assert list_available_sites(sites_dir) == ["site-a", "site-b"]

    def test_missing_dir_returns_empty(self, tmp_path):
        assert list_available_sites(tmp_path / "does-not-exist") == []


class TestLoadSite:
    def test_parses_global_settings_vlans_and_acls(self, tmp_path):
        sites_dir = _write(tmp_path, "site-a", """
domain_name: example.com
timezone: CET
mgmt_subnet: "255.255.254.0"
ntp_servers: [10.0.0.1, 10.0.0.2]
aaa_servers: "10.0.0.10, 10.0.0.11"
enable_secret: EXAMPLE-enable-secret
vlans:
  - { vlan_id: 10, vlan_name: MGMT, description: "Management" }
  - { vlan_id: 20, vlan_name: DATA }
acls:
  - { acl_name: ACL_VTY_ACCESS, action: permit, network: 10.0.0.0, wildcard: 0.0.0.255 }
  - { acl_name: ACL_VTY_ACCESS, action: deny, network: any }
""")
        site = load_site("site-a", sites_dir)
        assert site.name == "site-a"
        assert site.timezone == "CET"
        assert site.mgmt_subnet == "255.255.254.0"
        assert site.global_settings.domain_name == "example.com"
        assert site.global_settings.ntp_servers == ["10.0.0.1", "10.0.0.2"]
        # Comma-separated strings are accepted alongside real YAML lists.
        assert site.global_settings.aaa_servers == ["10.0.0.10", "10.0.0.11"]
        assert site.global_settings.enable_secret == "EXAMPLE-enable-secret"
        assert [v.vlan_id for v in site.vlans] == [10, 20]
        assert site.vlans[0].description == "Management"
        assert len(site.acls) == 2
        assert site.acls[1].action == "deny"

    def test_site_name_defaults_to_filename(self, tmp_path):
        sites_dir = _write(tmp_path, "site-a", "domain_name: example.com\n")
        assert load_site("site-a", sites_dir).name == "site-a"

    def test_site_name_override(self, tmp_path):
        sites_dir = _write(tmp_path, "site-a", "site_name: 'Head Office'\n")
        assert load_site("site-a", sites_dir).name == "Head Office"

    def test_empty_file_uses_all_defaults(self, tmp_path):
        sites_dir = _write(tmp_path, "site-a", "")
        site = load_site("site-a", sites_dir)
        assert site.vlans == []
        assert site.acls == []
        assert site.global_settings.enable_secret == "changeme"

    def test_non_mapping_yaml_raises(self, tmp_path):
        sites_dir = _write(tmp_path, "site-a", "- just\n- a\n- list\n")
        with pytest.raises(InvalidSiteError):
            load_site("site-a", sites_dir)

    def test_malformed_yaml_raises(self, tmp_path):
        sites_dir = _write(tmp_path, "site-a", "domain_name: [unterminated\n")
        with pytest.raises(InvalidSiteError):
            load_site("site-a", sites_dir)

    def test_vlan_missing_id_raises(self, tmp_path):
        sites_dir = _write(tmp_path, "site-a", "vlans:\n  - { vlan_name: MGMT }\n")
        with pytest.raises(InvalidSiteError, match="vlan_id"):
            load_site("site-a", sites_dir)

    def test_acl_missing_name_raises(self, tmp_path):
        sites_dir = _write(tmp_path, "site-a", "acls:\n  - { action: permit, network: any }\n")
        with pytest.raises(InvalidSiteError, match="acl_name"):
            load_site("site-a", sites_dir)


class TestLoadSites:
    def test_loads_every_resolvable_name(self, tmp_path):
        sites_dir = tmp_path / "sites"
        sites_dir.mkdir()
        (sites_dir / "site-a.yaml").write_text("domain_name: a.example.com\n")
        (sites_dir / "site-b.yaml").write_text("domain_name: b.example.com\n")

        sites, errors = load_sites(["site-a", "site-b"], sites_dir)
        assert errors == []
        assert set(sites.keys()) == {"site-a", "site-b"}

    def test_unresolvable_name_is_skipped_not_errored(self, tmp_path):
        """A device referencing an unknown site is reported by the workbook
        validator (with the list of available sites), not here."""
        sites_dir = tmp_path / "sites"
        sites_dir.mkdir()
        sites, errors = load_sites(["nope"], sites_dir)
        assert sites == {}
        assert errors == []

    def test_blank_name_is_ignored(self, tmp_path):
        sites, errors = load_sites([""], tmp_path / "sites")
        assert sites == {}
        assert errors == []

    def test_malformed_site_file_is_reported(self, tmp_path):
        sites_dir = _write(tmp_path, "site-a", "domain_name: [unterminated\n")
        sites, errors = load_sites(["site-a"], sites_dir)
        assert sites == {}
        assert len(errors) == 1
        assert "site-a" in errors[0]


class TestSiteFileValidation:
    """Site files go through the same models as the workbook, so mistakes are named."""

    def _errors(self, tmp_path: Path, content: str) -> list[str]:
        sites_dir = _write(tmp_path, "site-a", content)
        sites, errors = load_sites(["site-a"], sites_dir)
        assert sites == {}
        return errors

    def test_misspelt_setting_suggests_the_real_one(self, tmp_path):
        assert self._errors(tmp_path, "ntp_server: [10.0.0.1]\n") == [
            "Site 'site-a' (site-a.yaml): ntp_server is not a recognised setting. "
            "Did you mean 'ntp_servers'? Check the spelling, or remove it."
        ]

    def test_bad_address_names_the_list_entry(self, tmp_path):
        assert self._errors(tmp_path, "syslog_server: [10.0.1.30, 10.0.1.3l]\n") == [
            "Site 'site-a' (site-a.yaml): syslog_server[1]: '10.0.1.3l' is not a valid IPv4 address."
        ]

    def test_vlan_out_of_range_names_the_entry(self, tmp_path):
        errors = self._errors(tmp_path, "vlans:\n  - { vlan_id: 10, vlan_name: MGMT }\n  - { vlan_id: 5000, vlan_name: BAD }\n")
        assert errors == [
            "Site 'site-a' (site-a.yaml): vlans[1].vlan_id: VLAN 5000 is out of range. Valid range: 1 to 4094."
        ]

    def test_subnet_mask_in_an_acl_wildcard(self, tmp_path):
        errors = self._errors(
            tmp_path,
            "acls:\n  - { acl_name: ACL_VTY_ACCESS, action: permit, network: 10.0.0.0, wildcard: 255.255.255.0 }\n",
        )
        assert len(errors) == 1
        assert "acls[0].wildcard: '255.255.255.0' is a subnet mask" in errors[0]

    def test_invalid_choice(self, tmp_path):
        assert self._errors(tmp_path, "aaa_key_type: 9\n") == [
            "Site 'site-a' (site-a.yaml): aaa_key_type is '9'. Valid values: '0', '6' or '7'."
        ]

    def test_every_problem_is_reported_at_once(self, tmp_path):
        errors = self._errors(tmp_path, "aaa_protocol: diameter\nsnmp_host: nms.local\nmgmt_subnet: 255.0.255.0\n")
        assert len(errors) == 3

    def test_blank_values_fall_back_to_defaults(self, tmp_path):
        sites_dir = _write(tmp_path, "site-a", "aaa_group_name:\nbanner_motd: ''\n")
        settings = load_site("site-a", sites_dir).global_settings
        assert settings.aaa_group_name == "TACACS_SERVERS"
        assert settings.banner_motd.startswith("AUTHORISED ACCESS ONLY")

    def test_shipped_sample_site_is_valid(self):
        from cisco_config_generator.site_loader import SITES_DIR

        for name in list_available_sites(SITES_DIR):
            load_site(name, SITES_DIR)
