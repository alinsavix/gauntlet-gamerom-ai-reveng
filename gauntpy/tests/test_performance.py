"""Host-only benchmark and stress-workload contracts."""

from __future__ import annotations

import pytest

from gauntpy.performance import (
    BenchmarkRecorder,
    format_benchmark_report,
    stress_phase_index,
    summarize_timings,
)


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
