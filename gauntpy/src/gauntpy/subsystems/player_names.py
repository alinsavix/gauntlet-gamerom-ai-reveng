"""ROM high-score initials and secret-winner name/code routine families.

The two editors retain their distinct timing and completion branches. Only
the ROM character-ring and settled-button helpers are shared between them.
Player panel rebuilding remains a call to the lifecycle/HUD owner.
"""

from __future__ import annotations

from ..constants import PlayerStatus
from ..state import NUM_PLAYERS, GameState
from .player_animation import _PORT_DIR_TO_ROM_DIR


# player_state_timer reload values for the two status-0x04 dwells:
# highscore_check loads 0x0A8C for initials entry (0x49D88) and 0x0258 for the
# GAME OVER display (0x49DCA).  05_data_reference 0x904A26 documents both.
_NAME_ENTRY_TIMEOUT = 0x0A8C
_GAME_OVER_TIMEOUT = 0x0258

# Name entry (0x49DE6).  The joystick feeds a signed velocity accumulator
# clamped to +-0xA0 (0x49E4E/0x49E70); the repeat delay it produces is
# ``(0xA0 - |velocity|) >> 5 + 8`` (0x49F38-0x49F60), i.e. 13 frames per step at
# a fresh push down to 8 once the stick has been held for a while.
_NAME_ENTRY_VELOCITY_LIMIT = 0xA0
_NAME_ENTRY_REPEAT_SHIFT = 5
_NAME_ENTRY_REPEAT_BASE = 8
# The commit button is Magic *or* Fire, settled two frames (0x49F7E/0x49F9E:
# ``(shift & 0xF) == 0xC``) -- a shorter pattern than the start/join edge.
_NAME_ENTRY_COMMIT_MASK = 0x0F
_NAME_ENTRY_COMMIT_PATTERN = 0x0C
# 0x49FAA: presses are ignored for the first 0x78 frames of the 0x0A8C dwell,
# so the button that killed the hero cannot also commit its first initial.
_NAME_ENTRY_COMMIT_ARMED_BELOW = 0x0A14
# 0x4A00E: every committed initial buys 0x384 more frames.
_NAME_ENTRY_STEP_TIMEOUT = 0x0384
# Character codes name_entry_step_char (0x55440) cycles through.
_NAME_ENTRY_BACKSPACE = 0x08
_NAME_ENTRY_SPACE = 0x20
_NAME_ENTRY_FIRST_LETTER = 0x41      # 'A'
_NAME_ENTRY_LAST_LETTER = 0x5A       # 'Z'
#: Three initials per record (0x4A08C-0x4A0A0).
_NAME_ENTRY_LENGTH = 3
#: ``rank_high_score`` values outside 0-9 skip initials entry (0x49D4C/0x49D5C).
_HIGHSCORE_NO_RANK = 10

_SECRET_CODE_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTUWXYZ"  # ROM 0x54CA6
_SECRET_NAME_LENGTH = 29


def _secret_crc16(name: list[int]) -> int:
    """Port secret_code_build's table-driven CRC-CCITT update."""
    crc = 0
    for code in name:
        if code in (0, 0x20):
            if code == 0:
                break
            continue
        index = (code ^ (crc & 0xFF)) & 0xFF
        table = index << 8
        for _ in range(8):
            table = ((table << 1) ^ 0x1021) & 0xFFFF if table & 0x8000 else (table << 1) & 0xFFFF
        old_high = (crc >> 8) & 0xFF
        crc = ((table & 0xFF) << 8) | (old_high ^ (table >> 8))
    return crc


def secret_code_for(
    name: str, previous_maze: int, previous_trick: int, challenge: int,
) -> str:
    """Return secret_code_build 0x54BE0's code for explicit contest fields."""
    crc = _secret_crc16(list(name.encode("ascii")))
    packed = (
        ((((previous_trick & 0x0F) << 4)
          | (challenge & 0x0F)) << 7)
        | (previous_maze & 0x7F)
    )
    return (
        _SECRET_CODE_ALPHABET[((crc >> 8) >> 2) & 0x1F]
        + _SECRET_CODE_ALPHABET[(packed >> 10) & 0x1F]
        + _SECRET_CODE_ALPHABET[(crc >> 5) & 0x1F]
        + "-"
        + _SECRET_CODE_ALPHABET[(packed >> 5) & 0x1F]
        + _SECRET_CODE_ALPHABET[crc & 0x1F]
        + _SECRET_CODE_ALPHABET[packed & 0x1F]
    )


def secret_code_build(state: GameState) -> str:
    """Port secret_code_build 0x54BE0 and return its ``XXX-XXX`` result."""
    name = bytes(state.secret_name_buffer).split(b"\0", 1)[0].decode("ascii")
    code = secret_code_for(
        name, state.secret_prev_maze, state.secret_trick_last,
        state.secret_trick_id,
    )
    state.secret_code = code
    return code


def secret_getname(state: GameState) -> None:
    """Port secret_getname 0x54EC6, including its alpha-RAM setup."""
    winner = state.secret_player
    if not 0 <= winner < NUM_PLAYERS:
        return
    player = state.players[winner]
    if not (state.game_settings & 0x2000):
        state.global_delay_timer = 0x0385
        player.status = int(PlayerStatus.ALIVE_NEXT)
        state.secret_player = -1
        return
    player.name_entry_repeat_delay = _NAME_ENTRY_VELOCITY_LIMIT
    player.name_entry_velocity = 0
    player.initials_cursor = 0
    player.status = int(PlayerStatus.SECRET_NAME_ENTRY)
    state.global_delay_timer = 0x0A8D
    state.secret_name_buffer = [ord("A")] + [ord(" ")] * (_SECRET_NAME_LENGTH - 1)
    from .score import write_secret_name_entry

    write_secret_name_entry(state, winner)


def secret_name_entry_update(state: GameState) -> None:
    """Port the 29-character secret winner editor at 0x54FE8."""
    winner = state.secret_player
    if not 0 <= winner < NUM_PLAYERS:
        return
    player = state.players[winner]
    if player.status != int(PlayerStatus.SECRET_NAME_ENTRY):
        return

    cursor = player.initials_cursor
    dirs = (~(state.player_input_raw[winner] >> 4)) & 0x0F
    velocity = player.name_entry_velocity
    if dirs & 0x09:
        velocity = min(velocity + 1, _NAME_ENTRY_VELOCITY_LIMIT) if velocity >= 0 else 0
    elif dirs & 0x06:
        velocity = max(velocity - 1, -_NAME_ENTRY_VELOCITY_LIMIT) if velocity <= 0 else 0
    else:
        velocity = 0
    player.name_entry_velocity = velocity

    delay = player.name_entry_repeat_delay
    if delay:
        delay -= 1
    if delay == 0:
        if velocity and 0 <= cursor < _SECRET_NAME_LENGTH:
            state.secret_name_buffer[cursor] = name_entry_step_char(
                state.secret_name_buffer[cursor], velocity, bool(cursor),
            )
        delay = ((_NAME_ENTRY_VELOCITY_LIMIT - abs(velocity))
                 >> _NAME_ENTRY_REPEAT_SHIFT) + _NAME_ENTRY_REPEAT_BASE
    player.name_entry_repeat_delay = delay & 0xFF

    from .score import write_secret_code_result, write_secret_name_entry

    write_secret_name_entry(state, winner)
    if (
        _name_entry_commit_pressed(state, winner)
        and state.global_delay_timer < 0x0A15
    ):
        if state.secret_name_buffer[cursor] == _NAME_ENTRY_BACKSPACE:
            state.secret_name_buffer[cursor] = _NAME_ENTRY_SPACE
            cursor = max(0, cursor - 1)
        else:
            cursor += 1
            state.global_delay_timer = 0x0385
        player.initials_cursor = cursor
        if cursor < _SECRET_NAME_LENGTH:
            write_secret_name_entry(state, winner)

    if state.global_delay_timer >= 5 and cursor < _SECRET_NAME_LENGTH:
        return
    for index in range(max(0, cursor), _SECRET_NAME_LENGTH):
        state.secret_name_buffer[index] = _NAME_ENTRY_SPACE
    secret_code_build(state)
    write_secret_code_result(state, winner)
    player.status = int(PlayerStatus.ALIVE_NEXT)
    state.secret_player = -1
    state.debounce_shift_magic[winner] = 0
    state.debounce_shift_fire[winner] = 0
    state.global_delay_timer = 0x02D1


def highscore_check(state: GameState, player_index: int) -> None:
    """0x49D0E -- rank the dead player and open initials entry (§10.3).

    Ranks ``player_scorepercoin`` through OS ``rank_high_score``
    (0x1C6, WP-14's ``score.rank_high_score``) for that player's character
    class and stores the result in ``player_highscore_rank`` (0x904A4A).

      * a rank of 0-9 (0x49D4C/0x49D5C) opens the editor: the repeat delay
        (0x904A36) is primed to 0xA0, ``player_state_timer`` takes 0x0A8C
        (2700 frames, 45 s), the velocity accumulator (0x904A2E) and the
        initials cursor (0x904A3A) are cleared and the status becomes 0x04;
      * anything else just loads the 0x0258 (600-frame) GAME OVER dwell
        (0x49DCA) and leaves the status alone.

    Either way the player's panel column is rebuilt (0x49DD6).
    """
    from . import score
    from .players import setup_infopanel

    player = state.players[player_index]
    rank = score.rank_high_score(
        state, int(player.character), player.score_per_coin
    )                                                        # OS 0x1C6
    player.highscore_rank = rank                             # 0x904A4A

    if 0 <= rank < _HIGHSCORE_NO_RANK:                       # 0x49D4C/0x49D5C
        player.name_entry_repeat_delay = _NAME_ENTRY_VELOCITY_LIMIT  # 0x49D78
        player.state_timer = _NAME_ENTRY_TIMEOUT             # 0x49D88
        player.name_entry_velocity = 0                       # 0x49D98
        player.initials_cursor = 0                           # 0x49D9C
        player.initials = [_NAME_ENTRY_FIRST_LETTER] * _NAME_ENTRY_LENGTH
        player.status = int(PlayerStatus.DYING)              # 0x49DA6
    else:
        player.state_timer = _GAME_OVER_TIMEOUT              # 0x49DCA

    setup_infopanel(state, player_index)                     # 0x49DD6


def name_entry_step_char(current: int, direction: int, allow_backspace: bool) -> int:
    """0x55440 -- step one initials character round its ring.

    The ring is ``backspace (0x08) -> space (0x20) -> 'A'..'Z' -> backspace``,
    with the backspace glyph skipped when it is not allowed -- which is exactly
    ``cursor != 0``, since there is nothing to back up into at the first
    initial.  Every wrap in 0x5545E-0x554A6 is reproduced here.
    """
    value = (current + 1) if direction > 0 else (current - 1)
    if value == _NAME_ENTRY_BACKSPACE + 1:                   # 0x5545E
        return _NAME_ENTRY_SPACE
    if value == _NAME_ENTRY_SPACE + 1:                       # 0x55468
        return _NAME_ENTRY_FIRST_LETTER
    if value == _NAME_ENTRY_LAST_LETTER + 1:                 # 0x55472
        return _NAME_ENTRY_BACKSPACE if allow_backspace else _NAME_ENTRY_SPACE
    if value == _NAME_ENTRY_BACKSPACE - 1:                   # 0x55484
        return _NAME_ENTRY_LAST_LETTER
    if value == _NAME_ENTRY_SPACE - 1:                       # 0x5548E
        return (_NAME_ENTRY_BACKSPACE if allow_backspace
                else _NAME_ENTRY_LAST_LETTER)
    if value == _NAME_ENTRY_FIRST_LETTER - 1:                # 0x554A0
        return _NAME_ENTRY_SPACE
    return value


def _name_entry_initials(player) -> str:  # noqa: ANN001
    """The three editable codes as the string ``write_high_score_entry`` stores.

    A backspace glyph still sitting in a slot when the countdown expires is
    stored as a space -- the ROM hands the raw byte to the OS writer, whose
    base-40 codec (0x3AEC) has no letter for it either.
    """
    return "".join(
        " " if code in (_NAME_ENTRY_BACKSPACE, 0) else chr(code)
        for code in player.initials[:_NAME_ENTRY_LENGTH]
    )


def _name_entry_commit_pressed(state: GameState, player_index: int) -> bool:
    """0x49F6E-0x49FA2: Magic or Fire settled over two frames."""
    for shift in (state.debounce_shift_magic, state.debounce_shift_fire):
        if (shift[player_index] & _NAME_ENTRY_COMMIT_MASK) == _NAME_ENTRY_COMMIT_PATTERN:
            return True
    return False


def _name_entry_finish(state: GameState, player_index: int) -> None:
    """0x4A07A-0x4A116 -- insert the record and end the dwell.

    Builds ``{score_per_coin, initials[3]}`` and hands it to OS
    ``write_high_score_entry`` (0x1B4) at the stored rank, clears the status
    (0x4A0D8), zeroes both debounce registers so the commit press cannot leak
    into the next screen (0x4A0F2/0x4A0F6), loads the 600-frame GAME OVER dwell
    (0x4A0FE), rebuilds the panel and shows the continue prompt (0x4A110).
    """
    from . import score
    from .players import setup_infopanel, show_continue_prompt

    player = state.players[player_index]
    if 0 <= player.highscore_rank < _HIGHSCORE_NO_RANK:
        score.write_high_score_entry(                        # OS 0x1B4
            state,
            int(player.character),
            player.highscore_rank,
            player.score_per_coin,
            _name_entry_initials(player),
        )
    player.highscore_rank = _HIGHSCORE_NO_RANK
    player.status = int(PlayerStatus.REMOVED)                    # 0x4A0D8
    state.debounce_shift_magic[player_index] = 0             # 0x4A0F6
    state.debounce_shift_fire[player_index] = 0              # 0x4A0F2
    player.state_timer = _GAME_OVER_TIMEOUT                  # 0x4A0FE
    setup_infopanel(state, player_index)                     # 0x4A10A
    show_continue_prompt(state)                              # 0x4A110


def player_death_sequence(state: GameState, player_index: int) -> None:
    """0x49DE6 -- the status-0x04 per-frame handler (§4.1, player lifecycle).

    **Exact timing, ROM-verified -- the previous "count up to 0x40" was a
    guess and is wrong in both direction and length.**  0x49E12-0x49E1E is a
    *countdown*: ``player_state_timer`` (0x904A26) is decremented once per
    frame while it is non-zero, and the state ends when it reaches zero
    (0x4A06C).  There is no fixed 0x40 death animation anywhere in the
    lifecycle -- the animated part is the status-0x08 branch of
    main_move_players, which runs on the per-four-frame cadence below.

    Status 0x04 is entered only from ``highscore_check`` (0x49DA6): with
    initials to enter it loads 0x0A8C (2700 frames, 45 s, 0x49D88); the plain
    GAME OVER display loads 0x0258 (600 frames, 0x49DCA).  05_data_reference's
    0x904A26 entry documents both.

    The body in between is the initials editor, and all of it is RAM:

      * the joystick's up/right bits (mask 9 of the inverted direction nibble)
        drive the velocity accumulator up, its down/left bits (mask 6) drive it
        down, anything else zeroes it, and it clamps at ±0xA0 (0x49E20-0x49E86);
      * the repeat delay (0x904A36) counts down; on the frame it reaches zero a
        non-zero velocity steps the character under the cursor through
        ``name_entry_step_char``, and the delay reloads to
        ``(0xA0 - |velocity|) >> 5 + 8`` -- a held stick accelerates
        (0x49E8A-0x49F60);
      * a settled Magic or Fire press commits the character: a backspace glyph
        moves the cursor back, anything else moves it on and buys 0x384 more
        frames (0x49F6E-0x4A066);
      * the dwell ends when the countdown expires **or** the cursor passes the
        third initial (0x4A068), and the record is inserted there.

    A plain death does not pass through the ROM's copy of this at all: the
    health-zero path in main_health_countdown resets the player outright and
    only ``highscore_check`` can put it in status 4.  This port keeps its own
    death animation afterwards, so the expired dwell hands over to the
    status-0x08 branch instead of straight to REMOVED.
    """
    player = state.players[player_index]
    editing = 0 <= player.highscore_rank < _HIGHSCORE_NO_RANK

    if player.state_timer > 0:                       # 0x49E12: tst / subq #1
        player.state_timer -= 1

    if editing:
        _name_entry_edit(state, player_index)
        # 0x4A068: still running while the countdown has time left and the
        # cursor has not walked past the third initial.
        if player.state_timer > 0 and player.initials_cursor != _NAME_ENTRY_LENGTH:
            return
        _name_entry_finish(state, player_index)
        return
    elif player.state_timer > 0:
        return

    player.status = int(PlayerStatus.RESPAWN_WAIT)
    player.exit_pending = 0
    player.anim_counter = 0
    state.player_death_anim_frame[player_index] = _PORT_DIR_TO_ROM_DIR[
        player.direction & 0x07
    ]


def _name_entry_edit(state: GameState, player_index: int) -> None:
    """0x49E20-0x4A066 -- one frame of the initials editor."""
    player = state.players[player_index]

    # 0x49E20-0x49E34: the raw input word's direction nibble, active-high.
    dirs = (~(state.player_input_raw[player_index] >> 4)) & 0x0F
    velocity = player.name_entry_velocity
    if dirs & 0x09:                                  # 0x49E46: up / right
        velocity = min(velocity + 1, _NAME_ENTRY_VELOCITY_LIMIT) if velocity >= 0 else 0
    elif dirs & 0x06:                                # 0x49E68: down / left
        velocity = max(velocity - 1, -_NAME_ENTRY_VELOCITY_LIMIT) if velocity <= 0 else 0
    else:                                            # 0x49E80
        velocity = 0
    player.name_entry_velocity = velocity            # 0x49E86

    cursor = player.initials_cursor                  # 0x49E0C: byte 0
    delay = player.name_entry_repeat_delay           # 0x49E8A
    if delay:
        delay -= 1
    if delay == 0:                                   # 0x49E9E
        if velocity:                                 # 0x49EA6
            if 0 <= cursor < _NAME_ENTRY_LENGTH:
                player.initials[cursor] = name_entry_step_char(
                    player.initials[cursor], velocity, bool(cursor),
                )                                    # 0x49ED0/0x49EEE
        # 0x49F32-0x49F60: reload from the accumulated velocity.
        delay = ((_NAME_ENTRY_VELOCITY_LIMIT - abs(velocity))
                 >> _NAME_ENTRY_REPEAT_SHIFT) + _NAME_ENTRY_REPEAT_BASE
    player.name_entry_repeat_delay = delay & 0xFF    # 0x49F62
    from .score import draw_player_initials_entry

    draw_player_initials_entry(state, player_index)

    if not _name_entry_commit_pressed(state, player_index):
        return
    if player.state_timer >= _NAME_ENTRY_COMMIT_ARMED_BELOW:   # 0x49FAA
        return
    if 0 <= cursor < _NAME_ENTRY_LENGTH and \
            player.initials[cursor] == _NAME_ENTRY_BACKSPACE:  # 0x49FFC
        cursor -= 1                                  # 0x4A016
    else:
        cursor += 1                                  # 0x4A008
        player.state_timer = _NAME_ENTRY_STEP_TIMEOUT           # 0x4A00E
    player.initials_cursor = max(0, cursor)          # 0x4A066
    draw_player_initials_entry(state, player_index)
