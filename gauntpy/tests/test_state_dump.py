"""Complete host-only state dump contracts."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from gauntpy.eeprom_device import EepromImage, EepromRotation, MemoryEepromStorage
from gauntpy.host.eeprom import bind_eeprom_storage
from gauntpy.state import GameState
from gauntpy.host.state_dump import (
    StateDumpError,
    dump_game_state,
    game_state_from_payload,
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
    assert payload["eeprom"] == {"schema": 1, "image": None}
    assert "eeprom_storage" not in dumped
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
    del payload["eeprom"]
    for name in (
        "hurt_speech_timer",
        "random_pickups_setup_done",
        "playfield_color_latch",
        "playfield_color_base",
        "eeprom_persistence_enabled",
        "dialog_once_flags",
    ):
        del payload["state"][name]
    for player in payload["state"]["players"]:
        del player["damage_sample_count"]
        player["cumulative_damage"] = 1234
    payload["state"]["playfield_color_ram"][8] = 0x2468
    path = tmp_path / "original-schema-one.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    restored = load_game_state(path)

    assert restored.hurt_speech_timer == [0] * 4
    assert restored.playfield_color_base == 0x2468
    assert restored.playfield_color_latch == 0x2468
    assert restored.eeprom_persistence_enabled is False
    assert restored.dialog_once_flags == 0
    assert all(player.damage_sample_count == 0 for player in restored.players)
    assert all(player.cumulative_damage == 0 for player in restored.players)


def test_load_ignores_retired_host_message_suppression_field(tmp_path):
    payload = state_dump_payload(GameState())
    payload["state"]["suppress_first_encounter_messages"] = True
    path = tmp_path / "retired-host-option.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    restored = load_game_state(path)

    assert not hasattr(restored, "suppress_first_encounter_messages")


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

    external = tmp_path / "eeprom.json"
    original = '{"game_settings": 57488}'
    external.write_text(original)
    source = bind_eeprom_storage(GameState(eeprom_save_path=str(external)))
    state = load_game_state(dump_game_state(source, tmp_path))
    state.eeprom_write_timer = 2
    state.game_settings = 1
    writes = []
    save = eeprom.eeprom_save_settings

    def observe_save(value):
        writes.append(value.game_settings)
        save(value)

    monkeypatch.setattr(eeprom, "eeprom_save_settings", observe_save)

    eeprom.eeprom_periodic_write(state)
    assert state.eeprom_write_timer == 1
    eeprom.eeprom_periodic_write(state)

    assert writes == [1]
    assert state.eeprom_write_timer == eeprom.EEPROM_WRITE_INTERVAL
    assert state.eeprom_settings_cache == 1
    assert state.eeprom_storage.read().game_settings == 1
    state.game_settings = 2
    eeprom.eeprom_save_settings(state)
    assert state.eeprom_storage.read().game_settings == 2
    assert external.read_text() == original


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


def test_snapshot_preserves_device_image_distinct_from_live_ram(tmp_path):
    from gauntpy.subsystems.eeprom import eeprom_load_settings

    image = EepromImage(
        0x2345, 0, (((12345, "ABC"),), (), (), ()),
        EepromRotation(55, 2, 110, 3),
    )
    state = GameState(game_settings=0x2468, maze_number=99, two_player_mode=1)
    state.high_scores[0] = [(99999, "RAM")]
    state.eeprom_storage = MemoryEepromStorage(image)
    before = state_dump_payload(state)["state"]
    restored = load_game_state(dump_game_state(state, tmp_path))

    assert restored.eeprom_storage is not state.eeprom_storage
    assert restored.eeprom_storage.read() == image
    assert restored.game_settings == 0x2468
    assert restored.maze_number == 99
    assert restored.high_scores[0] == [(99999, "RAM")]
    before["eeprom_persistence_enabled"] = False
    assert state_dump_payload(restored)["state"] == before

    eeprom_load_settings(restored)
    assert restored.game_settings == 0x2345
    assert restored.two_player_mode == 0
    assert restored.maze_number == 55
    assert restored.high_scores[0] == [(12345, "ABC")]


@pytest.mark.parametrize("image", [
    None,
    EepromImage(66666),
    EepromImage(
        66666, -1, (((0x1234567, "a1 "),), (), (), ()),
        EepromRotation(999, 255, 7, 255),
    ),
])
def test_snapshot_round_trips_exact_device_values_without_normalization(tmp_path, image):
    state = GameState(game_settings=0x2468)
    state.eeprom_storage = MemoryEepromStorage(image)
    restored = load_game_state(dump_game_state(state, tmp_path))
    assert isinstance(restored.eeprom_storage, MemoryEepromStorage)
    assert restored.eeprom_storage.read() == image
    assert restored.game_settings == 0x2468


@pytest.mark.parametrize("legacy", [False, True])
def test_resume_never_reads_external_eeprom_or_calls_game_initializers(tmp_path, monkeypatch, legacy):
    from gauntpy.subsystems import boot, eeprom

    external = tmp_path / "eeprom.json"
    external.write_text('{"game_settings": 9029}')
    source = bind_eeprom_storage(GameState(
        game_settings=0x2468, eeprom_save_path=str(external),
    ))
    payload = state_dump_payload(source)
    if legacy:
        del payload["eeprom"]
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(json.dumps(payload))
    external.write_text('{"game_settings": 57488}')
    read_text = Path.read_text

    def protected_read(path, *args, **kwargs):
        assert path != external, "resume must never read external EEPROM"
        return read_text(path, *args, **kwargs)

    def forbidden_initializer(*args, **kwargs):
        pytest.fail("resume must not call EEPROM load or boot")

    monkeypatch.setattr(Path, "read_text", protected_read)
    monkeypatch.setattr(boot, "one_time_init", forbidden_initializer)
    monkeypatch.setattr(eeprom, "eeprom_load_settings", forbidden_initializer)
    restored = load_game_state(snapshot)
    assert isinstance(restored.eeprom_storage, MemoryEepromStorage)
    assert restored.eeprom_storage.read().game_settings == (0x2468 if legacy else 9029)
    assert restored.game_settings == 0x2468


def test_legacy_snapshot_seeds_isolated_device_from_reconstructed_ram():
    from gauntpy.subsystems.eeprom import eeprom_image

    state = GameState(
        game_settings=0x2345, two_player_mode=0, maze_number=47,
        maze_stride=3, treas_mazerand_num=110, treas_mazerand_adder=2,
    )
    state.high_scores[1] = [(98765, "OLD")]
    payload = state_dump_payload(state)
    del payload["eeprom"]
    restored = game_state_from_payload(payload)
    assert restored.eeprom_storage.read() == eeprom_image(state)


@pytest.mark.parametrize("envelope", [
    None, [], {}, {"schema": 1}, {"image": None},
    {"schema": 2, "image": None},
    {"schema": True, "image": None},
    {"schema": 1, "image": None, "path": "untrusted.json"},
    {"schema": 1, "image": []},
    {"schema": 1, "image": {"game_settings": 0}},
])
def test_malformed_eeprom_envelope_is_rejected(envelope):
    payload = state_dump_payload(GameState())
    payload["eeprom"] = envelope
    with pytest.raises(StateDumpError, match="invalid EEPROM snapshot"):
        game_state_from_payload(payload)


@pytest.mark.parametrize("changes", [
    {"game_settings": True},
    {"game_settings": "123"},
    {"two_player_mode": False},
    {"two_player_mode": "0"},
    {"high_scores": []},
    {"high_scores": [[[True, "ABC"]], [], [], []]},
    {"high_scores": [[[1, 2]], [], [], []]},
    {"rotation": {}},
    {"rotation": {
        "maze_number": 5, "maze_stride": 0, "treas_mazerand_num": 104,
        "treas_mazerand_adder": 0, "unknown": 1,
    }},
    {"rotation": {
        "maze_number": 5, "maze_stride": False, "treas_mazerand_num": 104,
        "treas_mazerand_adder": 0,
    }},
    {"unknown": 0},
])
def test_malformed_eeprom_snapshot_image_is_rejected(changes):
    payload = state_dump_payload(GameState())
    image = {
        "game_settings": 0, "two_player_mode": None,
        "high_scores": None, "rotation": None,
    }
    image.update(changes)
    payload["eeprom"] = {"schema": 1, "image": image}
    with pytest.raises(StateDumpError, match="invalid EEPROM snapshot"):
        game_state_from_payload(payload)
