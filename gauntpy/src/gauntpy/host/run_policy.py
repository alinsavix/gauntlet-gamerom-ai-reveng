"""Concrete host run constraints and performance-workload progress.

Clock sampling and state construction stay in the application. These objects
only account for the observations supplied by that loop, never advance a game.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..performance import BenchmarkRecorder
    from ..performance_workloads import PerformanceWorkload


@dataclass(frozen=True)
class RunPolicy:
    benchmark_frames: int | None = None
    stress_seconds: float | None = None
    uncapped: bool = False
    sound_enabled: bool = False

    @property
    def performance_mode(self) -> bool:
        return self.benchmark_frames is not None or self.stress_seconds is not None

    @property
    def accelerated(self) -> bool:
        return self.uncapped or self.performance_mode

    @property
    def playback_enabled(self) -> bool:
        return self.sound_enabled and not self.accelerated


@dataclass
class BenchmarkRun:
    """Warm-up and measured frames for each selected workload, in order."""

    target_frames: int
    workloads: tuple[PerformanceWorkload, ...] = ()
    workload_index: int = field(default=0, init=False)
    recorder: BenchmarkRecorder = field(init=False)
    warmup_remaining: int = field(init=False)

    def __post_init__(self) -> None:
        self.reset_recording()

    @property
    def label(self) -> str:
        if self.workloads:
            return self.workloads[self.workload_index].name
        return "selected-state"

    def reset_recording(self) -> None:
        """Begin accounting only after the selected state's setup is complete."""
        from ..performance import BenchmarkRecorder

        self.recorder = BenchmarkRecorder()
        self.warmup_remaining = min(30, self.target_frames)

    def should_record(self, *, frame_updated: bool) -> bool:
        if not frame_updated:
            return False
        if self.warmup_remaining:
            self.warmup_remaining -= 1
            return False
        return True

    @property
    def complete(self) -> bool:
        return self.recorder.frames >= self.target_frames

    def report(self, *, scale: int) -> str:
        from ..performance import format_benchmark_report

        return format_benchmark_report(
            self.recorder, scale=scale,
            workload=self.label if self.workloads else None,
        )

    def advance_workload(self) -> PerformanceWorkload | None:
        """Select the next recipe; the caller builds it before resetting timing."""
        if self.workload_index + 1 >= len(self.workloads):
            return None
        self.workload_index += 1
        return self.workloads[self.workload_index]


@dataclass
class StressRun:
    """Wall-time schedule with at most one phase change per host iteration."""

    seconds: float
    workloads: tuple[PerformanceWorkload, ...]
    phase_indices: tuple[int, ...]
    started: float
    phase: int = field(default=0, init=False)
    frames: int = field(default=0, init=False)
    phase_seconds: float = field(init=False)
    next_phase_at: float = field(init=False)

    def __post_init__(self) -> None:
        self.phase_seconds = min(2.0, self.seconds / len(self.workloads))
        self.next_phase_at = self.phase_seconds

    @property
    def phase_index(self) -> int:
        return self.phase_indices[self.phase]

    @property
    def label(self) -> str:
        return self.workloads[self.phase].name

    def advance_if_due(self, elapsed: float) -> bool:
        if elapsed >= self.next_phase_at:
            self.phase = (self.phase + 1) % len(self.workloads)
            self.next_phase_at += self.phase_seconds
            return True
        return False

    def completion_report(self, elapsed: float) -> str:
        return (
            f"gauntpy stress test complete: {self.frames} frames "
            f"in {elapsed:.3f} seconds"
        )
