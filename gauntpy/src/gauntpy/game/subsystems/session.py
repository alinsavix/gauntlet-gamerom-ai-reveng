"""Coins, credits, character select, and session start -- WP-16.

Reference: ``doc/04_game_subsystems.md`` §10.1, §22, §6.4;
``book/01_how_to_play.md`` and ``book/08_what_a_quarter_buys.md``.
"""

from __future__ import annotations

from .. import romtext
from ..alpha_memory import write_alpha_word
from ..constants import SLOT_SHOT_EXPLOSIONS, Character, GameMode, PlayerStatus
from ..state import NUM_PLAYERS, GameState
from .display import (
    write_alpha_glyphs, write_alpha_large_text,
)
from .player_lifecycle import (
    player_join_finalize, player_start_inner, setup_infopanel, show_continue_prompt,
)

# ---------------------------------------------------------------------------
# Health added per coin for an active player, indexed by game_settings & 0x1F.
# ROM table at 0x57862, 32 words.
# Reference: doc/04_game_subsystems.md §10.1.
# ---------------------------------------------------------------------------
_HEALTH_PER_COIN_TABLE: list[int] = [
    100, 125, 150, 175, 200, 225, 250, 300,
    350, 400, 450, 500, 550, 600, 650, 700,
    750, 800, 850, 900, 950, 1000, 1100, 1200,
    1300, 1400, 1500, 1600, 1700, 1800, 1900, 2000,
]

# Per-player coin-slot sound, ROM longword table at 0x57002: red/blue/yellow/
# green (0x22-0x25 in refs/soundcmds.csv).  Played by player_coindrop
# (0x488FE) and by coincheck when an active player re-coins (0x42CB6); both
# index it by *player slot*, not by character, which is what
# doc/05_data_reference.md's "character announcement speech IDs" label misses.
_COIN_SLOT_SOUND: list[int] = [0x22, 0x23, 0x24, 0x25]

_CHARACTER_SELECT_CORNERS = (
    (13, 25, 0x841C), (14, 25, 0x841D), (11, 26, 0x841C), (16, 26, 0x841D),
    (11, 27, 0x841E), (16, 27, 0x841F), (13, 28, 0x841E), (14, 28, 0x841F),
)


# ROM: part game:0x44204 | Extracted portrait-name/instruction drawing portion of start_attract_to_game.
def _write_character_select_alpha(state: GameState) -> None:
    """start_attract_to_game's portrait names and ROM instruction chain."""
    positions = ((12, 24), (5, 26), (12, 29), (18, 26))  # ROM 0x570B4/0x570B8
    for klass, (column, row) in enumerate(positions):
        write_alpha_glyphs(
            state, column, row, romtext.CHARACTER_HUD_GLYPHS[klass], 0x8000,
        )
    # The corners around the portraits (0x442F6-0x4432A, tables 0x570BC-0x570DC).
    for column, row, word in _CHARACTER_SELECT_CORNERS:
        write_alpha_word(state, row * 64 + column, word)
    for text, column, row in romtext.CHARACTER_SELECT_LINES:
        write_alpha_large_text(state, column, row, text, 0x8C00)

# ---------------------------------------------------------------------------
# Module-private helpers
# ---------------------------------------------------------------------------

# ROM: helper | Python signed-byte representation helper for the spawn bonus.
def _signed_byte(value: int) -> int:
    """``monster_spawn_probability_bonus`` (0x90405F) is a signed byte."""
    value &= 0xFF
    return value - 0x100 if value & 0x80 else value


# ROM: helper | Python signed-longword wrap helper for health storage.
def _signed_long(value: int) -> int:
    """Store a wrapped 68000 longword in the port's signed-health convention."""
    value &= 0xFFFF_FFFF
    return value - 0x1_0000_0000 if value & 0x8000_0000 else value


# ROM: part game:0x4800C | Extracted settled Magic pattern test from main_start_game at 0x48402-0x48416; no separate ROM input predicate entry.
def _magic_press_edge(state: GameState, player_index: int) -> bool:
    """Return True on a settled Magic press edge.

    0x1C = 0b11100: bits 4-2 are three released frames (1s), bits 1-0 are
    two held frames (0s).  Active low: 1 = not pressed, 0 = pressed.  Matches
    the pattern ``main_start_game`` tests at 0x48402-0x48416 over
    ``debounce_shift_magic`` (0x905F58).
    Reference: doc/04_game_subsystems.md §6.4.
    """
    return (state.debounce_shift_magic[player_index] & 0x1F) == 0x1C


# ROM: direct game:0x44204 | Attract-to-session boundary with extracted character-select display and typed maze loading; does not reproduce every original blocking display phase.
# ROM: part game:0x44DB4,game:0x4800C | Inlines show_level_start_screen's mixer command and main_start_game's fresh-session welcome-counter reset instead of merely invoking those bodies.
def start_attract_to_game(state: GameState) -> None:
    """0x44204 -- begin a new session, leaving attract for gameplay (§6.4).

    Three callers reach this every frame regardless of the attract lockout: a
    coin arriving during attract (``coincheck`` 0x42BE2), a free-play Magic
    press (``main_start_game`` 0x484B8), and the attract timer expiring in mode
    0 with a player still holding health (``main_attract`` 0x448CE).

    Sets NORMAL and starts a fresh game: score reset and **level 1 (maze 0)
    loaded**, so a player who then commits a character (``main_start_game`` ->
    ``player_start_inner``, I-08) spawns into a real maze. Guarded via
    ``reset_and_load_level`` so a ROM-less environment still makes the mode
    transition (it just has no maze to spawn into).

    ``player_resetall`` (0x4341E) runs here only when the cabinet is leaving
    **DEMO** (0x4424A-0x44254): every other attract screen already reset the
    four slots on the way in (``start_attract_screen`` 0x4446E), and DEMO is the
    one screen that then builds a live hero of its own. That is the ROM's own
    split, and it is what stops a demo Elf's health, inventory and MOB from
    following the coin into the session.

    Also clears the transition machinery the ROM resets here: the theme fade and
    session-start sounds (0x4425A/0x4429A), the bonus/treasure hold
    (``global_delay_timer`` = 0 at 0x44366) and the attract countdown, which
    is parked on its 0xFFFF disabled sentinel at 0x4436C so ``main_attract``
    stops running until a screen loads a timer again.
    """
    from .player_lifecycle import player_resetall
    from .score import main_msgbox_countdown
    from .sound import sound_play

    # 0x44220-0x44232: a box still up (a demo tip, say) is retired at once, or
    # its timer would hold the new game's gameplay band still.
    if 0 < state.dialog_timer < 0x8000:
        state.dialog_timer = 1
        main_msgbox_countdown(state)
    state.dialog_once_flags = 0              # 0x4423A
    state.dialog_first_encounter_flags = 0   # 0x44244
    if state.game_mode == GameMode.DEMO:     # 0x4424A
        player_resetall(state)               # 0x44254
    sound_play(state, 0x3C)             # 0x4425A theme fade-out
    state.game_mode = GameMode.NORMAL   # 0x44266
    state.levelnum_current = 1          # 0x4426C
    state.mazenum_current = 0           # 0x4420E
    state.thief_item_carried = 0x7D30   # 0x44274-0x44280
    state.thief_item_nextlevel = 0x7D30
    state.mugger_item_carried = 0       # 0x44286-0x4428E
    state.mugger_item_nextlevel = 0
    sound_play(state, 0x02)             # 0x4429A session-start sting
    from .level_transitions import show_level_start_screen
    from .score import maze_hide

    maze_hide(state)                    # 0x442A6
    show_level_start_screen(state)      # 0x442AC
    state.global_delay_timer = 0               # 0x44366 global_delay_timer
    state.bonus_amount = 0
    state.treasure_timer = 0
    state.player_treascount = [0] * NUM_PLAYERS
    state.welcome_elapsed_frames = 0       # fresh session setup, 0x48692
    state.attract_timer = 0xFFFF        # 0x4436C: the attract machine stands down
    from .. import maze
    from .exits import exit_scan_level
    if maze.reset_and_load_level(state, 1):   # level 1 = maze 0 (I-08 spawn target)
        exit_scan_level(state)                # maze_new_level_setup exit table
        from .secret_rooms import secret_new_level_setup

        secret_new_level_setup(state)         # 0x43916-0x4395C
    _write_character_select_alpha(state)      # 0x442BC-0x44346


# Free-play / demo starting health, ROM word at 0x578A0 (player_coindrop
# 0x488EC and 0x4891C).  With paid pricing the health comes from
# _HEALTH_PER_COIN_TABLE instead.
_FREE_PLAY_START_HEALTH = 0x7D0     # 2000


# ROM: part game:0x488CA | Extracted free-play/paid-health choice from player_coindrop; the health table itself is data.
def configured_start_health(state: GameState) -> int:
    """The full health assigned when a player starts or continues."""
    if not state.two_player_mode:
        return _FREE_PLAY_START_HEALTH
    return _HEALTH_PER_COIN_TABLE[state.game_settings & 0x1F]


# ROM: direct game:0x488CA | Coin-credit/select initialization boundary; source's additional 0x4895C label is an interior location, not a second callable. Includes a Python stale-multiplier guard.
def player_coindrop(state: GameState, player_index: int) -> None:
    """0x488CA + ``player_coindrop`` (0x4895C) -- credit a player into select.

    Plays that slot's coin-slot sound (0x488FE), sets the starting health --
    the free-play/demo word at 0x578A0, or the coin-health table at 0x57862 under
    paid pricing (0x4890E-0x48946) -- zeroes the score (0x48954), sets
    ``player_coincount`` to **1** (0x48962), which is why the level-end bonus has
    a nonzero coin factor even on free play, resets the low-health cadence word
    (0x4896C), puts the player into SELECTING (0x4899C) and rebuilds its info
    panel (0x489A8).

    The DEMO branch at 0x488E4 takes the free-play health and skips the sound,
    because the demo's joins are scripted rather than paid for.
    """
    from .sound import sound_play

    player = state.players[player_index]
    if state.game_mode == GameMode.DEMO:                        # 0x488DC
        player.health = _FREE_PLAY_START_HEALTH                 # 0x488EC
    else:
        sound_play(state, _COIN_SLOT_SOUND[player_index & 3])   # 0x488FE
        player.health = configured_start_health(state)          # 0x4890E-0x4891C
    player.score = 0                                            # 0x48954
    # A valid ROM lifecycle already ran player_resetcounters before a dead slot
    # can be credited again. Reassert its 1x baseline here so a host-driven
    # fresh session cannot expose stale multiplier state.
    player.bonusmult = 1
    player.coin_count = 1                                       # 0x48962
    player.state_timer = 0xFFFF                                 # 0x4896C
    player.status = PlayerStatus.SELECTING                      # 0x4899C
    state.pending_character[player_index] = int(player.character)
    setup_infopanel(state, player_index)                        # 0x489A8


# ---------------------------------------------------------------------------
# Main-loop calls (WP-16)
# ---------------------------------------------------------------------------

# ROM: direct game:0x42B6A | Game-side packed coin-counter detection and player-health/credit handling; not the separate OS process_coins pricing body.
def coincheck(state: GameState) -> None:
    """0x42B6A -- coin detection, credit accounting, and coin-for-health.

    Coins inserted for an already-active player add health from the table at
    0x57862 indexed by ``game_settings & 0x1F``. A coin arriving during attract
    can begin a session at any point -- it consults no lockout threshold.

    Change-detection pattern: compare ``coin_counters`` (0x904FEC) against
    ``last_coin_state`` (0x9049EA).  If they differ, process all 4 player slots.
    Reference: doc/04_game_subsystems.md §10.1.
    """
    if state.coin_counters == state.last_coin_state:
        return

    # Capture the old value before overwriting it, so per-channel deltas are
    # computed correctly (doc §10.1: operand order corrected to new+4-old).
    old = state.last_coin_state
    state.last_coin_state = state.coin_counters

    # 0x42BA4: free play ignores coin effects, but the shadow still tracks the
    # hardware counters so switching pricing modes cannot replay old events.
    if state.two_player_mode == 0:
        return

    from .sound import sound_play

    for i in range(NUM_PLAYERS):
        # Each player channel occupies 2 bits at offset i*2 (0x904FEC layout).
        new_count = (state.coin_counters >> (i * 2)) & 3
        old_count = (old >> (i * 2)) & 3
        if new_count == old_count:
            continue

        # Global attract check (doc §10.1 / §6.4).  The extra DEMO branch
        # exists because demo heroes hold health while the cabinet is idle.
        all_zero_health = all(p.health == 0 for p in state.players)
        if (all_zero_health or state.game_mode == GameMode.DEMO) and state.game_mode < 0:
            # Leave attract and start a fresh game (level 1 loaded). Then fall
            # through so this same coin credits the triggering player below --
            # one coin both begins the session and enters that player into
            # character select, rather than needing a second coin. (game_mode is
            # now NORMAL and every player's health was just reset to 0.)
            start_attract_to_game(state)

        player = state.players[i]
        if player.health > 0:
            # Active player re-coining: top up health from 0x57862 table.
            table_index = state.game_settings & 0x1F
            health_add = _HEALTH_PER_COIN_TABLE[table_index]
            player.health = _signed_long(player.health + health_add)  # 0x42C2C
            player.coin_count += 1                       # 0x42C04
            # 0x42C30: a positive monster_spawn_probability_bonus is walked back
            # one step per extra coin, so paying to stay alive also buys a
            # slightly calmer level -- the counterweight to the bonus
            # update_monster_spawn_bonus_from_score_per_coin adds each level.
            if _signed_byte(state.monster_spawn_probability_bonus) > 0:
                state.monster_spawn_probability_bonus = (
                    state.monster_spawn_probability_bonus - 1
                ) & 0xFF                                 # 0x42C38
            state.player_lowhealth_spoken[i] = 0         # 0x42C46
            state.player_respawn_speech_timer[i] = -1    # 0x42C54
            player.state_timer = 0xFFFF                  # 0x42C64
            state.health_dirty[i] = 1                    # 0x42C72 player_redraw bit 1
            # The whole panel is rebuilt only while the player is still inside
            # their "coins to start" allowance (0x42C88-0x42CA4).
            coins_to_start = ((state.game_settings & 0x300) >> 8) + 1
            if player.coin_count <= coins_to_start:
                setup_infopanel(state, i)                # 0x42CA4
            sound_play(state, _COIN_SLOT_SOUND[i & 3])   # 0x42CB6
        else:
            # A coin for a hero entering initials ends the entry first, and the
            # continue prompt's own gates now see that hero as gone (0x42CCA-0x42CDE).
            if player.status == int(PlayerStatus.DYING):
                player.status = int(PlayerStatus.REMOVED)
                show_continue_prompt(state)
            # New player joining: player_coindrop (0x488CA) sets the
            # starting health, credits one coin, and enters character select.
            if state.credits > 0:
                state.credits -= 1
            player_coindrop(state, i)


# ROM: direct game:0x42DF4 | Per-player character-selection input boundary with active-low direction priority and panel redraw.
def character_select_input_update(state: GameState) -> None:
    """0x42DF4 -- character selection input. See §22.

    Per-frame handler.  For each player slot with status == SELECTING, reads
    the joystick and updates the tentative character.  Directional bits are
    tested active-low (bit clear = pressed) in priority order:

      bit 7 (0x80) clear → Warrior
      bit 5 (0x20) clear → Valkyrie
      bit 6 (0x40) clear → Wizard
      bit 4 (0x10) clear → Elf

    If the selection changes, ``pending_character`` and ``player.character``
    are updated and the info panel is redrawn.
    Reference: doc/04_game_subsystems.md §22.
    """
    for i in range(NUM_PLAYERS):
        player = state.players[i]
        if player.status != PlayerStatus.SELECTING:
            continue

        # Read joystick from 0x904920[player*2]+1 (low byte of the input word).
        # Switches are active low: a bit that is 0 means the direction is held.
        joy = state.player_input_raw[i]

        # Priority order matches the ROM: bit 7 → up, bit 5 → left,
        # bit 6 → down, bit 4 → right (doc §22).
        if not (joy & 0x80):
            new_char = Character.WARRIOR
        elif not (joy & 0x20):
            new_char = Character.VALKYRIE
        elif not (joy & 0x40):
            new_char = Character.WIZARD
        elif not (joy & 0x10):
            new_char = Character.ELF
        else:
            new_char = state.pending_character[i]  # no direction held: keep current

        if new_char != state.pending_character[i]:
            state.pending_character[i] = new_char
            player.character = new_char
            setup_infopanel(state, i)                    # 0x42E7E


# ROM: part game:0x4800C | Extracted multiplayer-only challenge cancellation inside main_start_game at 0x48294-0x482B2.
def _cancel_solo_only_trick(state: GameState) -> None:
    """0x48294-0x482B2 -- drop a multiplayer-only secret trick in solo play.

    Tricks 0x0F ("Be Pushy"), 0x10 ("IT Could Be Nice") and 0x11 ("Don't Hurt
    Friends") all need a second hero on the level, so with exactly one player
    active the objective is cleared rather than left unwinnable.
    """
    from .exits import _TRICK_MULTIPLAYER_FIRST, _TRICK_MULTIPLAYER_LAST
    from .secret_rooms import TRICK_NONE

    if not _TRICK_MULTIPLAYER_FIRST <= state.secret_trick_id <= _TRICK_MULTIPLAYER_LAST:
        return
    if state.level_players_active == 1:
        state.secret_trick_id = TRICK_NONE


# ROM: part game:0x4800C | Which Magic presses count, 0x4841A-0x484A4.
def _press_is_accepted(state: GameState, player_index: int) -> bool:
    player = state.players[player_index]
    selecting = player.status == int(PlayerStatus.SELECTING)
    coins_needed = ((state.game_settings & 0x300) >> 8) + 1
    if (
        player.health
        and (player.coin_count & 0xFFFF) >= coins_needed
        and selecting
        and state.game_mode >= 0
    ):
        return True
    if not state.two_player_mode:
        return selecting or not player.status or state.game_mode < 0
    return False


# ROM: part game:0x4800C | A hero entering a loaded level by way of player_join, or player_join_finalize in a secret room (0x485A8-0x485C2, 0x4869A-0x486B4). A level loaded by no one, as in a ROM-free front end, still counts the hero.
def _enter_the_level(state: GameState, player_index: int) -> None:
    player = state.players[player_index]
    player.character = state.pending_character[player_index]
    if state.mazenum_current >= 0x73:
        player_join_finalize(state, player_index)
        return
    placed = player_start_inner(state, player_index)
    if placed != -1 and state.maze is None:
        state.level_players_active += 1
        placed = -1
    if placed == -1:
        player_join_finalize(state, player_index)


# ROM: part game:0x4800C | The reload both first-hero arms share: 0x4853C-0x48576 and 0x4861E-0x48656.
def _reload_the_level(state: GameState) -> None:
    from .. import maze
    from .secret_rooms import secret_new_level_setup

    if state.level_next_potion == 3:
        state.level_next_potion = 0
    if maze.reset_and_load_level(
        state, state.levelnum_current, maze_number=state.mazenum_current,
    ):
        secret_new_level_setup(state)                  # 0x43916-0x4395C
    # These arms have no thief_setup (0x4835E), so main_start_thief must not run one.
    state.thief_level_setup_done = True


# ROM: part game:0x4800C | The first hero of a level with the reload: a continue (0x48512-0x4859C) or free play (0x48612-0x48692).
def _first_hero_reloads_the_level(
    state: GameState, player_index: int, *, enable_pickups: bool,
) -> None:
    from ..maze import maze_addrandompickups
    from .display import maze_show
    from .level_transitions import update_monster_spawn_bonus_from_score_per_coin

    _reload_the_level(state)
    _enter_the_level(state, player_index)
    update_monster_spawn_bonus_from_score_per_coin(state)
    maze_addrandompickups(state, enable_pickups)
    maze_show(state)
    state.welcome_elapsed_frames = 0


# ROM: part game:0x4800C | A Magic press once it counts, 0x484A8-0x486E2: every arm of the start, join and continue decision.
def _handle_start_press(state: GameState, player_index: int) -> None:
    from .display import maze_show
    from .sound import sound_play

    player = state.players[player_index]
    free_play = not state.two_player_mode
    if free_play and state.game_mode < 0:              # 0x484A8-0x484CA
        start_attract_to_game(state)
        player_coindrop(state, player_index)
        return
    if player.status != int(PlayerStatus.SELECTING):   # 0x484FE, 0x485EA, 0x486D4
        player_coindrop(state, player_index)
        return
    if state.global_delay_timer:                       # 0x486DC: the splash is still up
        player.character = state.pending_character[player_index]
        player_join_finalize(state, player_index)
        return
    if state.level_players_active:                     # 0x48508, 0x485F4
        _enter_the_level(state, player_index)
        return
    attract_timer = state.attract_timer & 0xFFFF
    if state.game_mode == 0 and attract_timer < 0x8000:   # 0x484D4-0x484E4: a continue
        setup_infopanel(state, -1)                     # 0x48524
        sound_play(state, 0x3C)                        # 0x4852A-0x48530
        _first_hero_reloads_the_level(state, player_index, enable_pickups=False)
    elif free_play and state.game_mode >= 0:           # 0x485FE-0x4860E
        _first_hero_reloads_the_level(state, player_index, enable_pickups=True)
    else:                                              # 0x4867E: a new game's level is loaded
        _enter_the_level(state, player_index)
        maze_show(state)                               # 0x4526A
        _mark_level_entry_overrun(state)
        state.welcome_elapsed_frames = 0               # 0x48692
        # Nothing on this path adds pickups or schedules a thief.
        state.random_pickups_setup_done = True
        state.thief_level_setup_done = True


# ROM: direct game:0x4800C | Game start/join/transition boundary; extracted helpers and ROM-less join fallback do not create additional ROM entries.
def main_start_game(state: GameState) -> None:
    """0x4800C -- turn a credited player into a hero in the maze.

    The start/join/character-commit press is on the **Magic** line, matching
    ``(debounce_shift_magic & 0x1F) == 0x1C`` at 0x48402-0x48416. It is not
    Fire; that was a documented correction. Use ``input.magic_press_edge``.

    For each player with SELECTING status and a settled Magic press:
      - Commits the pending character.
      - Awards a starting health of 800.
      - Spawns the hero through ``player_start_inner`` (0x48BEC) and finalizes
        the join through ``player_join_finalize`` (0x48A36), so the panel,
        welcome speech and ``level_players_active`` all follow the ROM's path.
      - ``player_start_inner`` applies the first-player class byte at 0x40E66
        to ``monster_spawn_probability_bonus``; it is not a score multiplier.

    In free play (``two_player_mode == 0``) a Magic press while in attract mode
    starts the session (``start_attract_to_game``, 0x484B8) and credits the
    pressing player into character select (``player_coindrop``, 0x484BE).
    Reference: doc/04_game_subsystems.md §6.4; PLAN.md §6 WP-16.
    """
    state.welcome_elapsed_frames = (
        state.welcome_elapsed_frames + 1
    ) & 0xFFFF_FFFF                                               # 0x48020

    # 0x48026-0x480B2: nothing below runs until the last hero is off the level,
    # one is waiting for the next (status bit 1, or bit 5 naming a secret) and the
    # shared effects in slots 13-16 have played out.
    statuses = 0
    for player in state.players:
        statuses |= int(player.status)
    if (
        state.level_players_active == 0
        and statuses & 0x22
        and not any(
            state.mobs.picture[slot] for slot in SLOT_SHOT_EXPLOSIONS
        )
    ):
        _level_handoff(state)
        if state.game_mode == int(GameMode.DEMO):
            return

    for i in range(NUM_PLAYERS):
        if _magic_press_edge(state, i) and _press_is_accepted(state, i):
            _handle_start_press(state, i)


# ROM: part game:0x42A66 | Models the overrun a level's entry causes, as MAME shows; see FIDELITY.md rule 110.
def _mark_level_entry_overrun(state: GameState) -> None:
    """The pass that puts heroes into a level's start outlasts a field on the arcade.

    Replays of piloted games on MAME (tools/mame_replay.py) show it at level 1's first
    hero and at each later level's entry after its splash, every time. The semaphore makes
    this tick's closing check set ``frame_overflow``, as level setup's does.
    """
    state.vblank_semaphore = 1


# ROM: part game:0x4800C | The level handoff at 0x480B6-0x483FC: the demo's end, the next level's commit, and the splash countdown that places the heroes.
def _level_handoff(state: GameState) -> None:
    # 0x480B6-0x480E2: the recorded actors are done. Reset the puppet party and
    # expire this attract screen; main_attract later in the frame goes to LEGEND.
    if state.game_mode == int(GameMode.DEMO):
        from .player_lifecycle import player_resetall
        from .score import main_msgbox_countdown

        player_resetall(state)                                    # 0x480C0
        state.attract_timer = 0                                   # 0x480C6
        if state.dialog_timer:
            state.dialog_timer = 1                                # 0x480D4
            main_msgbox_countdown(state)                           # 0x480DC
        return

    # 0x480E6: with the timer at zero the next level goes in, and its splash starts.
    if state.global_delay_timer == 0:
        from .level_transitions import _finish_level_end
        from .secret_rooms import secret_check

        secret_check(state)                                # 0x480EC
        state.levelnum_current = state.level_next          # 0x480F2
        state.mazenum_current = state.maze_next            # 0x48102
        _finish_level_end(state)
        return

    # global_delay_timer counts here, outside the dialog-gated world band
    # (0x4817C), so level splashes advance even while a message box freezes play.
    if state.global_delay_timer > 0:
        state.global_delay_timer -= 1
        if (
            state.global_delay_timer == 0x014A
            and state.mazenum_current >= 0x73
        ):
            from .sound import sound_play

            sound_play(state, 0x3B)                         # 0x4817C-0x48190
        # 0x48198-0x481D8: the room's clock stays up through the tally, counting its hold.
        if (state.game_mode == int(GameMode.TREAS_EXIT)
                and state.global_delay_timer % 60 == 0):
            from .display import write_alpha_large_text

            write_alpha_large_text(
                state, 34, 2, f"{state.global_delay_timer // 60:>2}", 0x8000,
            )
        if state.global_delay_timer == 0:
            from .treasure_rooms import _exiting_or_here
            from .level_transitions import _finish_level_end, _spawn_level_players

            if state.level_start_pending:
                from .display import maze_show

                state.level_start_pending = False
                maze_show(state)                       # 0x4526A
                _spawn_level_players(state, _exiting_or_here(state))
                _mark_level_entry_overrun(state)
            elif state.game_mode == int(GameMode.TREAS_EXIT):
                _finish_level_end(state, after_tally=True)
