"""In-memory, host-only checkpoints at completed playable level setup."""

from __future__ import annotations

from copy import deepcopy

from ..game.constants import GameMode
from ..game.eeprom_device import MemoryEepromStorage
from ..game.state import GameState


def _isolated_copy(state: GameState) -> GameState:
    # Never copy a file-backed device: a rewind must not roll external EEPROM
    # back. Copy its actual image, not the potentially different working RAM.
    device = MemoryEepromStorage(deepcopy(state.eeprom_storage.read()))
    return deepcopy(state, {id(state.eeprom_storage): device})


class LevelRestart:
    """Retain one independent baseline, not a recipe for regenerating a maze.

    Level loading installs a new MobTable, including a return to the same maze.
    Retaining that object (rather than its id or maze number) identifies the
    lifecycle without adding a host generation counter to GameState.
    """

    def __init__(self, state: GameState, *, resumed: bool = False) -> None:
        self._mobs = state.mobs
        self._snapshot: GameState | None = None
        self._awaiting_setup = not resumed

    def observe(self, state: GameState) -> bool:
        """Capture at startup or after a complete tick, never inside setup."""
        if state.mobs is not self._mobs:
            self._mobs = state.mobs
            self._snapshot = None
            self._awaiting_setup = True
        if state.game_mode < 0:
            self._snapshot = None
        if not self._awaiting_setup or not self._ready(state):
            return False
        snapshot = _isolated_copy(state)
        self._snapshot = snapshot
        self._awaiting_setup = False
        return True

    @staticmethod
    def _ready(state: GameState) -> bool:
        return (
            state.game_mode == int(GameMode.NORMAL)
            and state.maze is not None
            and not state.level_start_pending
            and state.random_pickups_setup_done
            and state.thief_level_setup_done
            and state.level_players_active > 0
            and any(player.active and player.mob_slot for player in state.players)
        )

    def restore(self, state: GameState) -> GameState | None:
        """Return a fresh copy; neither live mutations nor resets alter the save."""
        if (
            self._snapshot is None
            or state.mobs is not self._mobs
            or state.game_mode != int(GameMode.NORMAL)
            or state.level_start_pending
        ):
            return None
        restored = _isolated_copy(self._snapshot)
        self._mobs = restored.mobs
        return restored
