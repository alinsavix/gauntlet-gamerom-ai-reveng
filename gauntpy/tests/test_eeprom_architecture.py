"""EEPROM transport boundaries; game timing remains owned by the ROM model."""

from __future__ import annotations

import ast
from dataclasses import fields
import inspect
import json
from pathlib import Path

import pytest

from gauntpy.game import eeprom_device
from gauntpy.game.eeprom_device import EepromImage, EepromRotation, MemoryEepromStorage
from gauntpy.host.eeprom import (
    FileEepromStorage,
    PersistencePolicy,
    bind_eeprom_storage,
)
from gauntpy.game.state import GameState
from gauntpy.game.subsystems import eeprom


@pytest.mark.parametrize("module", [eeprom, eeprom_device])
def test_device_and_rom_model_do_not_import_host_transport(module):
    tree = ast.parse(inspect.getsource(module))
    forbidden = {"host", "json", "pathlib", "os", "sys"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        else:
            continue
        assert not any(forbidden.intersection(name.split(".")) for name in names)
    assert "eeprom_save_path" not in inspect.getsource(module)
    assert "eeprom_persistence_enabled" not in inspect.getsource(module)


def test_default_devices_are_per_state_and_not_modeled_fields(tmp_path):
    left = GameState(eeprom_save_path=str(tmp_path / "unused.json"))
    right = GameState(eeprom_save_path=left.eeprom_save_path)
    assert isinstance(left.eeprom_storage, MemoryEepromStorage)
    assert left.eeprom_storage is not right.eeprom_storage
    assert "eeprom_storage" not in {field.name for field in fields(left)}
    left.game_settings = 0x2345
    eeprom.eeprom_save_settings(left)
    eeprom.eeprom_load_settings(right)
    assert right.game_settings == eeprom.GAME_DEFAULT_SETTINGS
    assert not list(tmp_path.iterdir())


def test_memory_device_runs_load_save_and_periodic_without_files(monkeypatch):
    def forbidden_io(*args, **kwargs):
        pytest.fail("the EEPROM model attempted filesystem I/O")

    monkeypatch.setattr(Path, "read_text", forbidden_io)
    monkeypatch.setattr(Path, "write_text", forbidden_io)
    monkeypatch.setattr(Path, "mkdir", forbidden_io)
    state = GameState(eeprom_write_timer=1)
    eeprom.eeprom_load_settings(state)
    state.game_settings = 0x2345
    eeprom.eeprom_periodic_write(state)
    assert state.eeprom_write_timer == eeprom.EEPROM_WRITE_INTERVAL
    assert state.eeprom_settings_cache == 0x2345
    state.game_settings = 0
    eeprom.eeprom_load_settings(state)
    assert state.game_settings == 0x2345


def test_rom_normalization_is_identical_for_memory_input():
    state = GameState()
    state.eeprom_storage = MemoryEepromStorage(EepromImage(
        66666, 0x10002,
        (((0x1234567, "a1 "),), (), (), ()),
        EepromRotation(999, 0xFF, 7, 0xFF),
    ))
    eeprom.eeprom_load_settings(state)
    assert state.game_settings == 66666 & 0xFFFF
    assert state.eeprom_settings_cache == state.game_settings
    assert state.two_player_mode == 2
    assert state.high_scores == [[(0xFFFFFF, "A1 ")], [], [], []]
    assert (state.maze_number, state.maze_stride) == (5, 7)
    assert (state.treas_mazerand_num, state.treas_mazerand_adder) == (104, 3)


def test_file_transport_does_not_apply_rom_normalization(tmp_path):
    path = tmp_path / "eeprom.json"
    path.write_text(json.dumps({
        "game_settings": 66666,
        "two_player_mode": 0x10002,
        "high_scores": [[[0x1234567, "a1 "]], [], [], []],
        "rotation": {
            "maze_number": 999, "maze_stride": 255,
            "treas_mazerand_num": 7, "treas_mazerand_adder": 255,
        },
    }))
    assert FileEepromStorage(path, policy=PersistencePolicy.READ_ONLY).read() == EepromImage(
        66666, 0x10002, (((0x1234567, "a1 "),), (), (), ()),
        EepromRotation(999, 255, 7, 255),
    )


def test_storage_write_failure_propagates_without_updating_settings_shadow():
    class FailingStorage:
        def read(self):
            return None

        def write(self, image):
            raise OSError("device write failed")

    state = GameState(game_settings=0x2345, eeprom_write_timer=1)
    state.eeprom_storage = FailingStorage()
    with pytest.raises(OSError, match="device write failed"):
        eeprom.eeprom_periodic_write(state)
    assert state.eeprom_settings_cache == 0
    assert state.eeprom_write_timer == eeprom.EEPROM_WRITE_INTERVAL


@pytest.mark.parametrize("policy", [
    PersistencePolicy.READ_WRITE, PersistencePolicy.READ_ONLY,
])
def test_file_binding_reloads_external_operator_changes(tmp_path, policy):
    path = tmp_path / "eeprom.json"
    path.write_text('{"game_settings": 9029, "two_player_mode": 0}')
    state = bind_eeprom_storage(GameState(eeprom_save_path=str(path)), policy=policy)
    eeprom.eeprom_load_settings(state)
    assert state.game_settings == 9029
    path.write_text('{"game_settings": 57488, "two_player_mode": 1}')
    eeprom.eeprom_load_settings(state)
    assert state.game_settings == 57488
    assert state.two_player_mode == 1
    assert state.eeprom_settings_cache == 57488


def test_periodic_comparison_rereads_current_external_rotation(tmp_path, monkeypatch):
    path = tmp_path / "eeprom.json"
    state = bind_eeprom_storage(GameState(
        game_settings=0xE090, eeprom_settings_cache=0xE090,
        eeprom_save_path=str(path), eeprom_write_timer=1,
    ))
    eeprom.eeprom_save_settings(state)
    data = json.loads(path.read_text())
    data["rotation"]["maze_number"] = 25
    path.write_text(json.dumps(data))
    written = []
    monkeypatch.setattr(state.eeprom_storage, "write", written.append)
    eeprom.eeprom_periodic_write(state)
    assert len(written) == 1
    assert written[0].rotation.maze_number == 5


@pytest.mark.parametrize("exists", [False, True])
def test_read_only_policy_never_writes_and_does_not_freeze_timer(tmp_path, exists):
    path = tmp_path / "nested" / "eeprom.json"
    if exists:
        path.parent.mkdir()
        path.write_text('{"game_settings": 57488}')
    original = path.read_bytes() if exists else None
    state = bind_eeprom_storage(
        GameState(eeprom_save_path=str(path), eeprom_write_timer=2),
        policy=PersistencePolicy.READ_ONLY,
    )
    eeprom.eeprom_load_settings(state)
    state.game_settings = 0x2345
    eeprom.eeprom_periodic_write(state)
    assert state.eeprom_write_timer == 1
    eeprom.eeprom_periodic_write(state)
    eeprom.eeprom_save_settings(state)
    assert state.eeprom_write_timer == eeprom.EEPROM_WRITE_INTERVAL
    assert state.eeprom_settings_cache == 0x2345
    assert (path.read_bytes() if path.exists() else None) == original
    assert not path.with_name(path.name + ".tmp").exists()
    assert exists or not path.parent.exists()


def test_isolated_binding_neither_reads_nor_writes_external_image(tmp_path):
    path = tmp_path / "eeprom.json"
    path.write_text('{"game_settings": 57488}')
    state = GameState(game_settings=0x2345, eeprom_save_path=str(path))
    before = {field.name: getattr(state, field.name) for field in fields(state)}
    bind_eeprom_storage(state, policy=PersistencePolicy.ISOLATED)
    assert {field.name: getattr(state, field.name) for field in fields(state)} == before
    assert state.eeprom_storage.read().game_settings == 0x2345
    state.game_settings = 0x2468
    eeprom.eeprom_save_settings(state)
    eeprom.eeprom_load_settings(state)
    assert state.game_settings == 0x2468
    assert path.read_text() == '{"game_settings": 57488}'


def test_read_only_accepted_writes_are_visible_without_external_changes(tmp_path, monkeypatch):
    path = tmp_path / "eeprom.json"
    original = '{"game_settings": 57488}'
    path.write_text(original)
    state = bind_eeprom_storage(
        GameState(eeprom_save_path=str(path), eeprom_write_timer=1),
        policy=PersistencePolicy.READ_ONLY,
    )
    eeprom.eeprom_load_settings(state)
    state.game_settings = 0x2345
    state.maze_number = 25
    eeprom.eeprom_periodic_write(state)
    assert state.eeprom_settings_cache == 0x2345
    assert path.read_text() == original

    written = []
    monkeypatch.setattr(state.eeprom_storage, "write", written.append)
    state.eeprom_write_timer = 1
    eeprom.eeprom_periodic_write(state)
    assert written == [], "the accepted image must satisfy subsequent comparisons"
    state.game_settings = 0
    state.maze_number = 99
    eeprom.eeprom_load_settings(state)
    assert state.game_settings == 0x2345
    assert state.maze_number == 25
    assert path.read_text() == original


def test_disabled_legacy_configuration_selects_host_policy_not_timer_policy(tmp_path):
    path = tmp_path / "eeprom.json"
    original = '{"game_settings": 57488}'
    path.write_text(original)
    state = bind_eeprom_storage(GameState(
        eeprom_save_path=str(path), eeprom_persistence_enabled=False,
        eeprom_write_timer=2,
    ))
    assert state.eeprom_storage.policy is PersistencePolicy.READ_ONLY
    eeprom.eeprom_load_settings(state)
    state.game_settings = 0x2345
    eeprom.eeprom_periodic_write(state)
    assert state.eeprom_write_timer == 1
    eeprom.eeprom_periodic_write(state)
    assert state.eeprom_write_timer == eeprom.EEPROM_WRITE_INTERVAL
    assert state.eeprom_settings_cache == 0x2345
    state.game_settings = 0x2468
    eeprom.eeprom_save_settings(state)
    eeprom.eeprom_load_settings(state)
    assert state.game_settings == 0x2468
    assert path.read_text() == original


@pytest.mark.parametrize("payload", [
    "{broken", "[]", "null", "{}", '{"game_settings": "junk"}',
])
def test_corrupt_host_images_warn_and_report_unprogrammed_part(tmp_path, caplog, payload):
    path = tmp_path / "eeprom.json"
    path.write_text(payload)
    storage = FileEepromStorage(path, policy=PersistencePolicy.READ_WRITE)
    assert storage.read() is None
    assert "using factory settings" in caplog.text


def test_missing_image_is_an_unprogrammed_part_without_warning(tmp_path, caplog):
    storage = FileEepromStorage(
        tmp_path / "absent.json", policy=PersistencePolicy.READ_WRITE,
    )
    assert storage.read() is None
    assert not caplog.records


def test_invalid_optional_blocks_warn_but_preserve_valid_settings(tmp_path, caplog):
    path = tmp_path / "eeprom.json"
    path.write_text(json.dumps({
        "game_settings": 9029, "two_player_mode": [],
        "high_scores": False, "rotation": {},
    }))
    storage = FileEepromStorage(path, policy=PersistencePolicy.READ_WRITE)
    assert storage.read() == EepromImage(9029)
    assert len(caplog.records) == 3


def test_atomic_replace_failure_preserves_original_and_propagates(tmp_path, monkeypatch):
    path = tmp_path / "eeprom.json"
    original = '{"game_settings": 57488}'
    path.write_text(original)
    storage = FileEepromStorage(path, policy=PersistencePolicy.READ_WRITE)

    def fail_replace(self, target):
        raise PermissionError("replace denied")

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(PermissionError, match="replace denied"):
        storage.write(EepromImage(9029))
    assert path.read_text() == original
    assert sorted(item.name for item in tmp_path.iterdir()) == ["eeprom.json"]


def test_file_backend_rejects_isolated_policy(tmp_path):
    with pytest.raises(ValueError, match="MemoryEepromStorage"):
        FileEepromStorage(tmp_path / "eeprom.json", policy=PersistencePolicy.ISOLATED)


@pytest.mark.parametrize("image", [
    EepromImage(9029),
    EepromImage(9029, 1, ((), (), (), ()), EepromRotation(5, 0, 104, 0)),
])
def test_host_transport_round_trips_optional_blocks_without_warnings(tmp_path, caplog, image):
    storage = FileEepromStorage(tmp_path / "eeprom.json", policy=PersistencePolicy.READ_WRITE)
    storage.write(image)
    assert storage.read() == image
    assert not caplog.records
