"""Host-only timing summaries for the playable benchmark harness."""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field


@dataclass(frozen=True)
class TimingSummary:
    samples: int
    minimum_ms: float
    median_ms: float
    mean_ms: float
    p95_ms: float
    maximum_ms: float


def summarize_timings(samples: list[float]) -> TimingSummary:
    """Summarize one named interval using a nearest-rank 95th percentile."""
    if not samples:
        raise ValueError("at least one timing sample is required")
    ordered = sorted(samples)
    p95_index = max(0, math.ceil(len(ordered) * 0.95) - 1)
    return TimingSummary(
        samples=len(ordered),
        minimum_ms=ordered[0],
        median_ms=statistics.median(ordered),
        mean_ms=statistics.fmean(ordered),
        p95_ms=ordered[p95_index],
        maximum_ms=ordered[-1],
    )


@dataclass
class BenchmarkRecorder:
    """Accumulate named host/game intervals, including their documented nesting."""

    host_input_ms: list[float] = field(default_factory=list)
    game_update_ms: list[float] = field(default_factory=list)
    game_raster_ms: list[float] = field(default_factory=list)
    presentation_ms: list[float] = field(default_factory=list)
    complete_loop_ms: list[float] = field(default_factory=list)

    def add(
        self,
        *,
        host_input_ms: float,
        game_update_ms: float,
        game_raster_ms: float,
        presentation_ms: float,
        complete_loop_ms: float,
    ) -> None:
        self.host_input_ms.append(host_input_ms)
        self.game_update_ms.append(game_update_ms)
        self.game_raster_ms.append(game_raster_ms)
        self.presentation_ms.append(presentation_ms)
        self.complete_loop_ms.append(complete_loop_ms)

    @property
    def frames(self) -> int:
        return len(self.complete_loop_ms)


def format_benchmark_report(recorder: BenchmarkRecorder, *, scale: int) -> str:
    """Return a stable, terminal-friendly report for performance comparisons."""
    rows = (
        ("host input", summarize_timings(recorder.host_input_ms)),
        ("game update", summarize_timings(recorder.game_update_ms)),
        ("game raster", summarize_timings(recorder.game_raster_ms)),
        ("presentation", summarize_timings(recorder.presentation_ms)),
        ("complete loop", summarize_timings(recorder.complete_loop_ms)),
    )
    lines = [
        f"gauntpy benchmark: {recorder.frames} frames at scale {scale}",
        "interval          mean ms  median ms   p95 ms   min ms   max ms",
    ]
    for name, summary in rows:
        lines.append(
            f"{name:<16} {summary.mean_ms:8.3f}  {summary.median_ms:9.3f}"
            f"  {summary.p95_ms:7.3f}  {summary.minimum_ms:7.3f}"
            f"  {summary.maximum_ms:7.3f}"
        )
    loop_mean = rows[-1][1].mean_ms
    lines.append(f"throughput: {1000.0 / loop_mean:.2f} frames/second")
    return "\n".join(lines)


def stress_phase_index(
    elapsed_seconds: float, total_seconds: float, phase_count: int,
) -> int:
    """Select a phase so one requested run traverses the complete workload set."""
    if total_seconds <= 0:
        raise ValueError("stress-test duration must be positive")
    if phase_count <= 0:
        raise ValueError("at least one stress-test phase is required")
    phase_seconds = min(2.0, total_seconds / phase_count)
    return int(elapsed_seconds / phase_seconds) % phase_count
