"""Host rewinds preserve complete state; they are not arcade reset routines."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from gauntpy.constants import Character, GameMode, MazeObjIds, PlayerStatus
from gauntpy.custom_scenario import (
    SyntheticScenarioRuntime,
    attach_synthetic_runtime,
    build_synthetic_state,
    load_synthetic_scenario,
)
from gauntpy.eeprom_device import EepromImage, MemoryEepromStorage
from gauntpy.host import application, shell, startup
from gauntpy.host.eeprom import FileEepromStorage, PersistencePolicy
from gauntpy.host.session import HostSession
from gauntpy.host.state_dump import state_dump_payload
from gauntpy.mainloop import tick
from gauntpy.mob import MobTable
from gauntpy.state import GameState

from gex.roms import SLAPSTIC_ROMS, TILE_ROMS, _rom_dir

_ROM_PATH = _rom_dir()
requires_roms = pytest.mark.skipif(
    not (
        (_ROM_PATH / SLAPSTIC_ROMS[0]).is_file()
        and (_ROM_PATH / TILE_ROMS[0][0]).is_file()
    ),
    reason=f"ROM files not available at {_ROM_PATH}",
)
_SCENARIOS = Path(__file__).parents[1] / "scenarios"


def _ready_state():
    state = GameState(game_mode=GameMode.NORMAL)
    state.maze = SimpleNamespace(data={(3, 4): 49})
    state.players[0].status = int(PlayerStatus.ALIVE_HERE)
    state.players[0].mob_slot = 100
    state.level_players_active = 1
    state.random_pickups_setup_done = True
    state.thief_level_setup_done = True
    return state


def _contents(state):
    payload = state_dump_payload(state)
    payload.pop("captured_at_utc")
    return payload


def test_checkpoint_is_read_only_and_repeated_restores_are_independent():
    state = _ready_state()
    state.path_direction_grid[7] = 0xA5
    state.playfield_ram[22] = 0x1234
    state.alpha_ram[42] = 0x9234
    state.mob_color_ram[12] = 0x4567
    state.mobs.picture[100] = 0x789
    state.rng.seed = 0xBEEF
    state.eeprom_storage = MemoryEepromStorage(EepromImage(0xABCD))
    scenario = load_synthetic_scenario(_SCENARIOS / "benchmark-empty.gsc")
    attach_synthetic_runtime(state, SyntheticScenarioRuntime(scenario))
    session = HostSession(state)
    baseline = _contents(state)

    assert session.capture_level_start()
    assert _contents(state) == baseline
    for _ in range(3):
        current = session.state
        current.getrandom(100)
        current.maze.data.clear()
        current.playfield_ram[22] = 0
        current.alpha_ram[42] = 0
        current.mob_color_ram[12] = 0
        current.path_direction_grid[7] = 0
        current.mobs.picture[100] = 0
        current.players[0].keysnum = 8
        current.eeprom_storage.write(EepromImage(0x4321))
        session.synthetic.fired_events.add(0)
        session.synthetic.current_input = 0
        assert not session.capture_level_start()
        assert session.restart_level()
        assert session.state is not current
        assert _contents(session.state) == baseline


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("maze", None), ("game_mode", int(GameMode.DEMO)),
        ("level_start_pending", True), ("level_players_active", 0),
        ("random_pickups_setup_done", False), ("thief_level_setup_done", False),
    ],
)
def test_partial_setup_never_becomes_a_baseline(name, value):
    state = _ready_state()
    original = getattr(state, name)
    setattr(state, name, value)
    session = HostSession(state)
    assert not session.capture_level_start()
    assert not session.restart_level()
    setattr(state, name, original)
    assert session.capture_level_start()
    assert session.restart_level()


def test_new_mob_table_replaces_baseline_even_for_same_level_and_maze():
    state = _ready_state()
    session = HostSession(state)
    assert session.capture_level_start()
    state.mobs = MobTable()
    state.level_start_pending = True
    state.players[0].keysnum = 5
    assert not session.restart_level()
    assert not session.capture_level_start()
    state.level_start_pending = False
    assert session.capture_level_start()
    state.players[0].keysnum = 9
    assert session.restart_level()
    assert session.state.players[0].keysnum == 5


def test_resume_waits_for_a_new_level_not_a_midlevel_join():
    state = _ready_state()
    session = HostSession(state, resumed=True)
    assert not session.capture_level_start()
    assert not session.restart_level()
    state.level_players_active = 0
    assert not session.capture_level_start()
    state.level_players_active = 1
    assert not session.capture_level_start()
    state.mobs = MobTable()
    assert session.capture_level_start()
    assert session.restart_level()


def test_failed_level_acquisition_cannot_replace_the_checkpoint(monkeypatch):
    from gauntpy import maze

    state = _ready_state()
    session = HostSession(state)
    assert session.capture_level_start()
    baseline = _contents(state)

    def unavailable(*_args):
        raise maze.MazeError("no ROMs")

    monkeypatch.setattr(maze, "decode_maze", unavailable)
    assert not maze.reset_and_load_level(state, 2, maze_number=1)
    assert not session.capture_level_start()
    assert _contents(state) == baseline
    assert session.restart_level()
    assert _contents(session.state) == baseline


def test_rewind_never_reads_or_writes_the_live_eeprom_again(tmp_path, monkeypatch):
    from gauntpy.subsystems.eeprom import eeprom_periodic_write

    path = tmp_path / "operator.json"
    state = _ready_state()
    state.eeprom_storage = FileEepromStorage(path, policy=PersistencePolicy.READ_WRITE)
    state.eeprom_storage.write(EepromImage(0x1234))
    state.eeprom_write_timer = 1
    session = HostSession(state)
    assert session.capture_level_start()
    state.eeprom_storage.write(EepromImage(0x5678))
    external = path.read_bytes()

    def forbidden(*_args):
        pytest.fail("a restored state accessed external EEPROM")

    monkeypatch.setattr(FileEepromStorage, "read", forbidden)
    monkeypatch.setattr(FileEepromStorage, "write", forbidden)
    for _ in range(2):
        assert session.restart_level()
        restored = session.state
        assert isinstance(restored.eeprom_storage, MemoryEepromStorage)
        assert restored.eeprom_storage.read() == EepromImage(0x1234)
        eeprom_periodic_write(restored)
        assert restored.eeprom_write_timer != 1
        assert path.read_bytes() == external


@requires_roms
def test_direct_start_is_complete_and_replays_exact_ticks(monkeypatch):
    from gauntpy import maze
    from gauntpy.subsystems import boot, thief

    state = startup.build_state(16, Character.ELF, maze_number=15, rng_seed=1234)
    assert state.random_pickups_setup_done and state.thief_level_setup_done
    session = HostSession(state)
    assert session.capture_level_start()
    baseline = _contents(state)

    def forbidden(*_args, **_kwargs):
        pytest.fail("rewind reconstructed the level instead of restoring it")

    monkeypatch.setattr(maze, "load_level", forbidden)
    monkeypatch.setattr(boot, "one_time_init", forbidden)
    monkeypatch.setattr(thief, "thief_setup", forbidden)
    results = []
    for _ in range(2):
        assert session.restart_level()
        assert _contents(session.state) == baseline
        for frame in range(20):
            session.state.player_input_raw[0] = 0xFFEF if frame < 10 else 0xFFFD
            tick(session.state)
            assert not session.capture_level_start()
        results.append(_contents(session.state))
    assert results[0] == results[1]
    assert results[0]["state"]["rng"] != baseline["state"]["rng"]


def _advance_to_capture(session, limit=1000):
    for _ in range(limit):
        tick(session.state)
        if session.capture_level_start():
            return
    pytest.fail("level never reached complete playable setup")


@requires_roms
@pytest.mark.parametrize("transition", ["skip", "exit", "treasure", "secret"])
def test_natural_and_shortcut_transitions_capture_after_all_setup_tails(transition):
    from gauntpy.host.debug_controls import debug_force_secret_room, debug_skip_level
    from gauntpy.subsystems.exits import player_exit_sequence

    state = startup.build_state(12, Character.ELF, maze_number=11)
    state.level_next_treasure = 1 if transition == "treasure" else 4
    state.secret_trick_id = 0
    session = HostSession(state)
    assert session.capture_level_start()
    old_mobs = state.mobs
    if transition == "skip":
        assert debug_skip_level(state)
        assert not session.capture_level_start()
        assert not session.restart_level()
    else:
        if transition == "secret":
            assert debug_force_secret_room(state, 0)
        player_exit_sequence(state, 0, state.players[0].mob_slot, int(MazeObjIds.EXIT))
    _advance_to_capture(session)
    assert state.mobs is not old_mobs
    assert not state.level_start_pending
    assert state.random_pickups_setup_done and state.thief_level_setup_done
    assert state.players[0].active and state.players[0].mob_slot
    if transition == "secret":
        assert state.mazenum_current in (115, 116)
    elif transition == "treasure":
        assert 104 <= state.mazenum_current <= 114
    baseline = _contents(state)
    tick(state)
    assert session.restart_level()
    assert _contents(session.state) == baseline
    if transition in ("secret", "treasure"):
        room_level = session.state.levelnum_current
        room_mobs = session.state.mobs
        assert debug_skip_level(session.state)
        _advance_to_capture(session)
        assert session.state.levelnum_current == room_level
        assert session.state.mazenum_current < 104
        assert session.state.mobs is not room_mobs
        next_baseline = _contents(session.state)
        tick(session.state)
        assert session.restart_level()
        assert _contents(session.state) == next_baseline


@requires_roms
def test_attract_does_not_capture_demo_or_selection():
    state = startup.build_cold_boot_state(persistence_policy=PersistencePolicy.ISOLATED)
    session = HostSession(state)
    assert not session.capture_level_start()
    state.coin_counters = 1
    tick(state)
    assert not session.capture_level_start()
    state.player_input_raw[0] = 0xFFFE
    _advance_to_capture(session, 300)
    assert state.players[0].active
    baseline = _contents(state)
    assert session.restart_level()
    assert _contents(session.state) == baseline


@requires_roms
def test_synthetic_event_schedule_and_provenance_rewind_together():
    state = build_synthetic_state(
        load_synthetic_scenario(_SCENARIOS / "benchmark-empty.gsc"),
    )
    session = HostSession(state)
    assert session.capture_level_start()
    baseline = _contents(state)
    results = []
    for _ in range(2):
        for _ in range(5):
            session.apply_events()
            tick(session.state)
        assert session.synthetic.fired_events
        results.append(_contents(session.state))
        assert session.restart_level()
        assert _contents(session.state) == baseline
    assert results[0] == results[1]


@pytest.mark.parametrize("paused", [False, True])
def test_actual_shell_f11_restores_in_application_without_a_tick(monkeypatch, paused):
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setenv("SDL_AUDIODRIVER", "dummy")
    pygame = pytest.importorskip("pygame")
    state = _ready_state()
    state.alpha_ram[10] = 0x1234
    state.playfield_ram[20] = 0x5678
    state.sound_log[:] = [0x20]
    baseline = _contents(state)
    baseline["state"]["game_settings"] |= 0x0400
    seen = []
    audio_resets = []
    audio = SimpleNamespace(
        reset=lambda commands: audio_resets.append(tuple(commands)),
        close=lambda: None,
    )

    class TestShell(shell.HostShell):
        def __init__(self, **kwargs):
            super().__init__(audio_player=audio, **kwargs)
            self.paused = paused
            self.treasure_timer_paused = True
            self._diagnostics_previous = object()
            self._diagnostics_events.append("old event")
            self._render_times_ms.append(100.0)
            self.old_cache = self._cache

        def wait_for_vblank(self, current):
            current.alpha_ram[10] = 0
            current.playfield_ram[20] = 0
            current.rng.seed = 55
            pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F11))
            super().wait_for_vblank(current)

        def present(self, current):
            assert _contents(current) == baseline
            assert self.paused is paused
            assert not self.treasure_timer_paused
            assert self._diagnostics_previous is None
            assert not self._diagnostics_events
            assert not self._render_times_ms
            assert self._cache is not self.old_cache
            assert audio_resets == [(0x20,)]
            seen.append(current)
            raise SystemExit

    def forbidden(*_args, **_kwargs):
        pytest.fail("reset iteration must display the exact baseline without updating")

    monkeypatch.setattr(application, "_ensure_rom_dir", lambda: None)
    monkeypatch.setattr(application, "build_state", lambda *_args, **_kwargs: state)
    monkeypatch.setattr(application, "bind_eeprom_storage", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(application, "tick", forbidden)
    monkeypatch.setattr(shell, "HostShell", TestShell)
    application.run(uncapped=True, reduce_text=True)
    assert len(seen) == 1
    assert seen[0] is not state
