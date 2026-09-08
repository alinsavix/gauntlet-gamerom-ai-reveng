"""Caller-owned host session without adding fields to arcade memory."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..state import GameState
from .level_restart import LevelRestart

if TYPE_CHECKING:
    from ..custom_scenario import SyntheticScenarioRuntime


@dataclass
class HostSession:
    """The state selected by a host runner, independent of window lifetime.

    Legacy GameState-based synthetic APIs still own their metadata attachment.
    This caller-owned boundary does not attach a host object to GameState.
    """

    state: GameState
    resumed: bool = False
    restart_enabled: bool = True
    level_restart: LevelRestart = field(init=False)

    def __post_init__(self) -> None:
        self.level_restart = LevelRestart(self.state, resumed=self.resumed)

    def capture_level_start(self) -> bool:
        return self.restart_enabled and self.level_restart.observe(self.state)

    def restart_level(self) -> bool:
        if not self.restart_enabled:
            return False
        restored = self.level_restart.restore(self.state)
        if restored is None:
            return False
        self.state = restored
        return True

    @property
    def synthetic(self) -> SyntheticScenarioRuntime | None:
        from ..custom_scenario import synthetic_runtime_for

        return synthetic_runtime_for(self.state)

    def apply_events(self) -> None:
        """Compose fixture inputs before the normal game tick, never on pause."""
        from ..custom_scenario import apply_synthetic_events

        apply_synthetic_events(self.state)
