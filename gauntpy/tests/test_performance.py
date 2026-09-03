"""Host-only benchmark and stress-workload contracts."""

from __future__ import annotations

from pathlib import Path

import pytest

from gauntpy.performance import (
    BenchmarkRecorder,
    format_benchmark_report,
    stress_phase_index,
    summarize_timings,
)
from gauntpy.performance_workloads import (
    WORKLOADS,
    HarnessInvariantError,
    format_workload_catalog,
    scenario_path,
    validate_runtime_invariants,
)
from gauntpy.state import GameState


def test_timing_summary_uses_nearest_rank_p95():
    summary = summarize_timings([5.0, 1.0, 3.0, 2.0, 4.0])

    assert summary.samples == 5
    assert summary.minimum_ms == 1.0
    assert summary.median_ms == 3.0
    assert summary.mean_ms == 3.0
    assert summary.p95_ms == 5.0
    assert summary.maximum_ms == 5.0


def test_benchmark_report_names_each_measured_boundary():
    recorder = BenchmarkRecorder()
    recorder.add(
        host_input_ms=1.0,
        game_update_ms=2.0,
        game_raster_ms=3.0,
        presentation_ms=4.0,
        complete_loop_ms=7.0,
    )

    report = format_benchmark_report(recorder, scale=4)

    for label in (
        "host input", "game update", "game raster", "presentation",
        "complete loop", "throughput",
    ):
        assert label in report
    assert "1 frames at scale 4" in report


def test_benchmark_report_identifies_named_workload():
    recorder = BenchmarkRecorder()
    recorder.add(
        host_input_ms=1.0,
        game_update_ms=2.0,
        game_raster_ms=3.0,
        presentation_ms=4.0,
        complete_loop_ms=7.0,
    )

    assert "workload benchmark-mobs" in format_benchmark_report(
        recorder, scale=4, workload="benchmark-mobs",
    )


def test_workload_catalog_has_unique_names_and_existing_synthetic_fixtures():
    names = [workload.name for workload in WORKLOADS]
    pathological = {
        "pathological-ten-dragons",
        "pathological-slot-saturation",
        "pathological-projectile-channels",
        "pathological-four-players",
        "pathological-boxed-generators",
        "pathological-overlapping-specials",
        "pathological-wall-intersection",
        "pathological-wrap-seams",
        "pathological-counter-wrap",
    }

    assert len(names) == len(set(names))
    assert {"benchmark-empty", "benchmark-generators", "benchmark-mobs"} <= set(names)
    assert pathological <= set(names)
    assert all(
        workload.name == Path(workload.scenario_filename).stem
        for workload in WORKLOADS
        if workload.scenario_filename is not None
    )
    assert all(
        scenario_path(workload).is_file()
        for workload in WORKLOADS
        if workload.scenario_filename is not None
    )
    catalog = format_workload_catalog()
    assert all(name in catalog for name in names)


def test_runtime_invariants_accept_a_consistent_chain():
    state = GameState()
    state.mobs.create(65, 1, 0, 0, 18)
    state.mobs.create(98, 1, 0, 0, 19)

    validate_runtime_invariants(state, workload="unit", frame=7)


def test_runtime_invariants_report_first_duplicate_chain_slot():
    state = GameState()
    state.mobs.create(65, 1, 0, 0, 18)
    state.mobs.set_next(65, 65)

    with pytest.raises(
        HarnessInvariantError, match="unit frame 7: duplicate MOB chain slot 65",
    ):
        validate_runtime_invariants(state, workload="unit", frame=7)


def test_runtime_invariants_reject_a_slip_outside_the_chain():
    state = GameState()
    state.mobs.create(65, 1, 0, 0, 18)
    state.mobs.slip_heads[0] = 98

    with pytest.raises(HarnessInvariantError, match="SLIP 0 points outside"):
        validate_runtime_invariants(state, workload="unit", frame=7)


def test_stress_schedule_visits_every_phase_before_repeating():
    assert [
        stress_phase_index(second, 12.0, 6)
        for second in (0.0, 2.0, 4.0, 6.0, 8.0, 10.0, 12.0)
    ] == [0, 1, 2, 3, 4, 5, 0]


@pytest.mark.parametrize(
    ("seconds", "total", "phases"),
    ((1, 0, 1), (1, 1, 0)),
)
def test_stress_schedule_rejects_invalid_dimensions(seconds, total, phases):
    with pytest.raises(ValueError):
        stress_phase_index(seconds, total, phases)
