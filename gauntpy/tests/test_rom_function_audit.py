"""The ROM/Python audit must classify every callable entry exactly once."""

from __future__ import annotations

import csv
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "doc" / "generated" / "callable_contract_coverage.csv"
REPORT = ROOT / "gauntpy" / "ROM_FUNCTION_AUDIT.md"
CROSSWALK = ROOT / "gauntpy" / "ROM_FUNCTION_AUDIT.csv"

MISSING = {0x49A98}
PARTIAL = {
    0x4280E, 0x428A4, 0x4293A, 0x429D0, 0x43F68,
    0x46C5E, 0x4DE76, 0x4E7FC,
}
OMITTED = {
    0x40000, 0x40006, 0x4000C, 0x40012, 0x40018, 0x4001E, 0x40024,
    0x40030, 0x40048, 0x40054, 0x400DE, 0x400E4, 0x400EA, 0x400F0,
    0x400F6, 0x40140, 0x4014C,
    0x40CC4, 0x40CF2, 0x40D24, 0x40D4E, 0x43826,
    0x56E58, 0x56E6E, 0x56E84, 0x56E90, 0x56E98, 0x56EAA,
    0x41C30, 0x42598, 0x425B4, 0x5DE44, 0x5DED4, 0x5E542,
    0x5E5D2, 0x5EA26, 0x5EAC2, 0x5F598, 0x5F772, 0x5FC56,
    0x5554E, 0x555C4, 0x5F644,
    0x449CC, 0x5317C,
    0x45BE8, 0x5FD58, 0x5FD64, 0x5FD6A,
    0x5E868,
}


def _inventory_addresses() -> set[int]:
    with INVENTORY.open(newline="", encoding="utf-8") as handle:
        return {int(row["address"], 16) for row in csv.DictReader(handle)}


def test_every_callable_has_exactly_one_audit_class():
    inventory = _inventory_addresses()
    exceptions = MISSING | PARTIAL | OMITTED

    assert len(inventory) == 322
    assert not (MISSING & PARTIAL)
    assert not (MISSING & OMITTED)
    assert not (PARTIAL & OMITTED)
    assert exceptions <= inventory
    assert len(inventory - exceptions) == 263


def test_crosswalk_matches_the_callable_inventory_and_class_totals():
    with CROSSWALK.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 322
    assert {int(row["address"], 16) for row in rows} == _inventory_addresses()
    assert len({row["rom_name"] for row in rows}) == 322
    assert {
        status: sum(row["status"] == status for row in rows)
        for status in {"complete", "partial", "unnecessary", "missing_gameplay"}
    } == {
        "complete": 263,
        "partial": 8,
        "unnecessary": 50,
        "missing_gameplay": 1,
    }


def test_report_exception_addresses_match_the_guard():
    text = REPORT.read_text(encoding="utf-8")
    sections = {
        "missing": text.split("## Missing game behavior", 1)[1].split(
            "## Partial equivalents", 1
        )[0],
        "partial": text.split("## Partial equivalents", 1)[1].split(
            "## Intentionally omitted entries", 1
        )[0],
        "omitted": text.split("## Intentionally omitted entries", 1)[1].split(
            "## Complete set", 1
        )[0],
    }

    def addresses(section: str) -> set[int]:
        return {
            int(value, 16)
            for value in re.findall(r"`0x([45][0-9A-F]{4})(?:`| )", section)
        }

    assert addresses(sections["missing"]) == MISSING
    assert addresses(sections["partial"]) == PARTIAL
    assert addresses(sections["omitted"]) == OMITTED
