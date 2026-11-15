"""Whole-file snapshot of the configs rendered from the sample workbook.

Every other rendering test asserts on a handful of lines. This one compares the
complete output of assets/sample_intent.xlsx against the default pack, so any
template or engine change that alters a generated config shows up as a diff.

When a change to the output is intended, regenerate the snapshots and review
the diff before committing:

    UPDATE_SNAPSHOTS=1 pytest tests/test_snapshots.py
"""

from __future__ import annotations

import difflib
import os
from pathlib import Path

import pytest

from cisco_config_generator.orchestrator import Orchestrator

REPO_ROOT = Path(__file__).resolve().parents[1]
PACK_PATH = REPO_ROOT / "packs" / "default"
SAMPLE_WORKBOOK = REPO_ROOT / "assets" / "sample_intent.xlsx"
SNAPSHOT_DIR = Path(__file__).resolve().parent / "snapshots" / "sample_intent"

UPDATE = os.environ.get("UPDATE_SNAPSHOTS") == "1"


@pytest.fixture(scope="module")
def rendered(tmp_path_factory) -> dict[str, str]:
    output_dir = tmp_path_factory.mktemp("snapshot-output")
    paths = Orchestrator(
        pack_path=PACK_PATH,
        workbook_path=SAMPLE_WORKBOOK,
        output_dir=output_dir,
    ).run()
    return {path.name: path.read_text(encoding="utf-8") for path in paths}


def test_snapshot_set_matches(rendered):
    """A device added to or dropped from the sample must be a deliberate change."""
    if UPDATE:
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        for stale in SNAPSHOT_DIR.glob("*.cfg"):
            if stale.name not in rendered:
                stale.unlink()
        for name, text in rendered.items():
            (SNAPSHOT_DIR / name).write_text(text, encoding="utf-8", newline="\n")
    expected = sorted(p.name for p in SNAPSHOT_DIR.glob("*.cfg"))
    assert sorted(rendered) == expected


@pytest.mark.parametrize(
    "name", sorted(p.name for p in SNAPSHOT_DIR.glob("*.cfg")) or ["<no snapshots>"]
)
def test_rendered_config_matches_snapshot(rendered, name):
    snapshot = SNAPSHOT_DIR / name
    assert snapshot.exists(), "No snapshots yet - run with UPDATE_SNAPSHOTS=1 to create them."
    expected = snapshot.read_text(encoding="utf-8")
    actual = rendered.get(name, "")
    if actual != expected:
        diff = "".join(difflib.unified_diff(
            expected.splitlines(keepends=True),
            actual.splitlines(keepends=True),
            fromfile=f"snapshot/{name}",
            tofile=f"rendered/{name}",
        ))
        pytest.fail(
            f"{name} differs from its snapshot. If the change is intended, "
            f"rerun with UPDATE_SNAPSHOTS=1.\n{diff}"
        )
