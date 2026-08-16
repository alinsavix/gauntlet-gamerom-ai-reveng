"""WP-21 sub-deliverable 3 -- MAME cross-check.

Scoped down to a design for this session: see ``mame_crosscheck.py``'s module
docstring for why (no reusable MAME script/trace exists anywhere in the
tree, and producing one needs an interactive MAME session). The tests below
check the interface itself rather than a real trace: the address map is
parsed from ``state.py``, not hand-copied, and the comparison logic behaves
correctly against a hand-built fake "MAME export."

The dedicated ``test_a_full_crosscheck_would_activate_here`` documents the
one remaining step -- pointing ``TRACE_PATH`` at a real export -- and is
skipped until that file exists, exactly like ``test_mainloop.py``'s
``requires_contracts`` pattern for a missing CSV.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from golden import GOLDEN_SEED, build_scripted_state
from mame_crosscheck import (
    PLAYER_FIELD_ADDRESSES,
    compare_state_to_trace,
    field_addresses,
    load_mame_trace,
)

TRACE_PATH = Path(__file__).resolve().parent / "goldens" / "mame_trace.csv"


def test_field_address_map_matches_state_py_verbatim():
    """A few load-bearing addresses, spot-checked against doc/05_data_
    reference.md directly (not just against state.py's own comment, which
    would be circular)."""
    addresses = field_addresses()

    assert addresses["frame_counter"] == 0x904006  # doc/05_data_reference.md line 20
    assert addresses["game_mode"] == 0x904918
    assert addresses["dialog_timer"] == 0x904A9E
    assert addresses["vblank_flag"] == 0x904002

    # Composite fields (no single address of their own) must not appear.
    assert "mobs" not in addresses
    assert "rng" not in addresses
    assert "players" not in addresses


def test_player_health_address_matches_doc_05_data_reference():
    """doc/05_data_reference.md line 149: '0x904980 | 4 B x 4 | player_health
    | Per-player health (32-bit longwords, stride 4).'"""
    base, stride = PLAYER_FIELD_ADDRESSES["health"]
    assert base == 0x904980
    assert stride == 4


def test_compare_state_to_trace_detects_a_real_mismatch():
    """Exercise the comparison logic against a hand-built fake trace, since
    no real MAME export exists yet."""
    state = build_scripted_state()
    state.frame_counter = 5

    trace = [
        {"frame": 5, "address": 0x904006, "value": 5},   # matches
        {"frame": 5, "address": 0x904918, "value": -99},  # game_mode mismatch
        {"frame": 5, "address": 0xDEADBE, "value": 1},    # untracked -- ignored
    ]

    problems = compare_state_to_trace(state, trace, frame=5)

    assert len(problems) == 1
    assert "game_mode" in problems[0]
    assert "0x904918" in problems[0].upper() or "0x904918".upper() in problems[0].upper()


def test_compare_state_to_trace_checks_per_player_health():
    state = build_scripted_state()
    state.players[2].health = 300

    trace = [{"frame": 0, "address": 0x904980 + 4 * 2, "value": 301}]
    problems = compare_state_to_trace(state, trace, frame=0)

    assert len(problems) == 1
    assert "player[2].health" in problems[0]


def test_compare_state_to_trace_is_silent_when_nothing_watched_this_frame():
    state = build_scripted_state()
    trace = [{"frame": 7, "address": 0x904006, "value": 999}]
    assert compare_state_to_trace(state, trace, frame=3) == []


def test_load_mame_trace_parses_hex_and_decimal_cells():
    # Not pytest's ``tmp_path`` fixture: this environment's pytest basetemp
    # (W:\zTEMP\TEMP\pytest-of-*) is not scannable, which fails fixture setup
    # before the test body even runs. A plain tempfile sidesteps that.
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        export = Path(tmpdir) / "fake_trace.csv"
        export.write_text(
            "frame,address,value\n"
            "0,0x904006,0\n"
            "1,9453574,1\n",  # decimal 0x904006 -- must parse the same as hex
            encoding="utf-8",
        )

        rows = load_mame_trace(export)

    assert rows[0] == {"frame": 0, "address": 0x904006, "value": 0}
    assert rows[1] == {"frame": 1, "address": 0x904006, "value": 1}


@pytest.mark.skipif(
    not TRACE_PATH.exists(),
    reason=(
        "no MAME trace recorded yet -- see mame_crosscheck.py's module "
        "docstring for what producing tests/goldens/mame_trace.csv requires"
    ),
)
def test_a_full_crosscheck_would_activate_here():
    """Once tests/goldens/mame_trace.csv exists (a real export, forced to
    GOLDEN_SEED per PLAN.md §21), this replays the same scripted run our
    golden trace uses and diffs every frame against MAME."""
    from gauntpy.mainloop import tick

    state = build_scripted_state()
    assert state.rng.seed == GOLDEN_SEED

    trace = load_mame_trace(TRACE_PATH)
    frames = {r["frame"] for r in trace}

    problems: list[str] = []
    for frame in range(max(frames) + 1):
        tick(state)
        problems.extend(compare_state_to_trace(state, trace, frame))

    assert not problems, "diverged from MAME:\n  " + "\n  ".join(problems)
