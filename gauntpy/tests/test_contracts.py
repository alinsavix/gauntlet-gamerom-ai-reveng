"""Worked examples of the ``tests/contracts.py`` helper -- WP-21 §1.

Most of ``doc/generated/*.csv`` documents a table or function contract that
belongs to a work package which has not landed yet (WP-5 through WP-17), so
there is nothing in the tree to check most of them against. These two tests
exercise the generic helper against what actually exists today:

1. WP-18 (sound) *has* landed -- ``subsystems/sound.py`` transcribes three
   named command IDs from ``refs/soundcmds.csv``. That is a real "table
   transcribed into Python, checked against its documented CSV row" case,
   the shape sub-deliverable 1 asks every future package to add for its own
   tables.
2. ``mainloop.py``'s call order is already covered by ``test_mainloop.py``,
   but only its *order* -- not the ROM address comment beside each call. This
   checks the addresses against ``main_loop_contracts.csv``'s ``target``
   column, which is a second, independent table over the same source line
   (name -> address, rather than position in a sequence).
"""

from __future__ import annotations

import inspect
import re

import pytest

from gauntpy import mainloop
from gauntpy.subsystems import sound

from contracts import (
    REPO_ROOT,
    assert_table_matches_contract,
    contract_map,
    load_contract_csv,
    parse_int,
)

MAIN_LOOP_CSV = "main_loop_contracts.csv"
SOUNDCMDS_CSV = "refs/soundcmds.csv"

requires_main_loop_csv = pytest.mark.skipif(
    not (REPO_ROOT / "doc" / "generated" / MAIN_LOOP_CSV).exists(),
    reason=f"contract CSV not found at doc/generated/{MAIN_LOOP_CSV}",
)
requires_soundcmds_csv = pytest.mark.skipif(
    not (REPO_ROOT / SOUNDCMDS_CSV).exists(),
    reason=f"contract CSV not found at {SOUNDCMDS_CSV}",
)


# --- 1. WP-18's sound command IDs against refs/soundcmds.csv ----------------
#
# refs/soundcmds.csv is the catalog PLAN.md §"WP-18" cites, and the one
# subsystems/sound.py's own module docstring names as authoritative: it
# carries the corrected CONTROL labels for 0x00/0x06/0x07 from the 2026-08-12
# MAME trace pass (doc/08_known_issues.md). doc/generated/soundcmds.csv is
# stale on exactly those three rows -- still "UNK ... (Used in self-test)" --
# because it predates that trace pass and has not been regenerated since.
# That staleness is a real doc/generated discrepancy; sound.py already flags
# it in its own comments, so this test points at the corrected file rather
# than re-litigating it.

@requires_soundcmds_csv
def test_soundcmds_catalog_is_the_documented_shape():
    """219 contiguous, unique command IDs 0x00-0xDA -- sound.py's own claim."""
    rows = load_contract_csv(SOUNDCMDS_CSV)
    ids = contract_map(rows, key_col="Sound Id", value_col="Subsystem", key_fn=parse_int)

    assert len(ids) == 219, "subsystems/sound.py's docstring: '219 command IDs'"
    assert min(ids) == 0x00
    assert max(ids) == 0xDA
    assert sorted(ids) == list(range(0x00, 0xDA + 1)), "must be contiguous, no gaps"


@requires_soundcmds_csv
def test_sound_command_constants_match_their_contract_row():
    """The three IDs WP-18 actually transcribed, checked row-for-row.

    This is the pattern every future package inherits: transcribe a table
    (however small) into Python, then diff it against its CSV contract with
    one call instead of one assertion per row.
    """
    rows = load_contract_csv(SOUNDCMDS_CSV)
    expected_subsystem = contract_map(rows, key_col="Sound Id", value_col="Subsystem", key_fn=parse_int)

    transcribed = {
        sound.SOUND_REINITIALIZE: "CONTROL",
        sound.SOUND_COMMAND_COUNT_QUERY: "CONTROL",
        sound.SOUND_DIAGNOSTIC_QUERY: "CONTROL",
    }
    expected = {k: expected_subsystem[k] for k in transcribed}

    assert_table_matches_contract(transcribed, expected, table_name="sound.py command-ID constants")


# --- 2. mainloop.py's ROM address comments against main_loop_contracts.csv --

CALL_ADDRESS_RE = re.compile(r"^\s*(\w+)\(state\)\s*#\s*(0x[0-9A-Fa-f]+)")


def _call_addresses_in(source: str) -> dict[str, int]:
    """``{call_name: rom_address}`` parsed from ``game_frame``'s trailing comments."""
    addresses: dict[str, int] = {}
    for line in source.splitlines():
        match = CALL_ADDRESS_RE.match(line)
        if match:
            addresses[match.group(1)] = int(match.group(2), 16)
    return addresses


@requires_main_loop_csv
def test_mainloop_address_comments_match_the_contract():
    """Every call in ``game_frame`` cites the address its CSV row documents.

    Independent of ``test_mainloop.py::test_call_order_matches_the_rom``:
    that test checks *order*, never *addresses* -- a call could be in the
    right position with a stale or transposed address comment and that test
    would not notice. This is ground rule 4 ("cite every non-obvious
    constant") turned into an assertion, and it does not care whether a call
    is still @stub -- the comment must be right regardless.
    """
    rows = load_contract_csv(MAIN_LOOP_CSV)
    frame_rows = [r for r in rows if r["phase"] == "frame"]
    expected = contract_map(frame_rows, key_col="name", value_col="target", value_fn=parse_int)

    source = inspect.getsource(mainloop.game_frame)
    actual = _call_addresses_in(source)

    assert actual, "no '# 0x...' address comments found in game_frame -- did the format change?"
    assert_table_matches_contract(actual, expected, table_name="game_frame ROM address comments")
