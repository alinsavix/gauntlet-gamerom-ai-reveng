"""Declarative synthetic-maze parsing, runtime, and dump provenance."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gauntpy.custom_scenario import (
    SYNTHETIC_SCENARIO_FORMAT,
    SyntheticScenarioError,
    SyntheticScenarioRuntime,
    apply_synthetic_events,
    attach_synthetic_runtime,
    build_synthetic_state,
    load_synthetic_scenario,
    parse_synthetic_scenario,
    synthetic_runtime_for,
)
from gauntpy.coords import hpos_x
from gauntpy.mainloop import tick
from gauntpy.render.state_dump import (
    StateDumpError,
    game_state_from_payload,
    state_dump_payload,
)
from gauntpy.render.diagnostics import (
    DEBUG_PAGES,
    capture_debug_snapshot,
    debug_page_lines,
)
from gauntpy.state import GameState
from gauntpy.subsystems.thief import THIEF_IS_MUGGER
from gauntpy.subsystems.input import JOY_IDLE, JOY_RIGHT

from gex.roms import SLAPSTIC_ROMS, TILE_ROMS, _rom_dir


_EXAMPLE = Path(__file__).parents[1] / "scenarios" / "narrow-lane-thief.gsc"
_ROM_PATH = _rom_dir()
requires_roms = pytest.mark.skipif(
    not (
        _ROM_PATH.is_dir()
        and (_ROM_PATH / SLAPSTIC_ROMS[0]).is_file()
        and (_ROM_PATH / TILE_ROMS[0][0]).is_file()
    ),
    reason=f"ROM files not available at {_ROM_PATH}",
)


def test_example_is_an_exact_versioned_32_by_32_fixture():
    scenario = load_synthetic_scenario(_EXAMPLE)

    assert scenario.name == "narrow-lane-thief"
    assert len(scenario.grid) == 32
    assert {len(row) for row in scenario.grid} == {32}
    assert scenario.source_name == _EXAMPLE.name
    assert len(scenario.sha256) == 64
    assert scenario.events[0].frame == 1200
    assert scenario.events[0].action == "activate_thief"
    assert scenario.initial_input is None


def test_live_scenario_input_does_not_overwrite_host_controls():
    scenario = load_synthetic_scenario(_EXAMPLE)
    state = GameState()
    state.player_input_raw[0] = JOY_IDLE & ~JOY_RIGHT
    attach_synthetic_runtime(state, SyntheticScenarioRuntime(scenario))

    apply_synthetic_events(state)

    assert state.player_input_raw[0] == JOY_IDLE & ~JOY_RIGHT


def test_diagnostics_page_shows_pending_and_fired_event_timers():
    scenario = load_synthetic_scenario(_EXAMPLE)
    state = GameState(frame_counter=1000)
    runtime = SyntheticScenarioRuntime(scenario)
    attach_synthetic_runtime(state, runtime)
    page = DEBUG_PAGES.index("SCENARIO")

    pending = dict(debug_page_lines(capture_debug_snapshot(state), page))
    runtime.fired_events.add(0)
    fired = dict(debug_page_lines(capture_debug_snapshot(state), page))

    assert pending["NAME"] == "narrow-lane-thief"
    assert pending["SOURCE"] == _EXAMPLE.name
    assert pending["INPUT"] == "LIVE"
    assert pending["EVENTS"] == "0/1 fired"
    assert pending["EVT 00"].startswith(
        "T-00200 @01200 activate_thief 1 28 mugger"
    )
    assert fired["EVENTS"] == "1/1 fired"
    assert fired["EVT 00"].startswith(
        "FIRED @01200 activate_thief 1 28 mugger"
    )


@requires_roms
def test_example_accepts_live_movement_through_the_frame_loop():
    state = build_synthetic_state(load_synthetic_scenario(_EXAMPLE))
    player = state.players[0]
    before = hpos_x(state.mobs.hpos[player.mob_slot])
    state.player_input_raw[0] = JOY_IDLE & ~JOY_RIGHT

    apply_synthetic_events(state)
    tick(state)

    assert hpos_x(state.mobs.hpos[player.mob_slot]) > before


def test_parser_rejects_unknown_symbols_and_non_wall_row_zero():
    text = _EXAMPLE.read_text(encoding="utf-8")

    with pytest.raises(SyntheticScenarioError, match="undefined symbols"):
        parse_synthetic_scenario(text.replace("#.@", "#x@", 1))
    with pytest.raises(SyntheticScenarioError, match="row 0"):
        parse_synthetic_scenario(text.replace("################################", ".###############################", 1))


def test_parser_rejects_arbitrary_event_actions():
    text = _EXAMPLE.read_text(encoding="utf-8")
    text = text.replace(
        "1200 activate_thief 1 28 mugger",
        "1200 execute_python dangerous.py",
    )

    with pytest.raises(SyntheticScenarioError, match="unsupported action"):
        parse_synthetic_scenario(text)


def test_parser_rejects_events_beyond_the_wrapping_frame_counter():
    text = _EXAMPLE.read_text(encoding="utf-8").replace(
        "1200 activate_thief", "65536 activate_thief",
    )

    with pytest.raises(SyntheticScenarioError, match="event frame"):
        parse_synthetic_scenario(text)


@requires_roms
def test_synthetic_build_uses_modeled_maze_mob_and_playfield_memory():
    state = build_synthetic_state(load_synthetic_scenario(_EXAMPLE))

    assert state.players[0].active
    assert state.players[0].mob_slot
    assert state.maze is not None
    assert any(state.playfield_ram)
    assert state.levelnum_current == 16
    assert state.mazenum_current == 15
    assert synthetic_runtime_for(state) is not None


@requires_roms
def test_scheduled_mugger_deploys_at_the_absolute_frame():
    state = build_synthetic_state(load_synthetic_scenario(_EXAMPLE))
    state.frame_counter = 1200

    apply_synthetic_events(state)

    assert state.thief_current_pos
    assert state.thief_mode & THIEF_IS_MUGGER
    assert synthetic_runtime_for(state).fired_events == {0}


@requires_roms
def test_pending_scheduled_event_survives_state_dump_resume():
    state = build_synthetic_state(load_synthetic_scenario(_EXAMPLE))
    state.frame_counter = 1200
    restored = game_state_from_payload(
        json.loads(json.dumps(state_dump_payload(state)))
    )

    apply_synthetic_events(restored)

    assert restored.thief_current_pos
    assert restored.thief_mode & THIEF_IS_MUGGER
    assert synthetic_runtime_for(restored).fired_events == {0}


def test_state_dump_embeds_self_contained_synthetic_provenance_and_runtime():
    scenario = load_synthetic_scenario(_EXAMPLE)
    state = GameState()
    runtime = SyntheticScenarioRuntime(scenario, fired_events={0})
    runtime.current_input = None
    attach_synthetic_runtime(state, runtime)

    payload = state_dump_payload(state)
    restored = game_state_from_payload(json.loads(json.dumps(payload)))
    metadata = payload["synthetic_scenario"]
    restored_runtime = synthetic_runtime_for(restored)

    assert metadata["format"] == SYNTHETIC_SCENARIO_FORMAT
    assert metadata["synthetic"] is True
    assert metadata["source_name"] == _EXAMPLE.name
    assert metadata["content"] == scenario.canonical_content
    assert metadata["sha256"] == scenario.sha256
    assert restored_runtime.scenario.sha256 == scenario.sha256
    assert restored_runtime.fired_events == {0}
    assert restored_runtime.current_input is None


def test_state_dump_rejects_tampered_synthetic_content():
    scenario = load_synthetic_scenario(_EXAMPLE)
    state = GameState()
    attach_synthetic_runtime(state, SyntheticScenarioRuntime(scenario))
    payload = state_dump_payload(state)
    payload["synthetic_scenario"]["content"] += "; changed\n"

    with pytest.raises(StateDumpError, match="hash mismatch"):
        game_state_from_payload(payload)
