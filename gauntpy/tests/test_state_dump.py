"""Complete host-only state dump contracts."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from gauntpy.state import GameState
from gauntpy.render.state_dump import (
    StateDumpError,
    dump_game_state,
    load_game_state,
    state_dump_payload,
)


def test_payload_contains_complete_modeled_memory_without_mutating_state():
    state = GameState()
    state.frame_counter = 123
    state.rng.seed = 0x4567
    state.alpha_ram[7] = 0xABCD
    state.playfield_ram[11] = 0x1357
    state.mob_color_ram[13] = 0x2468
    state.mobs.picture[42] = 0x1E0D
    state.mobs.hpos[42] = 0x222C
    state.players[0].health = 999
    state.maze = SimpleNamespace(data={(3, 4): 2}, mazenum=16)
    before = (
        state.frame_counter,
        state.rng.seed,
        tuple(state.mobs.picture),
        tuple(state.alpha_ram),
    )

    payload = state_dump_payload(state)
    dumped = payload["state"]

    assert payload["schema"] == 1
    assert payload["frame"] == 123
    assert dumped["rng"]["seed"] == 0x4567
    assert dumped["alpha_ram"][7] == 0xABCD
    assert dumped["playfield_ram"][11] == 0x1357
    assert dumped["mob_color_ram"][13] == 0x2468
    assert dumped["mobs"]["picture"][42] == 0x1E0D
    assert dumped["mobs"]["hpos"][42] == 0x222C
    assert dumped["players"][0]["health"] == 999
    assert dumped["maze"]["data"] == [{"key": [3, 4], "value": 2}]
    assert before == (
        state.frame_counter,
        state.rng.seed,
        tuple(state.mobs.picture),
        tuple(state.alpha_ram),
    )


def test_dump_writes_parseable_unique_json_files(tmp_path):
    state = GameState(frame_counter=77)

    first = dump_game_state(state, tmp_path)
    second = dump_game_state(state, tmp_path)

    assert first != second
    assert json.loads(first.read_text(encoding="utf-8"))["frame"] == 77
    assert json.loads(second.read_text(encoding="utf-8"))["state"]["frame_counter"] == 77


def test_load_reconstructs_runtime_types_and_non_string_mapping_keys(tmp_path):
    state = GameState(frame_counter=77)
    state.rng.seed = 0xBEEF
    state.players[2].health = 1234
    state.mobs.picture[42] = 0x1E0D
    state.path_direction_grid[19] = 0xA5
    state.movable_wall_hits[42] = 0x800
    state.playfield_floor_catalog[(3, 4)] = (1, 2, 3, 4)
    state.playfield_wall_catalog[7] = (5, 6, 7, 8)
    state.playfield_forcefield_cells.add(99)
    state.high_scores[0] = [(12345, "AAA")]

    restored = load_game_state(dump_game_state(state, tmp_path))

    assert restored.frame_counter == 77
    assert restored.rng.seed == 0xBEEF
    assert restored.players[2].health == 1234
    assert restored.mobs.picture[42] == 0x1E0D
    assert restored.path_direction_grid == state.path_direction_grid
    assert restored.movable_wall_hits == {42: 0x800}
    assert restored.playfield_floor_catalog == {(3, 4): (1, 2, 3, 4)}
    assert restored.playfield_wall_catalog == {7: (5, 6, 7, 8)}
    assert restored.playfield_forcefield_cells == {99}
    assert restored.high_scores[0] == [(12345, "AAA")]


def test_load_accepts_legacy_bytearray_repr(tmp_path):
    payload = state_dump_payload(GameState())
    payload["state"]["path_direction_grid"] = {
        "type": "bytearray",
        "repr": "bytearray(b'\\x01\\x02')",
    }
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    restored = load_game_state(path)

    assert restored.path_direction_grid == bytearray((1, 2))


def test_load_migrates_original_schema_one_shape(tmp_path):
    payload = state_dump_payload(GameState())
    for name in (
        "hurt_speech_timer",
        "random_pickups_setup_done",
        "playfield_color_latch",
        "playfield_color_base",
        "eeprom_persistence_enabled",
        "dialog_once_flags",
    ):
        del payload["state"][name]
    payload["state"]["playfield_color_ram"][8] = 0x2468
    path = tmp_path / "original-schema-one.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    restored = load_game_state(path)

    assert restored.hurt_speech_timer == [0] * 4
    assert restored.playfield_color_base == 0x2468
    assert restored.playfield_color_latch == 0x2468
    assert restored.eeprom_persistence_enabled is False
    assert restored.dialog_once_flags == 0


def test_load_rejects_schema_one_fields_from_before_the_naming_policy(tmp_path):
    payload = state_dump_payload(GameState())
    current_name = "forcefield_hurt_timer"
    stale_name = "ff_" + "hurt_timer"
    payload["state"][stale_name] = payload["state"].pop(current_name)
    path = tmp_path / "stale-naming-policy.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(StateDumpError, match="GameState shape mismatch"):
        load_game_state(path)


def test_loaded_state_cannot_overwrite_external_eeprom(tmp_path, monkeypatch):
    from gauntpy.subsystems import eeprom

    state = load_game_state(dump_game_state(GameState(), tmp_path))
    state.eeprom_write_timer = 0
    state.game_settings = 1
    writes = []
    monkeypatch.setattr(eeprom, "eeprom_save_settings", lambda value: writes.append(value))

    eeprom.eeprom_periodic_write(state)

    assert writes == []
    assert state.eeprom_write_timer == 0


def test_load_rejects_unknown_schema_and_incomplete_state(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text('{"schema": 2, "state": {}}', encoding="utf-8")
    with pytest.raises(StateDumpError, match="unsupported saved-state schema"):
        load_game_state(path)

    payload = state_dump_payload(GameState())
    del payload["state"]["frame_counter"]
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(StateDumpError, match="missing fields: frame_counter"):
        load_game_state(path)

    payload = state_dump_payload(GameState())
    payload["state"]["rng"]["seed"] = "not-an-integer"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(StateDumpError, match="invalid saved-state value"):
        load_game_state(path)
