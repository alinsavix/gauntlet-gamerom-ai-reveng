"""Host troubleshooting controls that reuse game-side state writers."""

from __future__ import annotations

from ..constants import GameMode, MazeObjIds, PlayerStatus
from ..state import GameState


def debug_add_key(state: GameState, player_index: int) -> bool:
    """Give one active player a key and refresh the modeled inventory panel."""
    if not 0 <= player_index < len(state.players):
        return False
    player = state.players[player_index]
    if not player.active:
        return False
    player.keysnum = (player.keysnum + 1) & 0xFF
    from ..subsystems.players import player_inv_update

    player_inv_update(state, player_index)
    return True


def debug_add_potion(state: GameState, player_index: int) -> bool:
    """Give one active player a potion and refresh the modeled inventory panel."""
    if not 0 <= player_index < len(state.players):
        return False
    player = state.players[player_index]
    if not player.active:
        return False
    player.potionsnum = (player.potionsnum + 1) & 0xFF
    from ..subsystems.players import player_inv_update

    player_inv_update(state, player_index)
    return True


def debug_enable_secret_room(state: GameState) -> bool:
    """Arm the current ordinary maze's ROM objective for normal exit checking."""
    if state.game_mode != int(GameMode.NORMAL):
        return False

    from ..subsystems import exits

    if exits.in_bonus_room(state):
        return False
    if not any(
        player.status == int(PlayerStatus.ALIVE_HERE)
        for player in state.players
    ):
        return False
    if state.trick_tasknum != exits.TRICK_NONE:
        return True

    previous_counter = state.secret_possible_counter
    state.secret_possible_counter = 0
    exits.secret_new_level_setup(state)
    from ..subsystems.session import _cancel_solo_only_trick

    _cancel_solo_only_trick(state)
    if state.trick_tasknum == exits.TRICK_NONE:
        state.secret_possible_counter = previous_counter
        return False
    return True


def debug_force_secret_room(state: GameState, player_index: int) -> bool:
    """Select one live player for the normal secret-room exit handoff."""
    if state.game_mode != int(GameMode.NORMAL):
        return False
    if not 0 <= player_index < len(state.players):
        return False

    from ..subsystems import exits

    if exits.in_bonus_room(state):
        return False
    # The ROM does not consult trick_player until the destination is past level
    # six (show_level_start_screen 0x44DCA).
    if state.levelnum_current < 6:
        return False
    if state.players[player_index].status != int(PlayerStatus.ALIVE_HERE):
        return False
    # Disable ordinary objective producers so another player cannot replace the
    # explicitly selected winner before the last exit dissolve completes.
    state.trick_tasknum = exits.TRICK_NONE
    state.trick_player = player_index
    return True


def debug_skip_level(state: GameState) -> bool:
    """Load the next rotation level immediately, preserving live-player state."""
    if state.game_mode != int(GameMode.NORMAL):
        return False
    survivors = [
        index for index, player in enumerate(state.players)
        if player.status == int(PlayerStatus.ALIVE_HERE)
    ]
    if not survivors:
        return False

    from ..subsystems import exits

    old_level = state.levelnum_current
    if not exits.in_bonus_room(state):
        exits.compute_next_level(state, int(MazeObjIds.EXIT))
    next_level = state.level_next or old_level + 1
    next_maze = state.maze_next
    state.levelnum_current = next_level
    state.mazenum_current = next_maze
    from ..subsystems.display import clear_alpha_visible

    clear_alpha_visible(state)
    exits.show_level_start_screen(state)
    if not exits._load_next_level(
        state, next_level, survivors, spawn_players=False,
    ):
        raise RuntimeError(
            "debug level skip could not load "
            f"level {next_level} / maze {state.mazenum_current}"
        )
    from ..subsystems.display import maze_show

    maze_show(state)
    exits._spawn_level_players(state, survivors)

    state.game_mode = int(GameMode.NORMAL)
    state.global_ui_delay_timer = 0
    state.bonus_amount = 0
    state.level_start_pending = False
    from ..subsystems.camera import snap_camera

    snap_camera(state)
    return True
