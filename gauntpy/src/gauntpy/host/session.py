"""Caller-owned host session without adding fields to arcade memory."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..state import GameState

if TYPE_CHECKING:
    from ..custom_scenario import SyntheticScenarioRuntime


@dataclass
class HostSession:
    """The state selected by a host runner, independent of window lifetime.

    Legacy GameState-based synthetic APIs still own their metadata attachment.
    This caller-owned boundary does not attach a host object to GameState.
    """

    state: GameState

    @property
    def synthetic(self) -> SyntheticScenarioRuntime | None:
        from ..custom_scenario import synthetic_runtime_for

        return synthetic_runtime_for(self.state)

    def apply_events(self) -> None:
        """Compose fixture inputs before the normal game tick, never on pause."""
        from ..custom_scenario import apply_synthetic_events

        apply_synthetic_events(self.state)
