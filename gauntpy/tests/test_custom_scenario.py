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
    override_synthetic_seed,
    parse_synthetic_scenario,
    synthetic_runtime_for,
    _input_word,
)
from gauntpy.coords import hpos_x, vpos_y
from gauntpy.constants import GENERATOR_TYPES, MONSTER_TYPES, MazeObjIds
from gauntpy.mainloop import tick
from gauntpy.performance_workloads import (
    WORKLOAD_BY_NAME,
    prepare_workload_state,
    validate_runtime_invariants,
)
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
from gauntpy.subsystems.thief import path_grid_get_direction
from gauntpy.subsystems.input import JOY_FIRE_BIT, JOY_IDLE, JOY_MAGIC_BIT, JOY_RIGHT
from gauntpy.subsystems.monsters import tile_on_screen_d4

from gex.roms import SLAPSTIC_ROMS, TILE_ROMS, _rom_dir


_EXAMPLE = Path(__file__).parents[1] / "scenarios" / "narrow-lane-thief.gsc"
_BENCHMARK_FIXTURES = sorted(
    (Path(__file__).parents[1] / "scenarios").glob("benchmark-*.gsc")
)
_PATHOLOGICAL_FIXTURES = sorted(
    (Path(__file__).parents[1] / "scenarios").glob("pathological-*.gsc")
)
_TEN_DRAGONS = (
    Path(__file__).parents[1] / "scenarios" / "pathological-ten-dragons.gsc"
)
_ROM_PATH = _rom_dir()
requires_roms = pytest.mark.skipif(
    not (
        _ROM_PATH.is_dir()
        and (_ROM_PATH / SLAPSTIC_ROMS[0]).is_file()
        and (_ROM_PATH / TILE_ROMS[0][0]).is_file()
    ),
    reason=f"ROM files not available at {_ROM_PATH}",
)


def _prepared_workload(name: str) -> GameState:
    workload = WORKLOAD_BY_NAME[name]
    fixture = Path(__file__).parents[1] / "scenarios" / workload.scenario_filename
    state = build_synthetic_state(load_synthetic_scenario(fixture))
    prepare_workload_state(state, workload)
    return state


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


@pytest.mark.parametrize("fixture", _BENCHMARK_FIXTURES, ids=lambda path: path.stem)
def test_benchmark_fixtures_are_exact_versioned_32_by_32_scenarios(fixture):
    scenario = load_synthetic_scenario(fixture)

    assert len(scenario.grid) == 32
    assert {len(row) for row in scenario.grid} == {32}
    assert scenario.initial_input == JOY_IDLE
    assert scenario.events


@pytest.mark.parametrize(
    "fixture", _PATHOLOGICAL_FIXTURES, ids=lambda path: path.stem,
)
def test_pathological_fixtures_are_exact_versioned_32_by_32_scenarios(fixture):
    scenario = load_synthetic_scenario(fixture)

    assert len(scenario.grid) == 32
    assert {len(row) for row in scenario.grid} == {32}
    assert scenario.initial_input == JOY_IDLE


def test_seed_override_updates_scenario_content_and_provenance():
    scenario = load_synthetic_scenario(_BENCHMARK_FIXTURES[0])

    overridden = override_synthetic_seed(scenario, 0x1234)

    assert overridden.seed == 0x1234
    assert "\nseed = 4660\n" in overridden.canonical_content
    assert overridden.sha256 != scenario.sha256
    assert overridden.source_name == scenario.source_name


@requires_roms
def test_pathological_ten_dragons_preserves_the_singleton_contention():
    state = build_synthetic_state(load_synthetic_scenario(_TEN_DRAGONS))
    dragon_slots = [
        slot for slot in range(len(state.mobs.link))
        if state.mobs.obj_type(slot) == int(MazeObjIds.MONST_DRAGON)
    ]
    linked_anchors = [slot for slot in dragon_slots if state.mobs.is_linked(slot)]

    assert len(dragon_slots) == 40
    assert len(linked_anchors) == 10
    assert state.dragon_mob_slot == linked_anchors[-1]
    assert state.dragon_seg_mob_ids == [
        state.dragon_mob_slot,
        state.dragon_mob_slot - 0x20,
        state.dragon_mob_slot + 1,
        state.dragon_mob_slot - 0x1F,
    ]


@requires_roms
def test_projectile_contention_starts_with_four_players_and_all_twelve_channels():
    state = _prepared_workload("pathological-projectile-channels")

    assert all(player.active for player in state.players)
    assert all(
        state.mobs.picture[slot] not in (0, 0x8000)
        for slot in range(1, 13)
    )
    for _ in range(20):
        apply_synthetic_events(state)
        tick(state)
        assert sum(
            state.mobs.picture[slot] not in (0, 0x8000)
            for slot in range(1, 13)
        ) >= 11


@requires_roms
def test_dense_and_pathological_workloads_start_with_their_focus_on_screen():
    cases = (
        ("benchmark-generators", GENERATOR_TYPES, 81, 20),
        ("benchmark-mobs", MONSTER_TYPES, 196, 42),
        ("pathological-ten-dragons", (int(MazeObjIds.MONST_DRAGON),), 10, 10),
        ("pathological-projectile-channels", MONSTER_TYPES, 8, 8),
        ("pathological-boxed-generators", GENERATOR_TYPES, 6, 6),
    )

    for name, object_types, expected_count, expected_visible in cases:
        state = _prepared_workload(name)
        slots = [
            slot for slot in state.mobs.iter_chain()
            if state.mobs.obj_type(slot) in object_types
        ]
        assert len(slots) == expected_count
        assert sum(tile_on_screen_d4(state, slot) for slot in slots) >= expected_visible


@requires_roms
def test_four_player_workload_moves_fires_and_casts_with_every_hero():
    state = _prepared_workload("pathological-four-players")
    starts = [
        (state.mobs.hpos[player.mob_slot], state.mobs.vpos[player.mob_slot])
        for player in state.players
    ]
    moved = [False] * 4
    fired = [False] * 4

    for _ in range(510):
        apply_synthetic_events(state)
        tick(state)
        for index, player in enumerate(state.players):
            moved[index] |= (
                state.mobs.hpos[player.mob_slot],
                state.mobs.vpos[player.mob_slot],
            ) != starts[index]
            fired[index] |= state.mobs.picture[index + 1] not in (0, 0x8000)

    assert all(moved)
    assert all(fired)
    assert [player.potionsnum for player in state.players] == [17] * 4


@requires_roms
def test_pathological_setup_shapes_match_their_claimed_edge_cases():
    saturated = _prepared_workload("pathological-slot-saturation")
    assert len(list(saturated.mobs.iter_chain())) == 899

    four_players = _prepared_workload("pathological-four-players")
    assert all(player.active and player.potionsnum == 20 for player in four_players.players)

    boxed = _prepared_workload("pathological-boxed-generators")
    generators = [
        slot for slot in boxed.mobs.iter_chain()
        if boxed.mobs.obj_type(slot) in GENERATOR_TYPES
    ]
    assert len(generators) == 6
    assert all(
        boxed.mobs.picture[neighbor] == 0x8000
        for slot in generators
        for neighbor in (slot - 0x21, slot - 0x20, slot - 0x1F, slot - 1,
                         slot + 1, slot + 0x1F, slot + 0x20, slot + 0x21)
    )

    overlap = _prepared_workload("pathological-overlapping-specials")
    dragon_slots = [
        slot for slot in range(len(overlap.mobs.link))
        if overlap.mobs.obj_type(slot) == int(MazeObjIds.MONST_DRAGON)
    ]
    assert len(dragon_slots) == 6
    assert sum(overlap.mobs.is_linked(slot) for slot in dragon_slots) == 2

    walls = _prepared_workload("pathological-wall-intersection")
    assert walls.cyclic_wall_setup_ready
    assert walls.random_wall_setup_ready
    assert walls.forcefield_segment_table

    wrapped = _prepared_workload("pathological-wrap-seams")
    assert wrapped.wrap_h and wrapped.wrap_v

    counter = _prepared_workload("pathological-counter-wrap")
    assert counter.frame_counter == 0xFFF0


@requires_roms
@pytest.mark.parametrize(
    "fixture", _PATHOLOGICAL_FIXTURES, ids=lambda path: path.stem,
)
def test_pathological_workloads_complete_their_scripted_duration(fixture):
    workload = WORKLOAD_BY_NAME[fixture.stem]
    scenario = load_synthetic_scenario(fixture)
    state = build_synthetic_state(scenario)
    prepare_workload_state(state, workload)

    for _ in range(scenario.default_frames):
        apply_synthetic_events(state)
        tick(state)
        validate_runtime_invariants(
            state, workload=workload.name, frame=state.frame_counter,
        )


@pytest.mark.parametrize(
    ("controls", "expected"),
    [
        ("fire", JOY_IDLE & ~JOY_FIRE_BIT),
        ("right+fire", JOY_IDLE & ~JOY_RIGHT & ~JOY_FIRE_BIT),
        ("up-left+magic", 0xFFFF & ~0x80 & ~0x20 & ~JOY_MAGIC_BIT),
        ("fire+magic", JOY_IDLE & ~JOY_FIRE_BIT & ~JOY_MAGIC_BIT),
        ("live", None),
    ],
)
def test_scripted_input_supports_directions_and_action_buttons(controls, expected):
    assert _input_word(controls) == expected


def test_scripted_input_can_drive_all_four_players_independently():
    scenario = load_synthetic_scenario(
        next(
            fixture for fixture in _PATHOLOGICAL_FIXTURES
            if fixture.stem == "pathological-four-players"
        )
    )
    state = GameState()
    attach_synthetic_runtime(state, SyntheticScenarioRuntime(scenario))

    apply_synthetic_events(state)

    assert state.player_input_raw == [0xFFBF, 0xFFDF, 0xFFEF, 0xFF7F]
    page = DEBUG_PAGES.index("SCENARIO")
    rows = dict(debug_page_lines(capture_debug_snapshot(state), page))
    assert rows["INPUT"] == "D"
    assert rows["INPUT P4"] == "U"


@pytest.mark.parametrize("controls", ["left+right", "idle+up", "fire+fire", "live+fire"])
def test_scripted_input_rejects_ambiguous_combinations(controls):
    with pytest.raises(SyntheticScenarioError):
        _input_word(controls)


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
        "T-00200 @01200 activate_thief 1 16 mugger"
    )
    assert fired["EVENTS"] == "1/1 fired"
    assert fired["EVT 00"].startswith(
        "FIRED @01200 activate_thief 1 16 mugger"
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
        parse_synthetic_scenario(
            text.replace(
                "#..............................#",
                "#x.............................#",
                1,
            )
        )
    with pytest.raises(SyntheticScenarioError, match="row 0"):
        parse_synthetic_scenario(text.replace("################################", ".###############################", 1))


def test_parser_rejects_arbitrary_event_actions():
    text = _EXAMPLE.read_text(encoding="utf-8")
    text = text.replace(
        "1200 activate_thief 1 16 mugger",
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


def test_parser_rejects_multiple_prearmed_thief_events():
    text = _EXAMPLE.read_text(encoding="utf-8").replace(
        "1200 activate_thief 1 16 mugger",
        "600 activate_thief 1 16 thief\n1200 activate_thief 1 16 mugger",
    )

    with pytest.raises(SyntheticScenarioError, match="only one activate_thief"):
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
    assert state.random_wall_setup_ready
    assert synthetic_runtime_for(state) is not None


@requires_roms
def test_scheduled_mugger_deploys_at_the_absolute_frame():
    state = build_synthetic_state(load_synthetic_scenario(_EXAMPLE))
    assert state.thief_victim == 0
    assert state.thief_enter_time == 1200
    for _ in range(1201):
        apply_synthetic_events(state)
        tick(state)

    assert state.thief_current_pos
    assert state.thief_mode & THIEF_IS_MUGGER
    assert synthetic_runtime_for(state).fired_events == {0}

    start_y = vpos_y(state.mobs.vpos[state.thief_mob_slot])
    for _ in range(70):
        tick(state)
    assert vpos_y(state.mobs.vpos[state.thief_mob_slot]) > start_y


@requires_roms
def test_player_movement_before_spawn_extends_the_armed_pursuit_route():
    state = build_synthetic_state(load_synthetic_scenario(_EXAMPLE))
    player = state.players[0]
    old_slot = player.mob_slot
    assert path_grid_get_direction(state, old_slot) == 8
    state.player_input_raw[0] = JOY_IDLE & ~JOY_RIGHT

    for _ in range(10):
        apply_synthetic_events(state)
        tick(state)
        if state.players[0].mob_slot != old_slot:
            break

    assert state.players[0].mob_slot != old_slot
    assert path_grid_get_direction(state, old_slot) == 2


@requires_roms
def test_pending_scheduled_event_survives_state_dump_resume():
    state = build_synthetic_state(load_synthetic_scenario(_EXAMPLE))
    state.frame_counter = 1200
    state.thief_enter_time = 0
    restored = game_state_from_payload(
        json.loads(json.dumps(state_dump_payload(state)))
    )

    apply_synthetic_events(restored)
    tick(restored)

    assert restored.thief_current_pos
    assert restored.thief_mode & THIEF_IS_MUGGER
    assert synthetic_runtime_for(restored).fired_events == {0}


def test_state_dump_embeds_self_contained_synthetic_provenance_and_runtime():
    scenario = load_synthetic_scenario(_EXAMPLE)
    state = GameState()
    runtime = SyntheticScenarioRuntime(scenario, fired_events={0})
    runtime.current_input = None
    runtime.additional_inputs = [0xFFED, None, 0xFF7D]
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
    assert restored_runtime.additional_inputs == [0xFFED, None, 0xFF7D]


def test_state_dump_rejects_tampered_synthetic_content():
    scenario = load_synthetic_scenario(_EXAMPLE)
    state = GameState()
    attach_synthetic_runtime(state, SyntheticScenarioRuntime(scenario))
    payload = state_dump_payload(state)
    payload["synthetic_scenario"]["content"] += "; changed\n"

    with pytest.raises(StateDumpError, match="hash mismatch"):
        game_state_from_payload(payload)
