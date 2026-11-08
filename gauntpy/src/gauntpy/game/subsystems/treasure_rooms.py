"""Treasure-room countdown, speech, and end-of-level bonus routines."""

from __future__ import annotations

from .. import romtext
from ..constants import GameMode, PlayerStatus
from ..state import GameState
from .display import alpha_word, fill_alpha_rect, write_alpha_decimal, write_alpha_large_text, write_alpha_text
from .sound import sound_play, sound_speech_play
from .level_data import (
    _SECRET_MAZE_FIRST as _SECRET_MAZE_FIRST,
)

# game_settings (0x904A24) bit 11, "Disable Speech".  main_treasure_timer forces
# the timeout announcement to element 0 (ZERO) when it is set (0x4D41A-0x4D426).
_GSETTING_SPEECH_DISABLE = 0x800


# ---------------------------------------------------------------------------
# Speech tables -- doc/05_data_reference.md §5.5, transcribed from row76.bin
# ---------------------------------------------------------------------------

# treasure_seconds_speech, ROM 0x5AB64 (row76.bin 0x1AB64) -- 11 longwords
# indexed *directly by the seconds remaining*, 0..10: ZERO, ONE, ... TEN
# (0x4D442-0x4D44C).  Element 0 is bypassed by the timeout branch but keeps the
# numeric table direct-indexed.
_TREASURE_SECONDS_SPEECH = [
    0x54,                          # 0     ZERO
    0x4A, 0x4B, 0x4C, 0x4D, 0x4E,  # 1-5   ONE..FIVE
    0x4F, 0x50, 0x51, 0x52, 0x53,  # 6-10  SIX..TEN
]

# treasure_fake_countdown_sequences, ROM 0x5AB90, reached through the four
# pointers at 0x5ABE0 (0x5AB90/0x5ABA4/0x5ABB8/0x5ABCC).  Each row is five
# speech IDs for displayed seconds 10 down to 6 -- deliberately scrambled, so
# the machine lies about how much time is left (0x4D382-0x4D3A0).
_TREASURE_FAKE_COUNTDOWN_SEQUENCES = [
    [0x4D, 0x50, 0x52, 0x4F, 0x51],  # FOUR SEVEN NINE SIX EIGHT
    [0x4C, 0x4D, 0x4E, 0x4F, 0x50],  # THREE FOUR FIVE SIX SEVEN
    [0x4B, 0x4C, 0x4D, 0x51, 0x52],  # TWO THREE FOUR EIGHT NINE
    [0x51, 0x50, 0x4F, 0x4E, 0x4D],  # EIGHT SEVEN SIX FIVE FOUR
]
# treasure_fakeout_speech, ROM 0x5ABF0 -- played once the fake countdown reaches
# displayed second 6 (0x4D3AA-0x4D3C0).
_TREASURE_FAKEOUT_SPEECH = [0xA5, 0xA6]          # JUST KIDDING / FOOLED YOU
# treasure_timeout_speech, ROM 0x5ABF8 (0x4D418-0x4D44C).
_TREASURE_TIMEOUT_SPEECH = [0x54, 0xA0, 0x54, 0xA7]
# treasure_warning_speech / treasure_warning_delay, ROM 0x5AC08 / 0x5AC18 --
# the six-second warning and how many countdown seconds it silences
# (0x4D3E4-0x4D40A).
_TREASURE_WARNING_SPEECH = [0xA1, 0xA2, 0xA3, 0xA4]
_TREASURE_WARNING_DELAY = [1, 2, 2, 2]
# The fake countdown is only armed above level 30 and only in a treasure (not
# secret) room, on a 1-in-16 roll at the ten-second mark (0x4D33E-0x4D364).
_FAKE_COUNTDOWN_ODDS = 0x10
_FAKE_COUNTDOWN_MIN_LEVEL = 0x1E     # 30
# The six-second warning fires on a 1-in-4 roll (0x4D3DA-0x4D3E2).
_WARNING_ODDS = 4


# ---------------------------------------------------------------------------
# main_treasure_timer (0x4D29E) -- countdown, speech, timeout
# ---------------------------------------------------------------------------

# ROM: part game:0x4D29E | Once-per-second countdown, fakeout, warning and timeout speech branch; instruction range 0x4D2FC-0x4D456 is internal to the timer routine.
def _countdown_speech(state: GameState, seconds_remaining: int) -> None:
    """The once-per-second announcement block, 0x4D2FC-0x4D456 (§16).

    Ten seconds out the machine decides whether to lie: above level 30, in a
    treasure (not secret) room, a 1-in-16 roll arms one of the four scrambled
    sequences at 0x5AB90, which counts 10-6 with the wrong numbers and then owns
    up with JUST KIDDING / FOOLED YOU.  Otherwise the true number is spoken from
    0x5AB64, with a 1-in-4 taunt at six seconds and a parting shot at zero.
    """
    if seconds_remaining == 10:                          # 0x4D330
        state.treasure_announcement_delay = 0
        state.treasure_voice_set = 0
        if (
            state.mazenum_current < _SECRET_MAZE_FIRST
            and state.getrandom(_FAKE_COUNTDOWN_ODDS) == 0
            and state.levelnum_current > _FAKE_COUNTDOWN_MIN_LEVEL
        ):
            state.treasure_voice_set = state.getrandom(4) + 1

    if state.treasure_announcement_delay != 0:           # 0x4D366
        state.treasure_announcement_delay -= 1
        return

    if state.treasure_voice_set != 0 and seconds_remaining >= 6:   # 0x4D378
        sequence = _TREASURE_FAKE_COUNTDOWN_SEQUENCES[state.treasure_voice_set - 1]
        sound_play(state, sequence[seconds_remaining - 6])
        if seconds_remaining == 6:                       # 0x4D3A6: own up
            sound_play(state, _TREASURE_FAKEOUT_SPEECH[state.getrandom(2)])
            state.treasure_announcement_delay = 1
            state.treasure_voice_set = 0
        return

    if seconds_remaining == 6 and state.getrandom(_WARNING_ODDS) == 0:  # 0x4D3D4
        pick = state.getrandom(4)
        sound_speech_play(state, _TREASURE_WARNING_SPEECH[pick])
        state.treasure_announcement_delay = _TREASURE_WARNING_DELAY[pick]
        return

    if seconds_remaining == 0:                           # 0x4D414
        pick = 0 if state.game_settings & _GSETTING_SPEECH_DISABLE else state.getrandom(4)
        sound_play(state, _TREASURE_TIMEOUT_SPEECH[pick])
        return

    if seconds_remaining <= 10:                          # 0x4D43C
        sound_play(state, _TREASURE_SECONDS_SPEECH[seconds_remaining])


# ROM: direct game:0x4D29E | Countdown gates, seconds display and expiry transition; speech is extracted and the shared UI timer is only tested here, not decremented.
def main_treasure_timer(state: GameState) -> None:
    """0x4D29E -- treasure-room countdown, speech, and timeout.

    Four gates, in the ROM's order (0x4D2B2-0x4D2D8):

      * ``global_delay_timer`` (0x904A4E) must be zero -- while a bonus tally
        or level splash is up, ``main_start_game`` runs down that shared timer
        and this routine leaves the treasure countdown frozen;
      * ``treasure_timer`` (0x9049E8) must be nonzero;
      * ``game_mode`` must be NORMAL (0);
      * ``mazenum_current`` must be >= 104 -- a treasure or secret room.

    The timer then decrements once per frame and every 60th frame speaks the
    remaining seconds (``_countdown_speech``).  When it reaches zero with at
    least one player still counted by ``player_activecount``, the level ends via
    ``show_level_end_bonus_screen`` (0x4D456-0x4D466).

    Reference: doc/04_game_subsystems.md §16.
    """
    from .level_state import in_bonus_room, player_activecount

    # main_treasure_timer only tests this shared timer. main_start_game owns its
    # decrement and transition actions at 0x4817C-0x481E8.
    if state.global_delay_timer > 0:
        return

    if state.treasure_timer <= 0:              # 0x4D2BC (also guards negatives)
        return
    if state.game_mode != int(GameMode.NORMAL):   # 0x4D2C6
        return
    if not in_bonus_room(state):               # 0x4D2D0
        return

    state.treasure_timer -= 1                  # 0x4D2DC

    # Every full second (60 frames), including the final zero.
    if state.treasure_timer % 60 == 0:         # 0x4D2EA divu #0x3C, remainder
        seconds_remaining = state.treasure_timer // 60
        write_alpha_large_text(
            state, 34, 2, f"{seconds_remaining:>2}", 0x8000,
        )                                       # 0x4D2FC-0x4D32A
        _countdown_speech(state, seconds_remaining)

    # Timer just expired: end the level if anyone is still present.
    if state.treasure_timer == 0:              # 0x4D456
        if player_activecount(state) > 0:   # 0x4D45E level_players_active
            show_level_end_bonus_screen(state)


# Bonus-screen hold before the next level loads: global_delay_timer = 0x12C
# (300 frames, 5 s) at show_level_end_bonus_screen 0x4D50E.
_BONUS_DISPLAY_FRAMES = 0x12C


# ROM: part game:0x4D476 | Extracted small-alpha ordinary/secret bonus tally writes using precomputed Python rows; does not own OS text-rendering bodies.
def _write_bonus_alpha(
    state: GameState, *,
    ordinary_rows: dict[int, tuple[int, int, int, int]],
    secret_room: bool,
    secret_player: int,
) -> None:
    """Write show_level_end_bonus_screen's exact small-alpha tally."""
    fill_alpha_rect(state, 0, 0, 29, 30, alpha_word(0x8000))
    if secret_room:                                  # 0x4D720: only the winner has a line
        if secret_player < 0:
            return
        attribute = 0x8400 + (secret_player << 10)
        row = 9 + secret_player * 5
        if state.bonus_amount:
            write_alpha_text(state, 4, row, romtext.BONUS_SECRET_5000, attribute)
            write_alpha_decimal(
                state, 19, row, state.bonus_amount, 7, attribute,
            )
        else:
            write_alpha_text(state, 4, row, romtext.BONUS_NONE, attribute)
        return

    for player_index, player in enumerate(state.players):
        attribute = 0x8400 + (player_index << 10)
        row = 8 + player_index * 5
        values = ordinary_rows.get(player_index)
        if values is None:
            if player.status == int(PlayerStatus.ALIVE_HERE):
                write_alpha_text(state, 4, row + 1, romtext.BONUS_NONE, attribute)
            continue
        player_factor, coin_factor, treasures, bonus = values
        write_alpha_text(state, 7, row, romtext.BONUS_100_X_COINS, attribute)
        write_alpha_decimal(state, 7, row, player_factor, 3, attribute)
        write_alpha_decimal(state, 22, row, coin_factor, 5, attribute)
        write_alpha_text(state, 9, row + 1, romtext.BONUS_TREASURES_X, attribute)
        write_alpha_decimal(state, 23, row + 1, treasures, 4, attribute)
        write_alpha_text(state, 13, row + 2, romtext.BONUS_EQUALS, attribute)
        write_alpha_decimal(state, 21, row + 2, bonus, 6, attribute)


# ROM: helper | Python survivor-index list for deferred level loading; not the narrower ROM bonus-recipient predicate.
def _exiting_or_here(state: GameState) -> list[int]:
    """Players who go on to the next level: still on it, or in the exit."""
    return [
        i for i, p in enumerate(state.players)
        if p.status in (int(PlayerStatus.ALIVE_NEXT), int(PlayerStatus.ALIVE_HERE))
    ]


# ROM: part game:0x4D476 | Status-2/status-8 recipient filter extracted from comparisons at 0x4D552/0x4D55E.
def _bonus_recipients(state: GameState) -> list[int]:
    """Players the tally pays -- status 2 or 8 exactly (0x4D552/0x4D55E).

    Narrower than ``_exiting_or_here``: somebody still standing in a bonus room
    when its clock runs out never reached the exit, and the ROM pays them
    nothing.
    """
    return [
        i for i, p in enumerate(state.players)
        if p.status in (int(PlayerStatus.ALIVE_NEXT), int(PlayerStatus.RESPAWN_WAIT))
    ]


# ROM: direct game:0x489B8 | The hero's power-up flash and transport sparkle go, and any transport in flight ends.
def remove_dying_player_sprites(state: GameState, player_index: int) -> None:
    mobs = state.mobs
    if mobs.picture[player_index + 1]:               # 0x489CE-0x489EC
        mobs.depth_remove(player_index)
        mobs.picture[player_index + 1] = 0
    if mobs.picture[player_index + 0x19]:            # 0x489F4-0x48A1A
        mobs.depth_remove(player_index + 0x18)
        mobs.picture[player_index + 0x19] = 0
    state.player_tport_phase[player_index] = -1      # 0x48A26


# ROM: part game:0x4D476 | A hero's way off the level at the tally: from the level (0x4D6EC-0x4D712, 0x4D810-0x4D82E) or the exit animation (0x4D6A0-0x4D6BE, 0x4D840-0x4D856).
def _hero_leaves_for_the_tally(state: GameState, player_index: int) -> None:
    player = state.players[player_index]
    remove_dying_player_sprites(state, player_index)
    if player.status == int(PlayerStatus.ALIVE_HERE):
        state.mobs.unlink_and_clear(player.mob_slot)
    else:
        state.mobs.depth_remove(player_index + 0x14)
        player.exit_pending = 0
    player.status = int(PlayerStatus.ALIVE_NEXT)


# ROM: direct game:0x4D476 | Bonus/tally and committed next-position boundary with extracted payout/text arms; the deferred Python continuation remains a caveat.
def show_level_end_bonus_screen(state: GameState) -> None:
    """0x4D476 -- end the level: award the treasure bonus, show the tally, then
    (after the hold) load the saved next maze.

    Commits the computed ``level_next``/``maze_next`` and pays every player who
    reached the exit their own bonus -- ``100 x player_activecount x
    player_coincount[p] x player_treascount[p]`` (0x4D516-0x4D5AA, doc/04 §16) --
    then enters the display phase: ``game_mode = TREAS_EXIT`` with ``global_delay_timer``
    (the ROM's ``global_delay_timer``, 0x904A4E) counting 300 frames down
    instead of cutting straight to the next level. ``main_start_game`` runs
    the countdown and fires the deferred load (``_finish_level_end``) when it
    expires. This routine writes the settled tally into alpha VRAM before it
    returns; the generic alpha pass displays those words during the hold.

    The product is the ROM's, with its widths: ``mulu.w`` at 0x4D578 keeps the
    whole of 100 x players x coins, which the screen shows, but ``mulu.w`` at
    0x4D58E takes only its low 16 bits, so with four heroes the bonus wraps from
    164 coins each. The treasure count is the byte at 0x904A50, which
    ``player_start_inner`` clears, so a hero who rejoins forfeits what they held.
    ``bonus_amount`` is the total shown on the screen; 0 treasures yields 0 (a
    "NO BONUS" screen).

    Robust to a ROM-less environment -- the deferred load leaves the old maze
    intact if the next one cannot be decoded.

    Leaving a treasure room plays the treasure-music fade (0x41) rather than the
    theme fade, matching the ``mazenum_current >= 115`` split at 0x4D496.

    Leaving a **secret** room takes the other tally entirely (0x4D720-0x4D8A0):
    ``secret_check_winner`` decides whether the challenge task was completed,
    only ``secret_player`` is paid -- ``5000 x player_coincount`` -- and the
    inventory stashed on the way in is handed back. The position is committed
    last (0x4D8E2/0x4D8EC), so every branch above still sees the maze that was
    just played, and ``secret_check`` (0x4D8DC) adapts how soon the next secret
    room may be offered.
    """
    from .level_state import in_secret_room, player_activecount
    from .secret_rooms import (
        _secret_room_payout as _secret_room_payout,
        secret_check as secret_check,
        secret_check_winner as secret_check_winner,
    )

    from .player_lifecycle import setup_infopanel

    was_secret_room = in_secret_room(state)          # 0x4D496, before the commit
    secret_player = state.secret_player if was_secret_room else -1
    ordinary_rows: dict[int, tuple[int, int, int, int]] = {}
    challenge_completed = secret_check_winner(state) if was_secret_room else False  # 0x4D4B0

    sound_play(state, 0x39)                          # 0x4D48A slow-motion silencer
    if not was_secret_room:
        sound_play(state, 0x41)                      # 0x4D4A2 treasure-music fade
    else:
        sound_play(state, 0x3C)                      # 0x4D4BA theme fade

    state.treasure_timer = 0
    state.treasure_voice_set = 0
    # 0x4D4D6 parks the announcement delay on -1: no countdown speech can fire
    # while the tally is up. Entering the next treasure room re-zeroes it.
    state.treasure_announcement_delay = 0xFFFF
    setup_infopanel(state, -1)                       # 0x4D4DE-0x4D4E4
    state.global_delay_timer = _BONUS_DISPLAY_FRAMES        # 0x4D50E
    state.game_mode = GameMode.TREAS_EXIT            # display phase (world frozen)

    open_name_entry = False
    if was_secret_room:                              # 0x4D544 -> 0x4D720
        open_name_entry = _secret_room_payout(state, challenge_completed)
        state.secret_need_hint = 0                   # 0x4D8D4
    else:
        player_factor = (100 * player_activecount(state)) & 0xFFFF  # 0x4D516-0x4D526

        state.bonus_amount = 0
        for i in _bonus_recipients(state):           # 0x4D552/0x4D55E status 2 / 8
            player = state.players[i]
            coin_factor = (player.coin_count & 0xFFFF) * player_factor  # 0x4D574-0x4D57A
            treasures = state.player_treascount[i] & 0xFF               # 0x4D586
            bonus = (coin_factor & 0xFFFF) * treasures                  # 0x4D58E mulu.w
            ordinary_rows[i] = (player_factor, coin_factor, treasures, bonus)
            player.score += bonus                    # 0x4D59E
            state.score_dirty[i] = 1                 # 0x4D5AA ori.b #1
            state.bonus_amount += bonus

        secret_check(state)                          # 0x4D8DC

    _write_bonus_alpha(
        state, ordinary_rows=ordinary_rows, secret_room=was_secret_room,
        secret_player=secret_player,
    )
    if not was_secret_room:
        for i, player in enumerate(state.players):   # 0x4D692-0x4D712
            if player.status in (int(PlayerStatus.ALIVE_HERE), int(PlayerStatus.RESPAWN_WAIT)):
                _hero_leaves_for_the_tally(state, i)
    for player in state.players:                     # 0x4D8A4-0x4D8AE
        player.mob_slot = 0
    state.level_players_active = 0                   # 0x4D8C4
    if open_name_entry:
        from .player_names import secret_getname

        secret_getname(state)                        # 0x4D7E0, after tally writes

    # Commit the next position last, exactly as 0x4D8E2/0x4D8EC do (default to
    # level+1 if compute_next_level was not run, e.g. a direct caller).
    state.levelnum_current = state.level_next or (state.levelnum_current + 1)
    if state.maze_next:
        state.mazenum_current = state.maze_next
