"""Host ownership, compatibility, and distinct startup lifecycle contracts."""

from __future__ import annotations

from dataclasses import fields
import importlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from gauntpy.custom_scenario import (
    SyntheticScenarioRuntime,
    attach_synthetic_runtime,
    load_synthetic_scenario,
    synthetic_runtime_for,
)
from gauntpy.host import application, startup
from gauntpy.host.session import HostSession
from gauntpy.host.state_dump import (
    game_state_from_payload,
    state_dump_payload,
)
from gauntpy.game.state import GameState


@pytest.mark.parametrize(
    ("legacy", "canonical", "names"),
    [
        ("play", "host.application", ("main", "run")),
        ("play", "host.startup", ("build_state",)),
        ("render.host", "host.shell", ("HostShell", "PygameUnavailable")),
        ("render.audio", "host.audio", ("StaticSoundPlayer", "SoundLibraryError")),
        (
            "render.diagnostics", "host.diagnostics",
            ("capture_debug_snapshot", "render_debug_panel", "DebugSnapshot"),
        ),
        (
            "render.debug_controls", "host.debug_controls",
            ("debug_add_key", "debug_skip_level", "debug_force_secret_room"),
        ),
        (
            "render.state_dump", "host.state_dump",
            ("state_dump_payload", "load_game_state", "game_state_from_payload"),
        ),
    ],
)
def test_legacy_imports_are_explicit_identity_preserving_exports(
    legacy, canonical, names,
):
    old = importlib.import_module(f"gauntpy.{legacy}")
    new = importlib.import_module(f"gauntpy.{canonical}")
    for name in names:
        assert getattr(old, name) is getattr(new, name)
        assert getattr(new, name).__module__ == f"gauntpy.{canonical}"


def test_headless_entry_points_do_not_import_pygame_or_gex():
    code = """
import importlib.abc
import sys
class NoOptionalRuntime(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'pygame', 'gex'}:
            raise AssertionError('headless import requested ' + fullname)
sys.meta_path.insert(0, NoOptionalRuntime())
import gauntpy.play
import gauntpy.scenarios
import gauntpy.custom_scenario
import gauntpy.host.session
import gauntpy.host.state_dump
assert 'pygame' not in sys.modules
assert 'gex' not in sys.modules
"""
    subprocess.run([sys.executable, "-c", code], check=True)


def test_session_is_caller_owned_without_changing_the_modeled_field_schema():
    state = GameState()
    before = state_dump_payload(state)["state"]
    scenario = load_synthetic_scenario(
        Path(__file__).parents[1] / "scenarios" / "benchmark-empty.gsc"
    )
    runtime = SyntheticScenarioRuntime(scenario)

    attach_synthetic_runtime(state, runtime)
    session = HostSession(state)

    assert session.state is state
    assert session.synthetic is runtime
    assert synthetic_runtime_for(state) is runtime
    assert "host_session" not in {field.name for field in fields(state)}
    assert not hasattr(state, "host_session")
    payload = state_dump_payload(state)
    assert payload["state"] == before
    assert payload["synthetic_scenario"]["sha256"] == scenario.sha256
    assert not hasattr(GameState(), "host_session")
    assert HostSession(state).synthetic is runtime


def test_cold_boot_seeds_once_before_the_real_boot_entry(monkeypatch):
    from gauntpy.game.subsystems import boot

    seen = []

    def initialize(state):
        seen.append(state.rng.seed)
        state.rng.seed = 0x1234
        state.frame_counter = 37

    monkeypatch.setattr(boot, "one_time_init", initialize)
    state = startup.build_cold_boot_state(0xBEEF)

    assert seen == [0xBEEF]
    assert state.rng.seed == 0x1234
    assert state.frame_counter == 37


def test_resume_reconstructs_runtime_without_any_game_initialization(monkeypatch):
    from gauntpy import custom_scenario
    from gauntpy.game import maze
    from gauntpy.game.subsystems import boot, display

    state = GameState(eeprom_persistence_enabled=False)
    state.frame_counter = 123
    state.rng.seed = 0xBEEF
    state.alpha_ram[42] = 0x8123
    state.playfield_ram[123] = 0x4567
    state.path_direction_grid[0] = 0xA5
    scenario = load_synthetic_scenario(
        Path(__file__).parents[1] / "scenarios" / "benchmark-empty.gsc"
    )
    runtime = SyntheticScenarioRuntime(scenario, fired_events={0})
    runtime.current_input = 0xFFF7
    attach_synthetic_runtime(state, runtime)
    payload = json.loads(json.dumps(state_dump_payload(state)))

    def forbidden(*_args, **_kwargs):
        pytest.fail("resume must not run a game initializer")

    for module, name in (
        (boot, "one_time_init"),
        (maze, "load_level"),
        (maze, "initialize_playfield_ram"),
        (display, "init_alpha_color_ram"),
        (startup, "build_state"),
        (startup, "spawn_player"),
        (custom_scenario, "build_synthetic_state"),
    ):
        monkeypatch.setattr(module, name, forbidden)

    restored = game_state_from_payload(payload)

    assert restored is not state
    assert state_dump_payload(restored)["state"] == payload["state"]
    session = HostSession(restored)
    assert session.synthetic is not runtime
    assert session.synthetic.fired_events == {0}
    assert session.synthetic.current_input == 0xFFF7
    assert not hasattr(restored, "host_session")


@pytest.mark.parametrize("paused", [False, True])
@pytest.mark.parametrize("benchmark_frames", [None, 1])
def test_resumed_application_skips_boot_and_honors_pause(
    monkeypatch, tmp_path, paused, benchmark_frames,
):
    from gauntpy.game.eeprom_device import EepromImage, MemoryEepromStorage
    from gauntpy.host import shell
    from gauntpy.game.subsystems import boot

    state = GameState(eeprom_persistence_enabled=False)
    device_image = EepromImage(0x2345)
    state.eeprom_storage = MemoryEepromStorage(device_image)
    state.frame_counter = 73
    state.sound_log[:] = [1, 2]
    path = tmp_path / "state.json"
    path.write_text(json.dumps(state_dump_payload(state)), encoding="utf-8")
    calls = []

    class FakeHost:
        treasure_timer_paused = False

        def __init__(self, **_kwargs):
            self.paused = paused

        def skip_existing_audio(self, current):
            calls.append(("audio", list(current.sound_log)))

        def wait_for_vblank(self, current):
            assert current.eeprom_storage.read() == device_image
            calls.append(("input", current.frame_counter))

        def present(self, current):
            calls.append(("present", current.frame_counter))
            raise SystemExit

        def close(self):
            calls.append(("close",))

    def forbidden(*_args, **_kwargs):
        pytest.fail("resumed paused frame must not initialize, tick, or fire events")

    def apply_events(session):
        calls.append(("events", session.state.frame_counter))

    def tick(current, **_kwargs):
        calls.append(("tick", current.frame_counter))
        current.frame_counter += 1

    monkeypatch.setattr(shell, "HostShell", FakeHost)
    monkeypatch.setattr(boot, "one_time_init", forbidden)
    monkeypatch.setattr(application, "build_state", forbidden)
    monkeypatch.setattr(application, "tick", forbidden if paused else tick)
    monkeypatch.setattr(
        HostSession, "apply_events", forbidden if paused else apply_events,
    )

    application.run(load_state_path=path, benchmark_frames=benchmark_frames)

    updates = [] if paused else [("events", 73), ("tick", 73)]
    assert calls == [
        ("audio", [1, 2]), ("input", 73), *updates,
        ("present", 73 if paused else 74), ("close",),
    ]


@pytest.mark.parametrize("read_only", [False, True])
def test_cold_boot_binds_host_storage_before_game_initialization(monkeypatch, read_only):
    from gauntpy.host.eeprom import FileEepromStorage, PersistencePolicy
    from gauntpy.game.subsystems import boot

    policy = PersistencePolicy.READ_ONLY if read_only else PersistencePolicy.READ_WRITE
    seen = []

    def initialize(state):
        assert isinstance(state.eeprom_storage, FileEepromStorage)
        seen.append(state.eeprom_storage.policy)

    monkeypatch.setattr(boot, "one_time_init", initialize)
    startup.build_cold_boot_state(persistence_policy=policy)
    assert seen == [policy]


def test_isolated_cold_boot_starts_with_an_unprogrammed_device(monkeypatch):
    from gauntpy.game.eeprom_device import MemoryEepromStorage
    from gauntpy.host.eeprom import FileEepromStorage, PersistencePolicy
    from gauntpy.game.subsystems.eeprom import game_difficulty

    def forbidden(*_args):
        pytest.fail("isolated cold boot accessed an external EEPROM image")

    monkeypatch.setattr(FileEepromStorage, "read", forbidden)
    state = startup.build_cold_boot_state(persistence_policy=PersistencePolicy.ISOLATED)
    assert isinstance(state.eeprom_storage, MemoryEepromStorage)
    assert state.game_settings == 0xE090
    assert state.eeprom_settings_cache == 0xE090
    assert game_difficulty(state) == 4
