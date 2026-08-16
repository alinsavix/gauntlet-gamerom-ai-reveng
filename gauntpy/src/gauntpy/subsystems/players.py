"""Player movement, lifecycle, health, and tile interaction -- WP-5 and WP-6.

Two work packages share this module: WP-5 owns movement and collision, WP-6
owns lifecycle, health, powers, and tile interaction. Agree on the split inside
``main_move_players`` before either starts.

Reference: ``doc/04_game_subsystems.md`` §4 (all), §21;
``doc/generated/player_collision_contracts.csv``,
``player_runtime_contracts.csv``, ``player_lifecycle_contracts.csv``;
``book/10_players.md``.
"""

from __future__ import annotations

from ..state import GameState
from . import stub


@stub
def main_move_players(state: GameState) -> None:
    """0x4A53A -- per-frame processing for all four player slots.

    Four sections: the game-mode gate, demo playback (recorded
    ``[timer, joystick]`` pairs), the per-player status dispatch, and the
    post-loop idle work (``open_timed_doors``, trap-wall conversion at 21000
    steps).

    The biggest call in the loop. WP-5 owns ``player_try_move`` (0x41BF0) and
    the four ``mob_probe_*`` leaves; WP-6 owns the status machine, power-ups,
    and ``player_tile_interact`` (0x511AC).
    """


@stub
def main_health_countdown(state: GameState) -> None:
    """0x466F6 -- health drain and the low-health warning cadence.

    The drain is flat: ``subq.l #1`` gated on ``frame_counter & 0x3F`` -- one
    point per player per 64 frames, in every mode, with **no class or
    difficulty term**. The table once called ``health_drain_table`` is not
    this; it is ``forcefield_damage_table`` and belongs to the forcefield
    contact path in ``main_move_players``.
    """


@stub
def main_handle_death(state: GameState) -> None:
    """0x4664C -- forcefield and death sound timers. See §21."""
