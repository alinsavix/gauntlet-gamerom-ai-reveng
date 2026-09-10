"""Host orchestration contracts with no window, ROM setup, or wall-time waits."""

from __future__ import annotations

from collections import deque

import pytest

from gauntpy import performance
from gauntpy.host import application, shell
from gauntpy.host.eeprom import PersistencePolicy
from gauntpy.host.run_policy import BenchmarkRun, RunPolicy, StressRun
from gauntpy.host.session import HostSession
from gauntpy.performance_workloads import WORKLOADS
from gauntpy.state import GameState


class LoopHarness:
    paused = False
    treasure_timer_paused = False
    restart_level_requested = False
    last_render_time_ms = 3.25
    last_display_flip_time_ms = 0.75

    def __init__(self, monkeypatch, actions):
        self.actions = deque(actions)
        self.events = []
        self.states = []
        self.names = {}
        self.reports = []
        self.updates = []
        self.presented = []
        self.options = {}
        self.now = 0.0
        self.clock_values = None
        self.closed = False

        monkeypatch.setattr(application, "_ensure_rom_dir", lambda: None)
        monkeypatch.setattr(application, "perf_counter", self.clock)
        monkeypatch.setattr(application, "build_state", self.build_direct)
        monkeypatch.setattr(application, "_build_workload_state", self.build_workload)
        monkeypatch.setattr(application, "_build_stress_state", self.build_stress)
        monkeypatch.setattr(application, "bind_eeprom_storage", self.bind)
        monkeypatch.setattr(application, "tick", self.tick)
        monkeypatch.setattr(application, "validate_runtime_invariants", self.validate)
        monkeypatch.setattr(application, "_apply_operator_overrides", self.override)
        monkeypatch.setattr(application, "_enabled_sound_dir", self.sound_dir)
        monkeypatch.setattr(shell, "HostShell", self.open)
        monkeypatch.setattr(HostSession, "apply_events", self.apply_events)
        monkeypatch.setattr(HostSession, "capture_level_start", self.capture)

        original_report = performance.format_benchmark_report
        harness = self

        class Recorder(performance.BenchmarkRecorder):
            def add(self, **kwargs):
                harness.events.append("record")
                super().add(**kwargs)

        def report(recorder, **kwargs):
            self.events.append(f"report:{kwargs['workload']}")
            self.reports.append((kwargs["workload"], recorder))
            return original_report(recorder, **kwargs)

        monkeypatch.setattr(performance, "BenchmarkRecorder", Recorder)
        monkeypatch.setattr(performance, "format_benchmark_report", report)

    def clock(self):
        self.events.append("clock")
        if self.clock_values is not None:
            self.now = next(self.clock_values)
        else:
            self.now += 1.0
        return self.now

    def make_state(self, name):
        self.events.append(f"build:{name}")
        state = GameState()
        self.states.append(state)
        self.names[id(state)] = name
        return state

    def name(self, state):
        return self.names[id(state)]

    def build_direct(self, *_args, **_kwargs):
        return self.make_state("direct")

    def build_workload(self, workload, seed):
        assert seed == 17
        return self.make_state(workload.name)

    def build_stress(self, index, seed):
        state = self.build_workload(WORKLOADS[index], seed)
        state.eeprom_persistence_enabled = False
        return state

    def bind(self, state, *, policy=None):
        self.events.append(f"bind:{self.name(state)}:{policy}")
        if policy is PersistencePolicy.ISOLATED:
            assert state.eeprom_persistence_enabled is False

    def override(self, state, *, reduce_text):
        self.events.append(f"override:{self.name(state)}:{reduce_text}")

    def sound_dir(self, enabled):
        self.events.append(f"sound:{enabled}")
        return "recordings" if enabled else None

    def open(self, **kwargs):
        self.events.append("open")
        self.options = kwargs
        return self

    def skip_existing_audio(self, state):
        self.events.append(f"skip-audio:{self.name(state)}")

    def state_restored(self, state):
        self.events.append(f"restore:{self.name(state)}")
        self.treasure_timer_paused = False

    def wait_for_vblank(self, state):
        self.events.append(f"input:{self.name(state)}")
        if not self.actions:
            raise SystemExit
        action = self.actions.popleft()
        self.paused = action.get("paused", False)
        self.treasure_timer_paused = action.get("treasure_timer_paused", False)
        self.restart_level_requested = action.get("restart", False)

    def apply_events(self):
        self.events.append("events")

    def capture(self):
        self.events.append("checkpoint")

    def tick(self, state, *, treasure_timer_paused):
        self.events.append(f"tick:{self.name(state)}")
        self.updates.append((self.name(state), treasure_timer_paused))
        state.frame_counter += 1

    def validate(self, state, *, workload, frame):
        self.events.append(f"invariant:{workload}:{frame}")
        assert frame == state.frame_counter

    def present(self, state):
        self.events.append(f"present:{self.name(state)}")
        self.presented.append((self.name(state), state.frame_counter, self.paused))

    def close(self):
        self.events.append("close")
        self.closed = True


def _updated_iteration(name, frame, *, performance_mode=True):
    events = [
        "clock", "clock", f"input:{name}", "clock", "clock", "events",
        f"tick:{name}", "clock", "checkpoint",
    ]
    if performance_mode:
        events += ["clock", f"invariant:{name}:{frame}", "clock"]
    return [*events, f"present:{name}", "clock"]


def _paused_iteration(name):
    return [
        "clock", "clock", f"input:{name}", "clock", "clock",
        f"present:{name}", "clock",
    ]


@pytest.mark.parametrize(
    "benchmark_frames,stress_seconds", [(None, None), (1, None), (None, 2)],
)
@pytest.mark.parametrize("uncapped", [False, True])
@pytest.mark.parametrize("sound_enabled", [False, True])
def test_run_policy_keeps_acceleration_silent(
    benchmark_frames, stress_seconds, uncapped, sound_enabled,
):
    policy = RunPolicy(benchmark_frames, stress_seconds, uncapped, sound_enabled)
    performance_mode = benchmark_frames is not None or stress_seconds is not None
    assert policy.performance_mode is performance_mode
    assert policy.accelerated is (uncapped or performance_mode)
    assert policy.playback_enabled is (sound_enabled and not policy.accelerated)


@pytest.mark.parametrize("frames,warmup", [(1, 1), (30, 30), (31, 30), (600, 30)])
def test_warmup_counts_only_updated_frames_and_resets_per_workload(frames, warmup):
    run = BenchmarkRun(frames, WORKLOADS[:2])
    for remaining in range(warmup, 0, -1):
        assert not run.should_record(frame_updated=False)
        assert run.warmup_remaining == remaining
        assert not run.should_record(frame_updated=True)
    assert not run.should_record(frame_updated=False)
    assert run.should_record(frame_updated=True)
    assert run.advance_workload() is WORKLOADS[1]
    run.reset_recording()
    assert run.warmup_remaining == warmup
    assert run.recorder.frames == 0
    assert run.advance_workload() is None


def test_benchmark_loop_clock_boundaries_pause_and_workload_reset(monkeypatch):
    names = [workload.name for workload in WORKLOADS[:2]]
    monkeypatch.setattr(application, "selected_workloads", lambda _name: WORKLOADS[:2])
    harness = LoopHarness(
        monkeypatch,
        [{"paused": True}, {}, {}, {}, {"paused": True}, {}, {}, {}, {}, {}],
    )

    application.run(
        benchmark_frames=2, workload_name="all", rng_seed=17, scale=1,
        sound_enabled=True, reduce_text=True,
    )

    start = harness.events.index("clock")
    expected = _paused_iteration(names[0])
    for frame in range(1, 4):
        expected += _updated_iteration(names[0], frame)
    expected += ["record", *_paused_iteration(names[0])]
    expected += _updated_iteration(names[0], 4)
    expected += [
        "record", f"report:{names[0]}", f"build:{names[1]}",
        f"bind:{names[1]}:{PersistencePolicy.ISOLATED}", f"override:{names[1]}:True",
    ]
    for frame in range(1, 5):
        expected += _updated_iteration(names[1], frame)
        if frame > 2:
            expected.append("record")
    expected += [f"report:{names[1]}", "close"]
    assert harness.events[start:] == expected
    assert harness.options["sound_dir"] is None
    assert harness.options["uncapped"] is True
    assert [label for label, _ in harness.reports] == names
    for _, recorder in harness.reports:
        assert recorder.host_input_ms == [1000.0, 1000.0]
        assert recorder.game_update_ms == [1000.0, 1000.0]
        assert recorder.game_raster_ms == [3.25, 3.25]
        assert recorder.display_flip_ms == [0.75, 0.75]
        assert recorder.complete_loop_ms == [6000.0, 6000.0]
    assert all(not state.eeprom_persistence_enabled for state in harness.states)
    assert harness.closed


@pytest.mark.parametrize("uncapped", [False, True])
@pytest.mark.parametrize("sound_enabled", [False, True])
def test_normal_play_keeps_pause_input_and_presentation_order(
    monkeypatch, uncapped, sound_enabled,
):
    harness = LoopHarness(monkeypatch, [
        {"paused": True}, {"treasure_timer_paused": True},
    ])

    application.run(uncapped=uncapped, sound_enabled=sound_enabled)

    start = harness.events.index("clock")
    assert harness.events[start:] == [
        *_paused_iteration("direct"),
        *_updated_iteration("direct", 1, performance_mode=False),
        "clock", "clock", "input:direct", "close",
    ]
    assert harness.options["uncapped"] is uncapped
    assert harness.options["sound_dir"] == (
        "recordings" if sound_enabled and not uncapped else None
    )
    assert harness.updates == [("direct", True)]
    assert not harness.reports


@pytest.mark.parametrize(
    "workloads,indices,seconds,phase_seconds",
    [(WORKLOADS[:3], (0, 1, 2), 3.0, 1.0), (WORKLOADS[:1], (0,), 9.0, 2.0)],
)
def test_stress_schedule_advances_once_per_iteration_even_after_a_stall(
    workloads, indices, seconds, phase_seconds,
):
    run = StressRun(seconds, workloads, indices, started=100.0)
    assert run.phase_seconds == phase_seconds
    assert not run.advance_if_due(phase_seconds - 0.001)
    for phase in range(1, 5):
        assert run.advance_if_due(20.0)
        assert run.phase == phase % len(workloads)
        assert run.phase_index == indices[phase % len(indices)]
        assert run.next_phase_at == phase_seconds * (phase + 1)


def test_stress_clock_schedule_rotates_before_input_and_counts_paused_frames(
    monkeypatch, capsys,
):
    selected = WORKLOADS[1:4]
    names = [workload.name for workload in selected]
    monkeypatch.setattr(application, "selected_workloads", lambda _name: selected)
    harness = LoopHarness(monkeypatch, [{}, {"paused": True}, {}, {}])
    harness.clock_values = iter([
        100.0,
        *([100.0] * 8),
        *([100.75] * 5),
        *([100.75] * 8),
        *([100.9] * 8),
        101.2,
    ])

    application.run(stress_seconds=1.2, rng_seed=17, reduce_text=True, sound_enabled=True)

    def switch(name):
        return [
            f"build:{name}", f"bind:{name}:{PersistencePolicy.ISOLATED}",
            f"override:{name}:True",
        ]

    start = harness.events.index("clock")
    expected = ["clock", *_updated_iteration(names[0], 1)]
    paused = _paused_iteration(names[1])
    expected += [paused[0], *switch(names[1]), *paused[1:]]
    expected += _updated_iteration(names[1], 1)
    updated = _updated_iteration(names[2], 1)
    expected += [updated[0], *switch(names[2]), *updated[1:]]
    expected += ["clock", "close"]
    assert harness.events[start:] == expected
    assert harness.presented == [
        (names[0], 1, False), (names[1], 0, True),
        (names[1], 1, False), (names[2], 1, False),
    ]
    assert not harness.actions
    assert harness.options["sound_dir"] is None
    assert harness.options["uncapped"] is True
    assert "4 frames in 1.200 seconds" in capsys.readouterr().out


@pytest.mark.parametrize("paused", [False, True])
def test_restart_is_presented_without_tick_or_timing_tail(monkeypatch, paused):
    harness = LoopHarness(monkeypatch, [
        {"restart": True, "paused": paused, "treasure_timer_paused": True},
        {"paused": paused, "treasure_timer_paused": True},
    ])
    restored = harness.make_state("restored")

    def restart(session):
        harness.events.append("restart")
        assert session.restart_enabled
        session.state = restored
        return True

    monkeypatch.setattr(HostSession, "restart_level", restart)
    application.run()

    start = harness.events.index("clock")
    expected = [
        "clock", "clock", "input:direct", "clock",
        "restart", "restore:restored", "present:restored",
    ]
    expected += (
        _paused_iteration("restored") if paused
        else _updated_iteration("restored", 1, performance_mode=False)
    )
    expected += ["clock", "clock", "input:restored", "close"]
    assert harness.events[start:] == expected
    assert harness.updates == ([] if paused else [("restored", True)])
    assert harness.presented[0] == ("restored", 0, paused)
    assert not harness.restart_level_requested
    assert harness.closed


def test_performance_restart_request_is_consumed_without_restoring(monkeypatch, capsys):
    harness = LoopHarness(monkeypatch, [{"restart": True}, {}])
    monkeypatch.setattr(
        application, "validate_runtime_invariants",
        lambda *_args, **_kwargs: None,
    )
    application.run(benchmark_frames=1)
    assert len(harness.updates) == 2
    assert not harness.restart_level_requested
    assert "level restart unavailable" in capsys.readouterr().out
    assert not any(event.startswith("restore:") for event in harness.events)


@pytest.mark.parametrize("benchmark_frames", [None, 1])
def test_application_cold_boot_keeps_preboot_policy_and_postboot_isolation(
    monkeypatch, benchmark_frames,
):
    harness = LoopHarness(monkeypatch, [])
    policies = []

    def cold_boot(seed, *, persistence_policy):
        assert seed == 17
        policies.append(persistence_policy)
        return harness.make_state("cold-boot")

    monkeypatch.setattr(application, "build_cold_boot_state", cold_boot)
    application.run(from_attract=True, benchmark_frames=benchmark_frames, rng_seed=17)
    assert policies == [
        PersistencePolicy.READ_WRITE if benchmark_frames is None
        else PersistencePolicy.READ_ONLY,
    ]
    binds = [event for event in harness.events if event.startswith("bind:")]
    assert binds == (
        [] if benchmark_frames is None
        else [f"bind:cold-boot:{PersistencePolicy.ISOLATED}"]
    )


@pytest.mark.parametrize("benchmark_frames", [None, 1])
def test_resume_preserves_device_and_skips_historical_audio_before_first_input(
    monkeypatch, benchmark_frames,
):
    from gauntpy.host import state_dump

    harness = LoopHarness(monkeypatch, [{"paused": True}])
    state = harness.make_state("resumed")
    state.frame_counter = 37
    state.eeprom_persistence_enabled = False
    device = state.eeprom_storage
    monkeypatch.setattr(state_dump, "load_game_state", lambda _path: state)
    application.run(load_state_path="saved-state.json", benchmark_frames=benchmark_frames)

    assert state.eeprom_storage is device
    assert harness.presented == [("resumed", 37, True)]
    assert not harness.updates
    assert not any(event.startswith("bind:") for event in harness.events)
    assert harness.events.index("skip-audio:resumed") < harness.events.index("checkpoint")
    assert harness.events.index("checkpoint") < harness.events.index("input:resumed")


@pytest.mark.parametrize("benchmark_frames", [None, 1])
def test_synthetic_start_is_isolated_without_resume_audio_skip(
    monkeypatch, benchmark_frames,
):
    from gauntpy import custom_scenario

    harness = LoopHarness(monkeypatch, [{"paused": True}])
    scenario = object()
    monkeypatch.setattr(
        custom_scenario, "load_synthetic_scenario", lambda _path: scenario,
    )

    def build(selected):
        assert selected is scenario
        return harness.make_state("synthetic")

    monkeypatch.setattr(custom_scenario, "build_synthetic_state", build)
    application.run(scenario_path="fixture.gsc", benchmark_frames=benchmark_frames)

    assert harness.presented == [("synthetic", 0, True)]
    assert [event for event in harness.events if event.startswith("bind:")] == [
        f"bind:synthetic:{PersistencePolicy.ISOLATED}",
    ]
    assert not any(event.startswith("skip-audio:") for event in harness.events)
    assert not harness.states[0].eeprom_persistence_enabled


def test_invariant_failure_closes_host_without_presentation(monkeypatch):
    harness = LoopHarness(monkeypatch, [{}])

    def invalid(*_args, **_kwargs):
        raise RuntimeError("inconsistent workload")

    monkeypatch.setattr(application, "validate_runtime_invariants", invalid)
    with pytest.raises(RuntimeError, match="inconsistent workload"):
        application.run(benchmark_frames=1)
    assert harness.events[-3:] == ["checkpoint", "clock", "close"]
    assert not harness.presented
    assert harness.closed
