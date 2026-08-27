"""The loop's call sequence must match the ROM's, verbatim.

``game_frame`` is an ordinary function that calls subsystems by name, so the
fidelity check parses its source rather than inspecting a data structure. The
sequence still cannot drift from ``main_loop_contracts.csv`` without failing
here -- which is the point.
"""

from __future__ import annotations

import ast
import csv
import inspect
import textwrap
from pathlib import Path

import pytest

from gauntpy import mainloop
from gauntpy.constants import GameMode
from gauntpy.mainloop import check_frame_overflow, game_frame, tick
from gauntpy.state import GameState

CONTRACTS = Path(__file__).resolve().parents[2] / "doc" / "generated" / "main_loop_contracts.csv"


def loop_calls() -> list[str]:
    """Names called by ``game_frame``, in source order."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(game_frame)))
    calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]
    calls.sort(key=lambda n: (n.lineno, n.col_offset))
    return [n.func.id for n in calls]


def gated_calls() -> list[str]:
    """Names called inside the ``dialog_timer`` gate."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(game_frame)))
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            names = []
            for stmt in node.body:
                for sub in ast.walk(stmt):
                    if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name):
                        names.append((sub.lineno, sub.col_offset, sub.func.id))
            return [n for _, _, n in sorted(names)]
    return []


def contract_rows() -> list[dict]:
    with CONTRACTS.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


requires_contracts = pytest.mark.skipif(
    not CONTRACTS.exists(), reason=f"contract CSV not found at {CONTRACTS}"
)


@requires_contracts
def test_call_order_matches_the_rom():
    """The most valuable test here: our order *is* the ROM's order.

    Makes drift between game_frame and the documented sequence unmergeable.
    """
    expected = [r["name"] for r in contract_rows() if r["phase"] == "frame"]
    assert loop_calls() == expected


@requires_contracts
def test_one_time_init_is_not_in_the_frame_body():
    """It runs once, before the first frame -- not inside game_frame."""
    once = [r["name"] for r in contract_rows() if r["phase"] == "once"]
    assert once == ["one_time_init"]
    assert "one_time_init" not in loop_calls()

    source = inspect.getsource(mainloop.g2mainloop)
    assert "one_time_init(state)" in source, "the outer loop must still call it"


def test_band_partition():
    """Three calls before the gate, sixteen inside it, nine after."""
    names = loop_calls()
    gated = gated_calls()

    assert len(names) == 28
    assert len(gated) == 16
    assert names[:3] == [
        "main_logo_updcolors", "input_debounce", "coincheck",
    ]
    assert names[3:19] == gated
    assert len(names[19:]) == 9


def test_the_gate_is_on_dialog_timer():
    source = inspect.getsource(game_frame)
    assert "state.dialog_timer == 0" in source


def test_every_call_is_a_real_function():
    """No typos: each name in the body resolves to something callable."""
    for name in loop_calls():
        fn = getattr(mainloop, name, None)
        assert callable(fn), f"{name} is not imported into mainloop"


def test_a_frame_runs():
    state = GameState(game_mode=GameMode.NORMAL)
    tick(state)
    assert state.frame_counter == 1
    assert state.vblank_flag == 0


def test_vblank_advances_the_hurt_palette_timer():
    state = GameState(game_mode=GameMode.TITLE)
    state.players[0].hurt_cooldown = 0x12

    tick(state)
    assert state.players[0].hurt_cooldown == 0x0C
    tick(state)
    assert state.players[0].hurt_cooldown == 0x06
    tick(state)
    assert state.players[0].hurt_cooldown == 0


def test_gated_calls_are_skipped_during_a_dialog(monkeypatch):
    """A message box freezes the world band and nothing else."""
    ran: list[str] = []
    for name in loop_calls():
        monkeypatch.setattr(
            mainloop, name, lambda _s, _n=name: ran.append(_n)
        )

    state = GameState(game_mode=GameMode.NORMAL, dialog_timer=30)
    tick(state)

    gated = set(gated_calls())
    assert not (gated & set(ran)), "gameplay ran during a dialog"
    assert ran == [n for n in loop_calls() if n not in gated]


def test_all_calls_run_without_a_dialog(monkeypatch):
    ran: list[str] = []
    for name in loop_calls():
        monkeypatch.setattr(
            mainloop, name, lambda _s, _n=name: ran.append(_n)
        )

    tick(GameState(game_mode=GameMode.NORMAL))
    assert ran == loop_calls()


def test_host_can_pause_only_the_treasure_timer(monkeypatch):
    timer_calls = []
    monkeypatch.setattr(
        mainloop, "main_treasure_timer", lambda state: timer_calls.append(state),
    )
    state = GameState(game_mode=GameMode.NORMAL)

    tick(state, treasure_timer_paused=True)

    assert timer_calls == []
    assert state.frame_counter == 1


def test_frame_overflow_sets_then_decays():
    """Set to 8 when the display laps us mid-frame; halved on each good one."""
    state = GameState(game_mode=GameMode.NORMAL)

    tick(state)
    assert state.frame_overflow == 0, "a frame that fits changes nothing"

    state.vblank_flag = 1          # another field finished while we worked
    check_frame_overflow(state)
    assert state.frame_overflow == 8

    for expected in (4, 2, 1, 0, 0):
        tick(state)
        assert state.frame_overflow == expected


#: Main-loop calls and the work package that owns each. Every one of the 28 has
#: a body; this roster is what keeps that claim honest -- deleting an
#: implementation, or adding a call nobody owns, fails the assertions below.
#: The former ``@stub`` marker this test used to consult is gone from every
#: subsystem, so consulting it only ever proved that nothing was marked.
IMPLEMENTED_CALLS = {
    "input_debounce",                  # WP-4
    "sound_response",                  # WP-18
    "main_update_sound",               # WP-18
    "eeprom_periodic_write",           # WP-19
    "main_cycle_tport_and_ffield",     # WP-11
    "main_open_doors",                 # WP-11
    "main_walls_cyclic_move",          # WP-11
    "main_walls_random_move",          # WP-11
    "main_move_players",               # WP-6
    "main_health_countdown",           # WP-6
    "main_handle_death",               # WP-6
    "main_scroll_playfield",           # WP-13
    "coincheck",                       # WP-16
    "character_select_input_update",   # WP-16
    "main_start_game",                 # WP-16
    "main_handle_shots",               # WP-7
    "main_msgbox_countdown",           # WP-14
    "main_score_update",               # WP-14
    "main_score_display",              # WP-14
    "main_treasure_timer",             # WP-15
    "main_exit_move",                  # WP-15
    "main_move_monsters",              # WP-8
    "main_handle_dragon",              # WP-9
    "main_thief_anim",                 # WP-10
    "main_start_thief",                # WP-10
    "main_handle_potions",             # WP-12
    "main_logo_updcolors",             # WP-17
    "main_attract",                    # WP-17
}


def test_every_loop_call_has_an_owner():
    """The roster and the loop body must name exactly the same 28 calls."""
    names = set(loop_calls())
    assert names - IMPLEMENTED_CALLS == set(), "a main-loop call nobody owns"
    assert IMPLEMENTED_CALLS - names == set(), "the roster names a call the loop dropped"


def test_no_loop_call_is_an_empty_placeholder():
    """A body of nothing but a docstring (or a bare ``pass``) is a stub in all
    but name -- the thing the deleted ``@stub`` marker used to track."""
    import ast as _ast

    empty = []
    for name in loop_calls():
        fn = getattr(mainloop, name)
        try:
            tree = _ast.parse(textwrap.dedent(inspect.getsource(fn)))
        except (OSError, SyntaxError):       # pragma: no cover - C or wrapped
            continue
        body = tree.body[0].body
        stripped = [
            node for node in body
            if not (isinstance(node, _ast.Expr) and isinstance(node.value, _ast.Constant))
        ]
        if not stripped or all(isinstance(node, _ast.Pass) for node in stripped):
            empty.append(name)
    assert empty == [], f"main-loop calls with no implementation: {empty}"
    assert empty == [], f"main-loop calls with no implementation: {empty}"
