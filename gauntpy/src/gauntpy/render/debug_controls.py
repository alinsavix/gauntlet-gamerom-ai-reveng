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
    if state.secret_trick_id != exits.TRICK_NONE:
        return True

    previous_counter = state.secret_possible_counter
    state.secret_possible_counter = 0
    exits.secret_new_level_setup(state)
    from ..subsystems.session import _cancel_solo_only_trick

    _cancel_solo_only_trick(state)
    if state.secret_trick_id == exits.TRICK_NONE:
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
    # The ROM does not consult secret_player until the destination is past level
    # six (show_level_start_screen 0x44DCA).
    if state.levelnum_current < 6:
        return False
    if state.players[player_index].status != int(PlayerStatus.ALIVE_HERE):
        return False
    # Disable ordinary objective producers so another player cannot replace the
    # explicitly selected winner before the last exit dissolve completes.
    state.secret_trick_id = exits.TRICK_NONE
    state.secret_player = player_index
    return True


def debug_skip_level(state: GameState) -> bool:
    """Enter the next rotation level's ordinary splash, preserving survivors."""
    if state.game_mode != int(GameMode.NORMAL):
        return False
    survivors = [
        index for index, player in enumerate(state.players)
        if (
            player.status in (
                int(PlayerStatus.ALIVE_HERE),
                int(PlayerStatus.ALIVE_NEXT),
            )
            or (
                player.status == int(PlayerStatus.EXITING)
                and player.exit_pending
            )
        )
    ]
    if not survivors:
        return False

    from ..subsystems import exits

    old_level = state.levelnum_current
    was_bonus_room = exits.in_bonus_room(state)
    was_secret_room = exits.in_secret_room(state)
    transition_in_flight = any(
        state.players[index].exit_pending for index in survivors
    )
    if not was_bonus_room and not transition_in_flight:
        exits.compute_next_level(state, int(MazeObjIds.EXIT))

    for index in survivors:
        player = state.players[index]
        player.status = int(PlayerStatus.ALIVE_NEXT)
        player.exit_pending = 0

    exits.advance_level_countdowns(state)
    if was_bonus_room:
        if was_secret_room:
            if state.level_start_pending:
                # The challenge has not spawned yet, so its inventory has not
                # been stashed. Cancel the winner without running the payout.
                state.secret_player = -1
            else:
                # A skipped active challenge is a timeout: forfeit its award,
                # but return the inventory stashed on entry.
                exits._secret_room_payout(state, False)
            state.secret_need_hint = 0
            state.treasure_timer = 0
            state.treasure_voice_set = 0
            state.treasure_announcement_delay = 0xFFFF
            state.levelnum_current = state.level_next or old_level + 1
            if state.maze_next:
                state.mazenum_current = state.maze_next
        else:
            # Settle collected treasure and commit the queued ordinary position,
            # but skip the host-unhelpful bonus tally hold.
            exits.show_level_end_bonus_screen(state)
    else:
        exits.secret_check(state)
        state.levelnum_current = state.level_next or old_level + 1
        state.mazenum_current = state.maze_next

    exits._finish_level_end(state)
    if not state.level_start_pending:
        raise RuntimeError(
            "debug level skip could not load "
            f"level {state.levelnum_current} / maze {state.mazenum_current}"
        )
    return True
