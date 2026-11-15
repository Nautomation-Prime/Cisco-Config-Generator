"""End-to-end tests for the command line entry point.

Nothing else in the suite imports cisco_config_generator.cli, which is how a
broken top-level import once shipped with CI green. These tests exercise the
real entry point.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from click.testing import CliRunner

from cisco_config_generator.cli import main
from tests.test_orchestrator_integration import _create_test_workbook

REPO_ROOT = Path(__file__).resolve().parents[1]
PACK_PATH = REPO_ROOT / "packs" / "default"


class TestCliEntryPoint:
    def test_module_entry_point_imports(self):
        """python -m cisco_config_generator must not fail at import time."""
        import cisco_config_generator.__main__  # noqa: F401

    def test_version_flag(self):
        result = CliRunner().invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "Cisco Config Generator" in result.output

    def test_headless_requires_a_workbook(self):
        result = CliRunner().invoke(main, ["--no-tui"])
        assert result.exit_code == 1
        assert "--workbook is required" in result.output

    def test_headless_run_writes_a_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            workbook = tmp_path / "intent.xlsx"
            output = tmp_path / "out"
            _create_test_workbook(workbook)

            result = CliRunner().invoke(
                main,
                ["--no-tui", "--pack", str(PACK_PATH), "--workbook", str(workbook), "--output", str(output),
                 "--sites-dir", str(tmp_path / "sites")],
            )

            assert result.exit_code == 0, result.output
            written = list(output.glob("*.cfg"))
            assert [p.name for p in written] == ["SW-TEST-01.cfg"]
            assert "hostname SW-TEST-01" in written[0].read_text()

    def test_headless_run_reports_validation_errors_and_exits_non_zero(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            workbook = tmp_path / "intent.xlsx"
            _create_test_workbook(workbook, global_overrides=[("enable_secret", "changeme")])

            result = CliRunner().invoke(
                main,
                ["--no-tui", "--pack", str(PACK_PATH), "--workbook", str(workbook),
                 "--output", str(tmp_path / "out"), "--sites-dir", str(tmp_path / "sites")],
            )

            assert result.exit_code == 1
            assert not (tmp_path / "out").exists()

    def test_missing_workbook_path_is_rejected_by_click(self):
        result = CliRunner().invoke(main, ["--no-tui", "--workbook", "does-not-exist.xlsx"])
        assert result.exit_code != 0
