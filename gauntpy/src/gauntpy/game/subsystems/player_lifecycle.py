"""Player join/reset, inventory display, health, and death-countdown routines."""

from __future__ import annotations

from .. import romtext
from ..constants import HEALTH_DRAIN_MASK, Character, GameMode, MazeObjIds, PlayerStatus
from ..coords import encode_hpos, encode_vpos_at_y
from ..state import NUM_PLAYERS, GameState
from .player_animation import _ANIM_TABLE_IDLE as _ANIM_TABLE_IDLE, update_player_sprite as update_player_sprite
from .player_names import _HIGHSCORE_NO_RANK as _HIGHSCORE_NO_RANK
from .sound import sound_play as _sound_play
from .sound import sound_speech_play as _sound_speech_play
from .player_data import (
    _LOW_HEALTH_THRESHOLD as _LOW_HEALTH_THRESHOLD,
    _SPEECH_CHARNAME_TBL as _SPEECH_CHARNAME_TBL,
    _STATE_TIMER_DISABLED as _STATE_TIMER_DISABLED,
)

# heartbeat_mask table at 0x576A8, seven words, transcribed from the ROM image
# (row76.bin offset 0x176A8): {0x1F, 0x3F, 0x3F, 0x7F, 0x7F, 0xFF, 0xFF}.  The
# eighth word there (0x0924) already belongs to score_star_picture_cycle
# (0x576B6) and is not part of this table.  §4.3 / main_health_countdown
# 0x46BC0-0x46BE2: index = health >> 5, the pulse fires when
# (player_state_timer & mask) == 0 -- smaller mask = more frequent.
# (The previous {1,3,7,15,31,63,127} entries were a plausible-looking guess and
# did not match the ROM: the real cadence never gets faster than every 32
# frames, and steps only three times across the whole 0-199 band.)
_HEARTBEAT_MASK_TABLE = [0x001F, 0x003F, 0x003F, 0x007F,
                             0x007F, 0x00FF, 0x00FF]

# Per-player low-health heartbeat sound, ROM 0x57942 (longwords, index =
# player).  Played by main_health_countdown at 0x46BEE, *not* by
# player_lowhealth -- that one is the spoken warning below.
_HEARTBEAT_SOUND_TABLE = [0x18, 0x19, 0x1A, 0x1B]

# character_lowhealth_speech, ROM 0x5797A (four longwords).  Selected by
# getrandom(3) for entries 0-2; entry 3 ("ALL YOUR POWERS WILL BE LOST!") is
# reachable only through the powers branch at 0x48812-0x48850 (05_data_reference
# §"0x5797A", Contradicted and corrected: the index is not the character).
_CHARACTER_LOWHEALTH_SPEECH = [0x5A, 0x5B, 0x5D, 0x5C]

# speech_welcome's lead-in phrase (0x4877A: ``pea.l $59.l``) and the
# 600-frame gate/reload it applies to welcome_elapsed_frames (0x48772/0x487BA).
_SPEECH_WELCOME_LEADIN = 0x59
_WELCOME_DELAY = 0x258

# player_lowhealth reloads player_respawn_speech_timer with 0x708 (0x488B8).
_LOWHEALTH_SPEECH_TIMEOUT = 0x708
_DAMAGE_COMMENT_SPEECH_IDS = (0x60, 0x5F)  # ROM 0x5B724
# player_coin_sound_ids, ROM 0x57952 (four longwords), indexed by character.
_PLAYER_COIN_SOUND_IDS = (0x09, 0x0A, 0x0B, 0x0C)

# random_item_group_ptrs/counts/values, ROM 0x578DA/0x578EA/0x5791A.
# Poison pickup and player death both choose one ungated character voice.
_RANDOM_ITEM_GROUP_VALUES = (
    (0xBB, 0x87),
    (0xB5,),
    (0xBA,),
    (0xB9, 0xBC),
)
_DIALOG_LOW_HEALTH = 0x00000004     # record 2, 0x4677E / 0x50EB0


def _play_random_character_voice(state: GameState, character: int) -> None:
    group = _RANDOM_ITEM_GROUP_VALUES[character & 0x03]
    _sound_play(state, group[state.getrandom(len(group))])


# =============================================================================
# Cross-package hooks
# =============================================================================
# main_move_players and player_tile_interact call these; the presentation half
# of each belongs to another work package, so each hook implements exactly the
# RAM-visible half the ROM performs and routes the rest through the state the
# owning package already reads.

def show_continue_prompt(state: GameState) -> None:
    """0x44C7E -- the five-line PRESS START continue prompt (§10.5).

    Verified gates, all of them RAM: ``level_players_active == 0``, a level
    other than 1, ``attract_timer`` not holding its disabled sentinel, and
    every player status either 0 or SELECTING (0x10).  When it draws, sound
    0x3B ("Gauntlet II Theme Song") plays and ``title_intro_state`` becomes 1.
    It does **not** decrement ``level_players_active``.

    The five text lines go through the fixed OS ``draw_string`` service; that
    is WP-2's, so this hook stops at the state the rest of the port reads.
    """
    if state.level_players_active != 0:
        return
    if state.levelnum_current == 1:
        return
    if state.attract_timer == 0xFFFF:
        return
    allowed = (int(PlayerStatus.REMOVED), int(PlayerStatus.SELECTING))
    if any(p.status not in allowed for p in state.players):
        return

    from .display import write_alpha_text

    _sound_play(state, 0x00)          # 0x44D06
    for text, column, row in romtext.CONTINUE_PROMPT_LINES:
        write_alpha_text(state, column, row, text, 0x8000)
    _sound_play(state, 0x3B)          # "Gauntlet II Theme Song" (§10.5)
    state.title_intro_state = 1


def setup_infopanel(state: GameState, player_selector: int) -> None:
    """0x452D0 -- redraw the info panel (§14.1).

    ``player_selector`` of -1 rebuilds the whole panel (the ROM loops 3->0);
    any other value redraws that player only.  Per §14.1 the body dispatches on
    player status and shares the numeric renderers ``draw_player_score``
    (0x45940) and ``draw_player_health`` (0x459A2) plus ``player_inv_update``,
    so this is a *synchronous* rebuild -- not a request for one.  It runs on
    join, on death (0x46AD0), and at every screen change, and the panel is
    expected to be right on the very next rendered frame rather than on that
    player's turn in ``main_score_display``'s four-frame rotation.

    So it drives WP-14's real latch: ``score``'s two draw routines write the
    ``PanelField`` the renderer reads, and the ``player_redraw`` bits (0x904908)
    are cleared because the draw the bits were asking for has just happened --
    the ROM clears them in ``draw_player_score``/``draw_player_health`` for the
    same reason.
    """
    from . import score

    if player_selector < 0:
        targets = range(NUM_PLAYERS)
    elif player_selector < NUM_PLAYERS:
        targets = range(player_selector, player_selector + 1)
    else:
        return
    if player_selector < 0:
        score.maze_hide(state)
        score.write_info_panel_header(state)
    for i in targets:
        score.write_player_panel_background(state, i)
        initials_entry = (
            state.players[i].status == int(PlayerStatus.DYING)
            and 0 <= state.players[i].highscore_rank < _HIGHSCORE_NO_RANK
        )
        if initials_entry:
            score.clear_player_panel_content(state, i)
            score.draw_player_initials_entry(state, i)
        elif state.players[i].status == int(PlayerStatus.SECRET_NAME_ENTRY):
            score.clear_player_panel_content(state, i)
            score.write_secret_name_entry(state, i)
        elif state.players[i].status != int(PlayerStatus.REMOVED):
            score.write_player_panel_static(state, i)
            score.draw_player_score(state, i)     # 0x45940
            score.draw_player_health(state, i)    # 0x459A2
            player_inv_update(state, i)            # 0x45522
        else:
            score.clear_player_panel_content(state, i)
            field = score.info_panel(state).players[i]
            field.score = state.players[i].score
            field.score_attr = score.PLAYER_TEXT_PALETTE_WORDS[i]
            field.score_drawn = True
            field.health = state.players[i].health
            field.health_attr = score.PLAYER_TEXT_PALETTE_WORDS[i]
            field.health_drawn = True
            field.bonusmult = state.players[i].bonusmult
        if not initials_entry and state.players[i].status != int(PlayerStatus.SECRET_NAME_ENTRY):
            score.write_player_panel_status(state, i)
        state.score_dirty[i] = 0               # player_redraw bit 0, serviced
        state.health_dirty[i] = 0              # player_redraw bit 1, serviced
    score.write_it_labels(state)


def speech_welcome(state: GameState, player_index: int) -> None:
    """0x48754 -- "Welcome, <character>" join speech (§4.4).

    Exact ROM shape (0x48754-0x487C8):

      * the lead-in phrase 0x59 is spoken when ``level_players_active`` is 1
        **or** ``welcome_elapsed_frames`` has reached 600 (0x48766/0x48772);
      * below 600 elapsed frames the routine stops there (0x4878C);
      * otherwise it speaks ``speech_charname_tbl[character + player * 4]``
        (0x596F6) and reloads ``welcome_elapsed_frames`` to 600 (0x487BA).

    Speech goes out through ``sound_speech_play`` (0x4AD4E), which is the same
    command ring ``sound_play`` uses, so it is queued here like any other sound.
    """
    if not 0 <= player_index < NUM_PLAYERS:
        return
    player = state.players[player_index]

    if state.level_players_active == 1 or state.welcome_elapsed_frames >= _WELCOME_DELAY:
        _sound_speech_play(state, _SPEECH_WELCOME_LEADIN)

    if state.welcome_elapsed_frames < _WELCOME_DELAY:
        return

    index = (player.character & 0x03) + player_index * 4
    _sound_speech_play(state, _SPEECH_CHARNAME_TBL[index])
    state.welcome_elapsed_frames = _WELCOME_DELAY


def player_inv_update(state: GameState, player_index: int) -> None:
    """0x45ACA -- redraw one player's key/potion row and power-up icons.

    Every pickup that changes ``keysnum``, ``potionsnum`` or ``powers`` calls
    it (0x515E4-0x51E0E), ``setup_infopanel`` calls it as part of the panel
    rebuild (0x45522), and loop 3 of ``main_score_update`` calls it every frame
    (0x470BA).  It is a pure draw: the ROM never touches ``player_redraw`` here,
    because it is not asking for a redraw later -- it is doing one now.

    ``PanelField`` latches score and health, while the compositor reads inventory
    counts from the same player record when it draws the alpha inventory row.
    Re-latching health here keeps the shared multiplier row current immediately.
    """
    from . import score

    if 0 <= player_index < NUM_PLAYERS:
        score.draw_player_health(state, player_index)
        score.write_player_inventory(state, player_index)


def player_lowhealth(state: GameState, player_index: int) -> None:
    """0x487CA -- the spoken low-health warning (§4.3).

    Call sites: main_health_countdown (0x46794, on a drain tick with health
    below 200) and player_damage_sample_update (0x50EC6).  Verified body:

      1. return immediately when ``player_lowhealth_spoken[p]`` is set
         (0x487DE) or ``player_respawn_speech_timer[p]`` is >= 0 (0x487F0) --
         the latch makes the warning one-shot per life, the timer spaces
         repeats after the latch is cleared;
      2. the "ALL YOUR POWERS WILL BE LOST!" phrase (entry 3) needs all three
         of: a non-zero ``player_powers & 0x00FF`` (0x4880A, a longword AND
         that keeps only the low byte), ``getrandom(8) > 3`` (0x4881C), and
         more than one power bit set among bits 0-7 (0x4884A);
      3. otherwise the phrase is ``getrandom(3)`` -> entries 0-2 (0x4885A);
      4. the chosen phrase is *preceded* by
         ``speech_charname_tbl[character + player * 4]`` (0x596F6), so the
         spoken sentence is two commands (0x48884 then 0x4889C);
      5. the latch is set and the timer reloads with 0x708 (0x488AA/0x488B8).

    05_data_reference's ``character_lowhealth_speech`` entry records the same
    Contradicted-and-corrected finding: the phrase index is *not* the
    character.
    """
    if not 0 <= player_index < NUM_PLAYERS:
        return
    if state.player_lowhealth_spoken[player_index]:
        return
    if state.player_respawn_speech_timer[player_index] >= 0:
        return

    player = state.players[player_index]
    phrase = None
    if player.powers & 0x00FF:                      # 0x4880A
        if state.getrandom(8) > 3:                  # 0x4881C: subq #3, ble skip
            bits = sum(1 for b in range(8) if player.powers & (1 << b))
            if bits - 1 > 0:                        # 0x4884A: more than one power
                phrase = 3
    if phrase is None:
        phrase = state.getrandom(3)                 # 0x4885A

    index = (player.character & 0x03) + player_index * 4
    _sound_speech_play(state, _SPEECH_CHARNAME_TBL[index])         # 0x48884
    _sound_speech_play(
        state, _CHARACTER_LOWHEALTH_SPEECH[phrase],
    )                                                               # 0x4889C
    state.player_lowhealth_spoken[player_index] = 1
    state.player_respawn_speech_timer[player_index] = _LOWHEALTH_SPEECH_TIMEOUT


def player_damage_sample_update(state: GameState, player_index: int) -> None:
    """0x50E34 -- advance the signed damage sample/commentary window."""
    from .player_items import (
        _dialog as _dialog,
    )

    player = state.players[player_index]

    if player.damage_sample_timer <= 0:
        player.damage_sample_timer += 1
        if player.damage_sample_timer:
            return
        player.damage_sample_count = 0
    else:
        player.damage_sample_timer -= 1
        if player.damage_sample_timer:
            return
        player.damage_sample_count = (player.damage_sample_count + 1) & 0xFFFF

        if (
            player.health < 500
            and player.pending_damage * 4 > player.health
        ):
            _dialog(state, player_index, _DIALOG_LOW_HEALTH)       # 0x50EB0
            player_lowhealth(state, player_index)

        if player.pending_damage > 20:
            player.cumulative_damage = min(
                player.cumulative_damage + player.pending_damage, 0x7D00
            )
        else:
            average = (
                player.cumulative_damage // player.damage_sample_count
                if player.damage_sample_count else 0
            )
            if average > 80 and player.damage_sample_count > 3:
                speech = _DAMAGE_COMMENT_SPEECH_IDS[state.getrandom(2)]
                _sound_speech_play(state, speech)                  # 0x50F58
                player.damage_sample_timer = -600
                player.cumulative_damage = 0
            elif average < 60:
                player.damage_sample_count = 0
                player.cumulative_damage = 0

    if player.damage_sample_timer:
        return

    player.damage_sample_timer = 60
    player.pending_damage = 0


def player_resetcounters(state: GameState, player_index: int) -> None:
    """0x43360 -- clear one player's whole per-slot record.

    Transcribed store for store from 0x4336A-0x43414: keys (0x90405A),
    potions (0x904055), status (0x9049A0) and the MOB slot (0x9048C8) are
    zeroed, ``player_bonusmult`` (0x90490E) goes back to 1,
    ``player_state_timer`` (0x904A26) to its 0xFFFF disabled sentinel,
    ``player_powers`` (0x9048E0) and the four timed-power countdowns
    (invisibility 0x905F50, repulsiveness 0x905F38, acid 0x905F40, supershot
    0x905F68) are cleared along with ``player_stundelay`` (0x904A54), and the
    transport phase word (0x904BCE) is parked on -1.

    It is called from ``player_resetall`` and from the ROM's own death path
    (main_health_countdown 0x4699A), which is what makes death a genuine
    inventory wipe rather than a status change.
    """
    player = state.players[player_index]
    player.keysnum = 0                                       # 0x90405A
    player.potionsnum = 0                                    # 0x904055
    player.status = int(PlayerStatus.REMOVED)                # 0x9049A0
    player.mob_slot = 0                                      # 0x9048C8
    player.bonusmult = 1                                     # 0x90490E
    player.state_timer = _STATE_TIMER_DISABLED               # 0x904A26
    player.powers = 0                                        # 0x9048E0
    state.player_invis_timer[player_index] = 0               # 0x905F50
    state.player_repulse_timer[player_index] = 0             # 0x905F38
    player.acid_timer = 0                                    # 0x905F40
    player.supershot = 0                                     # 0x905F68
    player.stundelay = 0                                     # 0x904A54
    state.player_tport_phase[player_index] = -1              # 0x904BCE = 0xFFFF
    state.player_fighting_dir[player_index] = 0               # 0x9049AC
    state.player_shooting[player_index] = 0                   # 0x9049B4
    state.player_walking[player_index] = 0                    # port-side frame result
    player.exit_pending = 0


def player_hurt_palette_vblank(state: GameState) -> None:
    """0x401DE-0x40304 -- perform the live player MOB-palette writes."""
    from .display import player_palette_vblank

    player_palette_vblank(state)


def player_resetall(state: GameState) -> None:
    """0x4341E -- reset all four players for a fresh session.

    Loops 3 down to 0 calling ``player_resetcounters`` and clearing that
    player's score (0x904990) and health (0x904980), then zeroes
    ``level_players_active`` (0x904928) and reassigns the default character
    per slot, {0, 1, 2, 3} (0x4345E-0x4347C).

    ``start_attract_screen`` calls it on **every** screen change (0x4446E), so
    no attract screen can ever be reached with a live hero's inventory, powers,
    timers or status still set.
    """
    for player_index in range(NUM_PLAYERS - 1, -1, -1):      # 0x43426: d2 = 3
        player_resetcounters(state, player_index)
        state.players[player_index].score = 0                # 0x9043E
        state.players[player_index].health = 0               # 0x4344C
    state.level_players_active = 0                           # 0x43458
    for player_index in range(NUM_PLAYERS):                  # 0x4345E-0x43474
        state.players[player_index].character = Character(player_index)


def calc_score_per_coin(state: GameState, player_index: int) -> int:
    """0x40628 as main_health_countdown calls it at 0x46A18-0x46A48.

    A plain 32-by-16 unsigned divide of ``player_score`` (0x904990) by
    ``player_coincount`` (0x904B2A), stored into ``player_scorepercoin``
    (0x904B1A).  This -- not the raw score -- is the value the high-score
    ladder ranks (§10.3), which is why a four-coin run has to earn four times
    the score to place.  The ROM would divide by zero on a coinless player;
    every player credited through ``player_coindrop`` (0x48962) has at least
    one coin, so the floor below only matters for a directly placed hero.
    """
    player = state.players[player_index]
    player.score_per_coin = player.score // max(1, player.coin_count)
    return player.score_per_coin


def player_start_inner(state: GameState, player_index: int) -> int:
    """0x48BEC -- find a spawn tile and turn it into the player MOB (§4.4).

    Returns -1 on success (a PLAYERSTART was found and claimed), 0 when no
    usable spawn position exists. Without a loaded maze (``state.maze`` is
    None) always returns 0.

    The PLAYERSTART marker MOB *becomes* the hero: same slot, same cell, and
    ``maze.py`` already placed it with the hero base picture (0x1e0d). Its
    ``obj_type`` stays PLAYERSTART, **not** a MONST_* type -- ``main_move_monsters``
    dispatches on ``obj_type``, so a monster type here would make the sim move
    and damage the hero (a bug the playable runner first hit, N-05). Rendering
    keys off the picture, which the runner refines per-frame by character and
    facing.  The state word takes the player index, which is what charges damage
    to the right hero once the record starts migrating between cells.

    Multi-player: a start cell already claimed by another player's ``mob_slot``
    is skipped, so up to four heroes take distinct PLAYERSTARTs when the maze
    provides them.  A player joining a level already in progress is placed in an
    empty cell next to a hero that is already in the maze, and that hero's
    ``mob_slot`` *is* its current cell, so the scan starts from the record.
    """
    if state.maze is None:
        return 0

    player = state.players[player_index]
    claimed = {
        state.players[j].mob_slot
        for j in range(NUM_PLAYERS)
        if j != player_index and state.players[j].mob_slot
    }
    slot = 0
    if state.level_players_active:
        for other in state.players:
            if other.index == player_index or not other.mob_slot:
                continue
            # ``active_mob_ids`` names the cell the hero is standing in, so the
            # adjacent-cell scan starts from the record itself.
            base = other.mob_slot
            for candidate in (
                (base & 0x3E0) | ((base - 1) & 0x1F),
                (base & 0x3E0) | ((base + 1) & 0x1F),
                (base - 0x20) & 0x3FF,
                (base + 0x20) & 0x3FF,
            ):
                if candidate > 0x20 and state.mobs.picture[candidate] == 0:
                    slot = candidate
                    break
            if slot:
                break
    else:
        state.player_it = 0xFFFF                                  # 0x48C08
        slot = state.maze_player_start_slot                       # 0x48C10
        if not slot:
            # Hand-built ROM-free/test mazes may omit maze_scan_objects(-1).
            slot = next(
                (
                    candidate for candidate in state.mobs.iter_chain()
                    if state.mobs.obj_type(candidate)
                    == int(MazeObjIds.PLAYERSTART)
                    and candidate not in claimed
                ),
                0,
            )

    if slot:
        from .display import init_player_mob_palette

        init_player_mob_palette(state, player_index, int(player.character))
        player.mob_slot = slot
        # player_start_inner rebuilds the marker as a real 3x3 hero MOB:
        # X origin -4 px, palette 0xC+player, packed size 0x12
        # (0x48DD0-0x48DF6).
        spawn_x = (slot & 0x1F) * 16 - 4
        spawn_y = ((slot >> 5) & 0x1F) * 16
        spawn_hpos = encode_hpos(
            spawn_x, (player_index + 0x0C) & 0x0F,
        )
        spawn_vpos = encode_vpos_at_y(spawn_y, 3, 3)
        initial_picture = _ANIM_TABLE_IDLE[
            (int(player.character) & 0x03) * 8 + 4
        ]
        if slot in state.mobs.iter_chain():
            state.mobs.hpos[slot] = spawn_hpos
            state.mobs.vpos[slot] = spawn_vpos
            state.mobs.picture[slot] = initial_picture
            state.mobs.set_obj_type(slot, int(MazeObjIds.PLAYERSTART))
            state.mobs.set_state(slot, player_index)
        else:
            state.mobs.create(
                slot,
                tile=initial_picture,
                hpos=spawn_hpos,
                vpos=spawn_vpos,
                obj_type=int(MazeObjIds.PLAYERSTART),
                state=player_index,
            )
        player.direction = 2                # facing down (§4.4)
        player.death_damage_counter = 0
        player.pending_damage = 0
        player.cumulative_damage = 0
        player.damage_sample_count = 0
        player.damage_sample_timer = 60
        player.hurt_cooldown = 0
        state.forcefield_hurt_timer[player_index] = 0
        state.death_touch_timer[player_index] = 0                 # 0x48E62-0x48EBE
        state.secret_tricks_flags[player_index] = 0xFF            # 0x48EDC
        # 0x48E86: the same per-player init run clears this level's treasure
        # credit, so a hero carrying a count from the last level cannot be paid
        # for it twice by show_level_end_bonus_screen (0x4D57E).
        state.player_treascount[player_index] = 0
        state.player_in_maze[player_index] = 1
        state.player_tile_or_tport_dest[player_index] = slot
        state.level_players_active += 1
        if state.level_players_active == 1:
            # The hardware level-start path has already framed the PLAYERSTART
            # before input is accepted. In the port the hero is the first point
            # at which that target exists, so initialize the camera here rather
            # than letting the offscreen gate pin the player for a long pan.
            from .camera import snap_camera

            snap_camera(state)
        # ROM byte table at 0x40E66, indexed by the first active player's
        # character. 0x48EF6 writes it to monster_spawn_probability_bonus;
        # subsequent joins clear that byte at 0x48F00. It is not bonusmult.
        first_player_spawn_bonus = (3, 0, 4, 0)
        if state.level_players_active == 1:
            state.monster_spawn_probability_bonus = first_player_spawn_bonus[
                player.character & 0x03
            ]
        else:
            state.monster_spawn_probability_bonus = 0
        return -1

    _sound_play(state, 0x43)                              # 0x48C94-0x48C9A
    return 0  # no usable spawn position


def player_join_finalize(state: GameState, player_index: int) -> None:
    """0x48A36 -- set active status, play join sound, redraw HUD (§4.4).

    Performs coin initialization when necessary, persists configuration,
    sets status/on-level state, plays character join sound, redraws HUD,
    calls speech_welcome.

    The coin-initialisation half is ``player_coindrop`` (0x488CA, WP-16), whose
    per-player resets that belong to this file are re-applied here: the
    low-health cadence timer takes its disabled sentinel (0x48972), the spoken
    warning latch clears (0x48980) and the speech spacing timer goes negative
    (0x4898E), so a joining hero starts able to be warned again.
    """
    player = state.players[player_index]
    if (
        (not state.two_player_mode or state.game_mode == int(GameMode.DEMO))
        and player.status == int(PlayerStatus.REMOVED)
    ):
        from .session import player_coindrop

        player_coindrop(state, player_index)
    player.status = PlayerStatus.ALIVE_HERE  # §4.4
    player.anim_counter = 0
    state.player_fighting_dir[player_index] = 0
    state.player_shooting[player_index] = 0
    state.player_walking[player_index] = 0
    player.state_timer = _STATE_TIMER_DISABLED             # 0x48972
    state.player_lowhealth_spoken[player_index] = 0        # 0x48980
    state.player_respawn_speech_timer[player_index] = -1    # 0x4898E
    _sound_play(
        state, _PLAYER_COIN_SOUND_IDS[player.character & 0x03],
    )                                                       # 0x48AB2-0x48ABC
    speech_welcome(state, player_index)
    setup_infopanel(state, player_index)
    update_player_sprite(state, player_index)


def player_join(state: GameState, player_index: int) -> None:
    """0x48BB6 -- outer wrapper: place player in world if possible (§4.4).

    Calls player_start_inner; on success calls player_join_finalize.
    """
    result = player_start_inner(state, player_index)
    if result == -1:
        player_join_finalize(state, player_index)


def main_health_countdown(state: GameState) -> None:
    """0x466F6 -- flat health drain and low-health warning cadence (§4.3).

    **Drain is flat**: ``subq.l #1`` gated on ``frame_counter & 0x3F`` at
    0x4670C/0x4675E -- one point per player per 64 frames in every game mode,
    with **no class, power, or difficulty term** (Contradicted and corrected,
    §4.3 TRAP 1).  Health is a 32-bit longword (§4.3 TRAP 2); no masking.

    The drain has four gates, all read straight off the ROM's own loop
    (0x46720-0x46758) and all of them previously missing here:

      * ``player_health != 0`` -- a player already at zero is on the death
        path, so the drain cannot push health negative;
      * ``player_status == 1`` exactly (ALIVE_HERE);
      * ``active_mob_ids[p] != 0`` -- no MOB, no drain;
      * ``acid_timer == 0`` (0x905F40) -- an acid-slowed player stops draining.

    Each drained point raises ``player_redraw`` bit 1 (0x4676A) and, below 200
    health, calls ``player_lowhealth`` (0x46794) -- **on the drain tick, not on
    the heartbeat cadence**.  The two were conflated here before.

    The heartbeat is the second pass (0x467AC-0x46BF8), which runs every frame
    for every player that has a MOB:

      * ``player_respawn_speech_timer`` counts down while non-negative
        (0x467C2-0x467D8);
      * below 200 health ``player_state_timer`` advances modulo 0x8000
        (0x46BAC) and the per-player sound at 0x57942 (0x18 + player) plays
        whenever ``timer & heartbeat_mask[health >> 5]`` is zero
        (0x46BC0-0x46BF2);
      * at 200 or more the ROM simply *stops advancing* the timer -- it does
        not write 0xFFFF here.  §4.3 attributes that reset to this routine, but
        the only writers are player_resetcounters (0x433B4), coincheck (0x42C64)
        and the food branch of player_tile_interact (0x51D24).
    """
    from .player_items import (
        _dialog as _dialog,
    )

    drain_this_frame = (state.frame_counter & HEALTH_DRAIN_MASK) == 0

    # ── Flat drain pass (0x4671C-0x4679E), all four players ───────────────────
    if drain_this_frame:
        for player_index, player in enumerate(state.players):
            if player.health == 0:                          # 0x46720
                continue
            if player.status != int(PlayerStatus.ALIVE_HERE):   # 0x46730
                continue
            if player.mob_slot == 0:                        # 0x46744
                continue
            if player.acid_timer != 0:                      # 0x46754
                continue
            player.health -= 1  # 32-bit longword; no mask (§4.3 TRAP 2)
            state.health_dirty[player_index] = 1            # player_redraw bit 1
            if player.health < _LOW_HEALTH_THRESHOLD:       # 0x46774
                _dialog(state, player_index, _DIALOG_LOW_HEALTH)  # 0x4677E
                player_lowhealth(state, player_index)   # 0x46794

    # ── Per-frame pass (0x467AC-0x46BF8), all four players ────────────────────
    for player_index, player in enumerate(state.players):
        if player.mob_slot == 0:                            # 0x467BA
            continue

        if state.player_respawn_speech_timer[player_index] >= 0:   # 0x467C8
            state.player_respawn_speech_timer[player_index] -= 1

        if player.health == 0:                              # 0x467E0: death path
            continue
        if player.health >= _LOW_HEALTH_THRESHOLD:          # 0x46B86
            continue

        player.state_timer = (player.state_timer + 1) & 0x7FFF     # 0x46BAC
        # Mask table at 0x576A8; index = health >> 5.  The ROM does not clamp,
        # but health here is 1..199 so the index is already 0..6.
        mask_idx = max(0, min(player.health >> 5,
                              len(_HEARTBEAT_MASK_TABLE) - 1))
        if (player.state_timer & _HEARTBEAT_MASK_TABLE[mask_idx]) == 0:
            _sound_play(state, _HEARTBEAT_SOUND_TABLE[player_index])     # 0x46BEE


def main_handle_death(state: GameState) -> None:
    """0x4664C -- forcefield and death sound timers (§21).

    Two looping-sound timer systems per player.  Contact code (in
    main_move_players at 0x4AA42-0x4AAB8) sets these to a *negative* value on
    fresh contact.  This function detects the sign (negative = new contact),
    plays the start sound, negates to begin a positive countdown, decrements
    each frame, and plays the stop sound when the timer reaches zero.

    Forcefield hurt timer (0x904B4A[player*2]):
        negative → sound 0x2E ("Player Touches Force Field"), negate
        zero (after countdown) → sound 0x2F ("Force Field Silencer")

    Death touch timer (0x904B42[player*2]):
        negative → sound 0x20 ("Death Touches Player"), negate
        zero (after countdown) → sound 0x21 ("Death Silencer")
    """
    for i in range(NUM_PLAYERS):
        # ── Forcefield hurt timer ─────────────────────────────────────────────
        ff = state.forcefield_hurt_timer[i]
        if ff < 0:
            # New contact: play start sound, flip to positive countdown.
            _sound_play(state, 0x2E)  # "Player Touches Force Field" (§21)
            state.forcefield_hurt_timer[i] = -ff
        elif ff > 0:
            state.forcefield_hurt_timer[i] = ff - 1
            if state.forcefield_hurt_timer[i] == 0:
                _sound_play(state, 0x2F)  # "Force Field Silencer" (§21)

        # ── Death touch timer ─────────────────────────────────────────────────
        dt = state.death_touch_timer[i]
        if dt < 0:
            # New contact: play start sound, flip to positive countdown.
            _sound_play(state, 0x20)  # "Death Touches Player" (§21)
            state.death_touch_timer[i] = -dt
        elif dt > 0:
            state.death_touch_timer[i] = dt - 1
            if state.death_touch_timer[i] == 0:
                _sound_play(state, 0x21)  # "Death Silencer" (§21)
