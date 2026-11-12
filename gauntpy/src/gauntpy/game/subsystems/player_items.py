"""Player powers, pickup dispatch, door opening, and trap bookkeeping."""

from __future__ import annotations

from ..constants import FIRST_PLAYABLE_SLOT, POWERUP_BIT_MASKS, POWERUP_ITEM_ID, MazeObjIds, PlayerStatus
from ..state import NUM_PLAYERS, GameState
from .sound import sound_play as _sound_play
from .sound import sound_speech_play as _sound_speech_play
from .player_data import (
    _LOW_HEALTH_THRESHOLD as _LOW_HEALTH_THRESHOLD,
    _SPEECH_CHARNAME_TBL as _SPEECH_CHARNAME_TBL,
    _STATE_TIMER_DISABLED as _STATE_TIMER_DISABLED,
    _WALL_PICTURE as _WALL_PICTURE,
)

# =============================================================================
# Power-ups (§4.6; ROM 0x59B64 / 0x4C72A / 0x517BA-0x518B0)
# =============================================================================
#
# ``constants.PlayerPower`` carries the masks and records how they were pinned
# down.  What lives here is the rest of each arm: the countdown each power arms
# and the speech that announces it.

#: ``powerup_speech_ids`` -- ROM 0x59B7C, 12 longwords parallel to
#: ``POWERUP_BIT_MASKS``; a zero entry means the pickup speaks nothing.
_POWERUP_SPEECH_IDS = (
    0x8F, 0x90, 0x91, 0x92, 0x93, 0x94,
    0x8E, 0xD1, 0xCF, 0xD0, 0x00, 0x00,
)

#: POWER_INVIS arms ``invis_timer`` with 0x4B0 frames (0x517D4).
_INVIS_TIMER_LOAD = 0x4B0

#: POWER_REPULSE arms the repulsiveness countdown from the character-indexed
#: table at ROM 0x5B72C (0x5181A).  Bit 9 is what 0x4185C tests to make a
#: monster flee; doc/05 calls both the timer and this table "reflect", which is
#: a different power (bit 10, type 0x38, read at 0x4B4B0 and with no timer).
_CHARACTER_REPULSE_TIMER_INIT = (0x038C, 0x04B8, 0x0260, 0x038C)

#: POWER_SUPERSHOT adds eleven charges (0x51874 ``addi.b #$b``).
_SUPERSHOT_CHARGES = 0x0B

#: POWER_INVULN arms the 0x905F40 countdown with 0x384 frames (0x5189E).
_INVULN_TIMER_LOAD = 0x384


# ROM: part game:0x511AC | Extracted temporary-power timer/charge writes from pickup arms at 0x517BA-0x518B0; also exposed for direct test-game setup.
def initialize_player_temporary_power(
    state: GameState, player_index: int, obj_type: int,
) -> None:
    """Install one power-up tile's live state for a direct test-game start."""
    item_id = POWERUP_ITEM_ID.get(int(obj_type))
    if item_id is None or item_id < 6:
        raise ValueError(f"not a temporary power-up object type: {obj_type}")
    player = state.players[player_index]
    player.powers |= POWERUP_BIT_MASKS[item_id]
    if obj_type == int(MazeObjIds.POWER_INVIS):
        state.player_invis_timer[player_index] = _INVIS_TIMER_LOAD
    elif obj_type == int(MazeObjIds.POWER_REPULSE):
        state.player_repulse_timer[player_index] = (
            _CHARACTER_REPULSE_TIMER_INIT[player.character & 0x03]
        )
    elif obj_type == int(MazeObjIds.POWER_SUPERSHOT):
        player.supershot = (player.supershot + _SUPERSHOT_CHARGES) & 0xFF
    elif obj_type == int(MazeObjIds.POWER_INVULN):
        player.invuln_timer = _INVULN_TIMER_LOAD


#: The treasure-room maze band (0x519FE/0x51A08): mazes 0x68 through 0x72 skip
#: the bonus-multiplier block and settle up on the bonus screen instead.
_TREASURE_ROOM_MAZES = range(0x68, 0x73)


# =============================================================================
# First-encounter dialogs (§10.4; dialog_first_encounter 0x4C440)
# =============================================================================
#
# The routine takes a 32-bit mask whose set bit number selects the message
# record, plus an optional numeric value the record interpolates.  These are the
# masks pushed at the call sites inside this file's routines; the records
# themselves live in ``score.DIALOG_MESSAGES``.
#
# Records reached from *other* modules, listed so nobody re-wires them here:
# record 4 ("COLLECT MAGIC POTION BEFORE PRESSING MAGIC") is main_handle_potions'
# (0x470CC/0x47134, potions.py), record 7 ("SHOOTING POISON SLOWS MONSTERS") is a
# shot-hit dialog (0x4B8FA/0x4BA50, shots.py), and record 15 ("AVOID ACID
# PUDDLES") comes from monster_playerhit's per-monster-type mask held in A4
# (0x4986A/0x49A2C, monsters.py) rather than from any fixed literal.

_DIALOG_FOOD = 0x00000001           # record 0, 0x51CDE / 0x51C00
_DIALOG_KEYS = 0x00000008           # record 3, 0x51620
_DIALOG_SAVE_POTIONS = 0x00000020   # record 5, 0x51796
_DIALOG_POISONED = 0x00002000       # record 13, 0x516BE / 0x51CAA
_DIALOG_INVENTORY_FULL = 0x02000000  # record 25, 0x5147C / 0x5170A
_DIALOG_TRAP = 0x00800000           # record 23, 0x51278
_DIALOG_STUN_FLOOR = 0x04000000     # record 26, 0x51388
_DIALOG_FAKE_EXIT = 0x40000000      # record 30, 0x513EC

#: hpos bit 4 (0x513E4 ``btst #4`` on the low byte) marks an exit as an
#: illusion.  §8.2 calls hpos bits 5-4 the MOB's two software flags.
_FAKE_EXIT_FLAG = 0x0010

# Secret-room objective codes this subsystem reports progress on.  WP-15
# (``secret_rooms.secret_trick_progress``/``secret_trick_set``) owns the counter and
# the ``secret_trick_id`` guard; these are just the literals the ROM compares.
_TRICK_NOGREEDY1 = 12       # 0x0C -- "don't be greedy": keys or potions
_TRICK_NOUSEINVUL = 8       # 0x08 -- "don't use invulnerability"
#: 0x5140A -- the fooled-by-a-fake objective, an assignment like 0x518B2.
_TRICK_NOFOOLED = 11
#: The food arm reports 0x0D (0x51C0C/0x51CEE).  The treasure arm's own codes
#: -- 0x0E (0x519C2), 0x50 (0x519CE) and 0x5A (0x519DA) -- belong to the same
#: ROM block as the count bump and are reported by ``secret_rooms.treasure_collected``.
#: Note that WP-15's ``TRICK_NOGREEDY2 = 13``/``TRICK_DIET = 14`` comments read
#: the other way round from the ROM's compares; these follow the ROM.
_TRICK_FOOD = 0x0D
#: Objective codes from the 0x50-0x5D band rather than the 1-17 trick
#: numbering.  The hidden pot answers to two of them (0x518FA/0x51908), and in
#: every such case the alternatives share one ``addq.b #1``.
_TASK_HIDDENPOT_A = 0x51
_TASK_HIDDENPOT_B = 0x5D

#: A key is worth 100 before the bonus multiplier (0x514F4 ``pea $64``).
_KEY_SCORE = 0x64
_KEY_PICTURE = 0x0AFC           # single key, 0x515A2 and 0x4686E
_KEY_PILE_PICTURE = 0x1D76      # several keys, 0x46876

#: player_tile_interact's transporter result: the teleport has started.
TILE_TELEPORTED = -2

#: Per-character food speech, ROM pointer/count tables 0x5B7C0/0x5B7D0.
_FOOD_SPEECH_IDS = (
    (0x88, 0x82, 0x81),     # Warrior
    (0x8A, 0xA9),           # Valkyrie
    (0x69, 0x6F, 0x71),     # Wizard
    (0x77, 0x76),           # Elf
)

#: Food pictures and effects verified against 0x51ADC-0x51CFE.
_RANDOM_FOOD_PICTURE = 0x277B
_POISONED_FOOD_PICTURE = 0x25ED
_POISONED_POTION_PICTURE = 0x20FC
_RANDOM_FOOD_HEALTH = (
    100, 50, 75, 100, 75,
    50, 25, 200, 25, 50,
    75, 100, 75, 100, 25,
    200, 75, 25, 50, 100,
)
# ``pickup_score_popup_types`` (0x5B774), parallel to the adaptive food table.
_PICKUP_SCORE_POPUP_TYPES = (
    13, 11, 12, 13, 12, 11, 10, 14, 10, 11,
    12, 13, 12, 13, 10, 14, 12, 10, 11, 13,
)

#: Poisoning costs 50 health (0x51C48/0x5164E) -- the same 50 the record's
#: "PLAYER LOSES %d HEALTH" line is passed -- and arms the dizzy countdown with
#: 0x4B0 frames (0x51C68/0x5166E).
_POISON_DAMAGE = 0x32
_DIZZY_TIMER_LOAD = 0x4B0
_GAME_SETTINGS_REDUCE_TEXT = 0x0400


# ROM: adapter game:0x4C440 | Delegation boundary for dialog_first_encounter; the implementing body is score.dialog_first_encounter.
def _dialog(state: GameState, player_index: int, mask: int,
            value: int = 0) -> None:
    """``dialog_first_encounter`` (0x4C440) -- WP-14's real message box.

    A cross-subsystem call, because score.py owns the record text, the one-shot
    flags, the box geometry and the speech, and its ``dialog_timer`` is what
    gates the gameplay band for the frames the box is up (§10.4).
    """
    from . import score

    score.dialog_first_encounter(state, player_index, mask, value)


# ROM: part game:0x511AC | Coalesces poison-food and poison-potion arms within the same tile-interaction entry; not a merger of separate callables.
def _poisoned(state: GameState, player_index: int) -> None:
    """0x51C40-0x51CB4 (food) and 0x51644-0x516C8 (potion) -- the bad variant.

    Both arms are the same code twice: take 50 health with a floor at zero, arm
    the dizzy countdown, speak a character-random hurt line, and show record 13
    with 50 as its interpolated value.
    """
    from .player_lifecycle import (
        _play_random_character_voice as _play_random_character_voice,
    )

    player = state.players[player_index]
    player.health = max(0, player.health - _POISON_DAMAGE)   # 0x51C4A/0x51C5A
    state.player_dizzy_timer[player_index] = _DIZZY_TIMER_LOAD  # 0x51C68
    _play_random_character_voice(state, player.character)
    _dialog(state, player_index, _DIALOG_POISONED, _POISON_DAMAGE)


# ROM: helper | Python delegation shim to the parameterized secret-task progress helper; no separate ROM progress callable.
def _secret_trick_progress(state: GameState, player_index: int,
                           trick_id: int, amount: int = 1) -> None:
    """WP-15's ``secret_rooms.secret_trick_progress`` -- the ``addq.b #1`` hook shape.

    Every progress site in the ROM is ``cmpi.b #<trick>,secret_trick_id`` followed
    by a bump of that player's ``secret_tricks_flags`` byte, so the guard lives
    in WP-15's routine and the call sites here stay one line each.
    """
    from .secret_rooms import secret_trick_progress

    secret_trick_progress(state, player_index, trick_id, amount)


# ROM: helper | Python delegation shim to the parameterized secret-task assignment helper; no separate ROM setter callable.
def _secret_trick_set(state: GameState, player_index: int,
                      trick_id: int, value: int) -> None:
    """WP-15's ``secret_rooms.secret_trick_set`` -- the ``move.b #n`` hook shape."""
    from .secret_rooms import secret_trick_set

    secret_trick_set(state, player_index, trick_id, value)


# ROM: part game:0x511AC | Delegated treasure-credit/progress arm at 0x519C2-0x519F8; the extracted counter writes are owned by secret_rooms.treasure_collected.
def _treasure_collected(state: GameState, player_index: int) -> None:
    """0x519F0-0x519F8 -- credit one treasure to the player who took it.

    ``player_treascount`` (0x904A50) is the treasure factor of the per-player
    level-end bonus (0x4D57E), so a pickup has to name its collector rather than
    only bumping the level total.  WP-15 owns that counter and exposes
    ``secret_rooms.treasure_collected`` as its single write site.

    Function-local import for the same reason ``player_exit_sequence`` uses one:
    exits.py re-enters this module for the post-transition respawn.

    0x519C2/0x519CE/0x519DA -- the three objective codes that share the
    ``addq.b #1`` at 0x519EC -- are part of the same ROM block and are reported
    by ``secret_rooms.treasure_collected`` itself, so this arm must not repeat them or
    a "collect six treasures" task would finish in three pickups.
    """
    from .secret_rooms import treasure_collected

    treasure_collected(state, player_index)


# ROM: direct game:0x5E80C | Wall-marker sweep and exit conversion boundary; MOB placement remains a callee.
def maze_convert_walls_to_exits(state: GameState) -> int:
    """0x5E80C -- the escape timeout's all-walls-become-exits conversion.

    Verified body (0x5E80C-0x5E866): scan MOB slots 0x20-0x3FF and convert a
    slot when either

      * ``mob_picture == 0x20F6`` -- the movable-wall base picture; or
      * ``mob_picture == 0x8000`` -- the generic solid-wall marker -- and its
        object type is not 0x3F (FORCEFIELDHUB, excluded at 0x5E844),

    by calling ``mob_place_tile(slot, 0x10)``, i.e. replacing the record with
    an unlinked EXIT marker whose picture is 0x8001.  Returns 1 when at least
    one slot was converted, else 0 (§08 known-issues: this routine returns an
    ordinary 1, not -1).
    """
    from ..maze import _place_one, set_cell_descriptor

    converted = 0
    for slot in range(FIRST_PLAYABLE_SLOT, 0x400):
        picture = state.mobs.picture[slot]
        if picture == _WALL_PICTURE:
            if state.mobs.obj_type(slot) == int(MazeObjIds.FORCEFIELDHUB):
                continue          # 0x5E844: forcefields survive the escape
        elif picture != _MOVABLE_WALL_PICTURE:
            continue

        _place_one(state, slot, int(MazeObjIds.EXIT))
        set_cell_descriptor(state, slot, int(MazeObjIds.EXIT))
        converted = 1

        # The ROM releases the VBLANK semaphore every 64 slots (0x5E828) so a
        # full-table scan cannot tear the display.
        if (slot & 0x3F) == 0:
            state.vblank_semaphore = 0
    return converted


# =============================================================================
# Door helper (only call site: main_move_players at 0x4ACFC)
# =============================================================================

# ROM: adapter game:0x47FAC | Compatibility delegation to maze_objects.open_timed_doors, which now owns the actual sweep body.
def open_timed_doors(state: GameState) -> None:
    """0x47FAC -- remove every DOOR_HORIZ/DOOR_VERT and play sound 0x12.

    Called once per level when the door-idle threshold is exceeded (§4.1
    post-loop).  Sole call site at 0x4ACFC, within main_move_players -- which
    is why the entry point lives here even though the sweep itself is
    living-maze work.  The body is WP-11's ``maze_objects.open_timed_doors``:
    the two were byte-for-byte the same routine, and one of them had to go.

    That implementation carries the two details worth keeping: the ROM sweeps
    MOB slots directly rather than walking the depth chain, and it plays
    "Doors Open" **only when it actually removed something** (the flag test at
    0x47FF0 gates the ``pea.l $12`` at 0x47FF4).
    """
    from .maze_objects import open_timed_doors as _open_timed_doors

    _open_timed_doors(state)


# ROM: merged game:0x51E80,game:0x51FAE,game:0x5207C | Door-front initializer includes both immediate vertical/horizontal endpoint scanners inline; main_open_doors remains an ordinary callee.
def door_open_start(state: GameState, door_slot: int, player_index: int) -> None:
    """0x51E80 -- start the two opening fronts for a door a key just unlocked.

    The ROM gives every player its own pair of the eight front channels at
    ``door_endpoint_pos``/``door_endpoint_dir`` (0x904A76/0x904A86), indexed
    ``player * 2`` and ``player * 2 + 1``, seeds both with the door's own cell,
    and points them in opposite directions along the door line: up/down for a
    vertical door (0x51ED4/0x51EE2) and left/right for a horizontal one
    (0x51F20/0x51F30).  It then calls ``main_open_doors`` (0x51F9E) so the
    first cell of each front opens on the same frame.

    Both the front records and their animator belong to WP-11, so this only
    seeds them and hands over; the picture ranges that decide how far a front
    travels stay that module's business.
    """
    from .maze_objects import main_open_doors, pf_isdoor

    if not 0 <= player_index < NUM_PLAYERS:
        return
    channel = player_index * 2
    picture = state.mobs.picture[door_slot]
    obj_type = state.mobs.obj_type(door_slot)
    if picture >= 0x9D7C:
        directions = (0, 2)      # up / down along a vertical door
    elif picture >= 0x9D3C:
        directions = (3, 1)      # left / right along a horizontal door
    else:
        # Class-1 junction picture: the ROM scans both axes, in object-type
        # order, and records at most two immediate branches.
        horizontal = ((-1, 3), (1, 1))
        vertical = ((-0x20, 0), (0x20, 2))
        scans = (
            (vertical, horizontal)
            if obj_type == int(MazeObjIds.DOOR_VERT)
            else (horizontal, vertical)
        )
        found = []
        for scan in scans:
            for offset, direction in scan:
                candidate = (door_slot + offset) & 0x3FF
                if offset in (-1, 1):
                    candidate = (
                        (door_slot & 0x3E0)
                        | ((door_slot + offset) & 0x1F)
                    )
                if pf_isdoor(state, candidate):
                    found.append(direction)
                    if len(found) == 2:
                        break
            if len(found) == 2:
                break
        directions = tuple(found)

    for offset, direction in enumerate(directions):
        state.door_endpoint_pos[channel + offset] = door_slot
        state.door_endpoint_dir[channel + offset] = direction
    main_open_doors(state)       # 0x51F9E


# ROM: part game:0x511AC | Extracted key-spending door arm at 0x51DAE-0x51DE4 plus touched-MOB removal tail; not a door_traverse ray-march entry.
def _door_unlock(state: GameState, door_slot: int, player_index: int) -> None:
    """The shared body of the ROM's key-opens-a-door path (0x51DAE-0x51DE4).

    Resets the escape timer, spends the key, refreshes the inventory, opens the
    cell the player is standing against, starts the two fronts that walk the
    rest of the door line, and plays "Doors Open".

    The shared interaction tail removes the touched MOB at 0x51E64-0x51E6A,
    after the fronts have advanced. Neither removal redraws adjacent doors.
    """
    from .player_lifecycle import (
        player_inv_update as player_inv_update,
    )

    player = state.players[player_index]
    state.escape_timer = 0                          # 0x51DAE: clr.w (a3)
    player.keysnum = (player.keysnum - 1) & 0xFF    # 0x51DB8
    player_inv_update(state, player_index)          # 0x51DC2
    door_open_start(state, door_slot, player_index)  # 0x51DD8
    from .maze_objects import _remove_door_slot

    _remove_door_slot(state, door_slot)
    _sound_play(state, 0x12)                        # 0x51DDE: "Doors Open"
    _tile_taken(state, player_index)


# ROM: direct game:0x511AC | Tile-type pickup/door/transport/exit dispatch boundary, with several arms extracted into helpers; correspondence does not assert complete behavioral fidelity.
def player_tile_interact(state: GameState, tile_mob_slot: int,
                          player_index: int) -> int:
    """0x511AC -- dispatch on tile type and apply effect (§4.6).

    Returns -1 when handled/consumed, 0 when unhandled.
    Sound calls use a fixed sound_play pointer in A2 (see player_runtime_contracts.csv).

    Each branch clears the escape timer (0x9048C6, ``a3`` here) itself; a taken
    tile leaves through ``_take_tile``.
    """
    from .player_lifecycle import (
        player_inv_update as player_inv_update,
    )
    from .player_transport import (
        player_tport as player_tport,
    )
    from .level_transitions import (
        player_exit_sequence as player_exit_sequence,
    )
    from .score import player_add_score_with_mult

    if tile_mob_slot == 0:
        return 0

    player = state.players[player_index]
    obj_type = state.mobs.obj_type(tile_mob_slot)

    # ── Food ──────────────────────────────────────────────────────────────────
    # 0x51ADC-0x51CFE. The picture distinguishes ordinary, adaptive and poison
    # food. The prior two-way test treated level-1 FOOD000 as poison.
    if obj_type in (int(MazeObjIds.FOOD_DESTRUCTABLE),
                    int(MazeObjIds.FOOD_INVULN)):
        picture = state.mobs.picture[tile_mob_slot] & 0x7FFF
        if picture == _POISONED_FOOD_PICTURE:
            _poisoned(state, player_index)              # 0x51C40-0x51CB4
        else:
            health_gain = 100
            if picture == _RANDOM_FOOD_PICTURE:
                adaptive_index = (player.health & 0xFFFF) % 20
                health_gain = _RANDOM_FOOD_HEALTH[adaptive_index]
                from .shot_effects import playfield_showscore

                playfield_showscore(
                    state, tile_mob_slot, _PICKUP_SCORE_POPUP_TYPES[adaptive_index],
                )
            player.health += health_gain
            state.player_dizzy_timer[player_index] = 0  # 0x51CDA
            _dialog(state, player_index, _DIALOG_FOOD)  # 0x51CDE, record 0
        # 0x51CEE (wholesome) and 0x51C0C (poisoned) both bump the same byte
        # right after their dialog call, so eating *any* food counts.
        _secret_trick_progress(state, player_index, _TRICK_FOOD)
        # 0x51D06 is the shared tail; poison joins it at 0x51CBE.
        # 0x51D06-0x51D32: once the player is back at 200 or more the
        # low-health machinery is stood down -- the cadence timer takes its
        # disabled sentinel and the spoken-warning latch is re-armed. This is
        # where §4.3's "reset to 0xFFFF" lives; main_health_countdown itself
        # never writes it.
        if player.health >= _LOW_HEALTH_THRESHOLD:
            player.state_timer = _STATE_TIMER_DISABLED
            state.player_lowhealth_spoken[player_index] = 0
        state.health_dirty[player_index] = 1             # 0x51D3E
        # 0x51D44-0x51D92: a roll above 29 speaks one of the character's food
        # lines instead of the eating sound.
        if state.getrandom(0x20) > 0x1D:
            lines = _FOOD_SPEECH_IDS[player.character & 0x03]
            _sound_play(state, lines[state.getrandom(len(lines))])
        else:
            _sound_play(state, 0x0D)
        state.escape_timer = 0                           # 0x51D96: clr.w (a3)
        # "Non-destructible" means shots cannot destroy it; collect() deletes
        # both food types after a successful pickup.
        _take_tile(state, tile_mob_slot, player_index)
        return -1

    # ── Key ───────────────────────────────────────────────────────────────────
    if obj_type == int(MazeObjIds.KEY):
        if player.keysnum + player.potionsnum >= 12:
            _dialog(state, player_index, _DIALOG_INVENTORY_FULL)
            if any(
                candidate.status == int(PlayerStatus.ALIVE_HERE)
                and candidate.health >= 0
                and candidate.keysnum < 12
                for candidate in state.players
            ):
                return 0
            state.escape_timer = 0
            _take_tile(state, tile_mob_slot, player_index)
            return -1
        # 0x514D4: a key counts against "don't be greedy" (keys or potions).
        _secret_trick_progress(state, player_index, _TRICK_NOGREEDY1)
        state.escape_timer = 0                          # 0x514EA: clr.w (a3)
        _sound_play(state, 0x13)                        # 0x514EC/0x514F2
        # 0x514F4-0x514FE: a key is worth 100, through the same
        # multiplier-aware award the treasure arm uses.
        player_add_score_with_mult(state, player_index, _KEY_SCORE)
        # 0x51504-0x51516: the record's state is a pile size (a dead hero's
        # keys); below 2 it is one key.
        count = state.mobs.state(tile_mob_slot)
        if count >= 2:
            room = 12 - player.keysnum - player.potionsnum      # 0x51530
            if count > room:
                # 0x51558-0x515FA: take what fits, shrink the pile in place,
                # and leave the hero blocked by what remains.
                player.keysnum = (player.keysnum + room) & 0xFF
                state.mobs.set_state(tile_mob_slot, count - room)
                if count - room == 1:                            # 0x51590
                    mobs = state.mobs
                    mobs.picture[tile_mob_slot] = _KEY_PICTURE
                    mobs.hpos[tile_mob_slot] = (
                        mobs.hpos[tile_mob_slot] + 0x200) & 0xFFFF
                    mobs.vpos[tile_mob_slot] = (
                        mobs.vpos[tile_mob_slot] & 0xFFC0) | 0x09
                player_inv_update(state, player_index)          # 0x515E4
                if state.idle_timer > 0:                        # 0x515EA
                    state.idle_timer = 0
                return 0
            player.keysnum = (player.keysnum + count) & 0xFF    # 0x51606
        else:
            player.keysnum = (player.keysnum + 1) & 0xFF        # 0x51528
        player_inv_update(state, player_index)          # 0x51610
        _dialog(state, player_index, _DIALOG_KEYS)      # 0x51620, record 3
        _take_tile(state, tile_mob_slot, player_index)
        return -1

    # ── Potions ───────────────────────────────────────────────────────────────
    # 0x5162E: like food, a potion's *picture* says whether it is poisoned --
    # 0x20FC is the bad one (0x5163A).
    if obj_type in (int(MazeObjIds.POT_DESTRUCTABLE),
                    int(MazeObjIds.POT_INVULN)):
        state.escape_timer = 0                          # 0x5162E: clr.w (a3)
        if state.mobs.picture[tile_mob_slot] == _POISONED_POTION_PICTURE:
            _poisoned(state, player_index)              # 0x51644-0x516C8; no redraw bit
        else:
            # 0x516E0: a good potion cures the dizziness first, even one too many to carry.
            state.player_dizzy_timer[player_index] = 0
            if player.keysnum + player.potionsnum >= 12:
                _dialog(state, player_index, _DIALOG_INVENTORY_FULL)
                if (
                    obj_type != int(MazeObjIds.POT_INVULN)
                    or any(
                        candidate.status == int(PlayerStatus.ALIVE_HERE)
                        and candidate.health >= 0
                        and candidate.keysnum < 12
                        for candidate in state.players
                    )
                ):
                    return 0
                _take_tile(state, tile_mob_slot, player_index)
                return -1
            player.potionsnum = (player.potionsnum + 1) & 0xFF
            _sound_play(state, 0x26)                    # 0x51778
            player_inv_update(state, player_index)      # 0x51786
            _dialog(state, player_index, _DIALOG_SAVE_POTIONS)  # 0x51796, rec 5
            # 0x5179C: the good-potion path only -- a *poisoned* potion is
            # never picked up, so it cannot make the player greedy.
            _secret_trick_progress(state, player_index, _TRICK_NOGREEDY1)
        # Both records resist shots differently, but both disappear on pickup.
        _take_tile(state, tile_mob_slot, player_index)
        return -1

    # ── Treasure ──────────────────────────────────────────────────────────────
    # Each treasure collected is credited to its collector through WP-15's
    # ``treasure_collected`` (the ROM's write site at 0x519F0-0x519F8), which
    # bumps ``player_treascount``.
    #
    # Type 0x2E enters at 0x519C2 and shows no popup. Treasure rooms (mazes
    # 0x68-0x72) branch from 0x51A12 straight to the shared tail at 0x51E36:
    # no multiplier, sound, score, redraw bit or escape-timer clear, because
    # the bonus screen pays for the collected count instead.
    if obj_type == int(MazeObjIds.TREASURE):
        _treasure_collected(state, player_index)
        if state.mazenum_current not in _TREASURE_ROOM_MAZES:
            _treasure_award(state, player_index, 100)
        _take_tile(state, tile_mob_slot, player_index)      # 0x51E6A
        return -1

    # Type 0x30 enters at 0x51998: popup, then the award at 0x51A16. It is not
    # counted as treasure and has no treasure-room branch.
    if obj_type == int(MazeObjIds.TREASURE_BAG):
        from .shot_effects import playfield_showscore

        bonus_score = state.special_bonus_score & 0xFFFF
        playfield_showscore(
            state, tile_mob_slot, bonus_score // 1000 + 1,
        )                                               # 0x519B8
        _treasure_award(state, player_index, bonus_score)
        _take_tile(state, tile_mob_slot, player_index)      # 0x51E6A
        return -1

    # ── Locked treasure (type 0x2F) ───────────────────────────────────────────
    # Not handled here, deliberately: the second dispatch table (0x511CE + type
    # * 2) sends 0x2F to the unhandled tail at 0x51E60, exactly like an
    # out-of-range type.  A chest is opened by *shooting* it -- shots.py's
    # supershot treasure arm (0x4B80E) owns its destruction -- so walking into
    # one with a key in hand must neither spend the key nor pay out.  Falling
    # through to the tail leaves the player blocked by it, which is the
    # behaviour the ROM has.

    # ── Doors ─────────────────────────────────────────────────────────────────
    if obj_type in (int(MazeObjIds.DOOR_HORIZ), int(MazeObjIds.DOOR_VERT)):
        # §4.6: doors (check key count).  0x51DA8: no key means the tile is
        # left unhandled, so the player simply stays blocked.
        if player.keysnum > 0:
            _door_unlock(state, tile_mob_slot, player_index)
            return -1
        return 0

    # ── Transporter ───────────────────────────────────────────────────────────
    if obj_type == int(MazeObjIds.TRANSPORTER):
        if state.player_tport_phase[player_index] >= 0:  # 0x513B8: a shove while mid-transport
            return 0
        # 0x513CE returns player_tport's D0 unchanged: -2 means the teleport
        # happened, 0 means it was aborted for too few clear landing cells, in
        # which case the tile has not been handled. The movement tail at
        # 0x42570 keys on the -2.
        if player_tport(state, player_index, tile_mob_slot):
            return TILE_TELEPORTED
        return 0

    # ── Exit ──────────────────────────────────────────────────────────────────
    if obj_type in (int(MazeObjIds.EXIT), int(MazeObjIds.EXITTO6)):
        # 0x513DA, reached for both 0x10 and 0x11 through the dispatch table at
        # 0x511EC.  Before an exit works, the ROM checks hpos bit 4
        # (0x513E4 ``btst #4,$1(a0,d0.w)``): a set bit means this exit is a
        # *fake*.  Stepping on one shows record 30, removes only its MOB collision
        # record, and satisfies the "don't be fooled" objective -- but does not
        # exit.  The playfield descriptor remains an exit-shaped illusion.
        if state.mobs.hpos[tile_mob_slot] & _FAKE_EXIT_FLAG:
            _dialog(state, player_index, _DIALOG_FAKE_EXIT)   # 0x513F8
            state.mobs.unlink_and_clear(tile_mob_slot)        # 0x51404
            _secret_trick_set(state, player_index, _TRICK_NOFOOLED, 1)
            return -1
        # The tile's obj_type *is* the ROM exit_type (EXIT=0x10, EXITTO6=0x11).
        # The record stays, so the tile counts as unhandled (0x51E60).
        state.escape_timer = 0                          # 0x5142A: clr.w (a3)
        player_exit_sequence(state, player_index, tile_mob_slot, obj_type)
        if state.idle_timer > 0:                        # 0x51442
            state.idle_timer = 0
        return 0

    # ── Stun / trap tiles ─────────────────────────────────────────────────────
    if obj_type == int(MazeObjIds.TILE_STUN):
        _clear_floor_marker(state, tile_mob_slot)
        if player.invuln_timer == 0:
            if state.mazenum_current < 0x73:
                stun_add = (120, 45, 120, 60)[player.character & 3]
                sound_id = (0x32, 0x34, 0x32, 0x33)[player.character & 3]
            else:
                stun_add = 120
                sound_id = 0x32
            _sound_play(state, sound_id)
            player.stundelay += stun_add
            state.death_touch_timer[player_index] = -player.stundelay
            state.player_fighting_dir[player_index] = 0
            player.hurt_cooldown = 0x12
        _dialog(state, player_index, _DIALOG_STUN_FLOOR)
        _tile_contact_progress(state, player_index)
        return -1

    if obj_type in (int(MazeObjIds.TILE_TRAP1),
                    int(MazeObjIds.TILE_TRAP2),
                    int(MazeObjIds.TILE_TRAP3)):
        # 0x5124C: the trigger becomes floor, then every matching trigger and
        # its type-7/8/9 wall group is dropped by maze_place_object_types.
        _clear_floor_marker(state, tile_mob_slot)
        if _drop_trap_walls(state, obj_type):
            _sound_play(state, 0x27)
        _dialog(state, player_index, _DIALOG_TRAP)
        _tile_contact_progress(state, player_index)
        return -1

    # ── Power-up tiles ────────────────────────────────────────────────────────
    # 0x517BA-0x518B0, one arm per type, reached through the tile jump table at
    # 0x5122A.  Every arm pushes its power-up ID, calls
    # ``player_give_item_with_message`` (0x4C72A) to OR
    # ``powerup_bit_masks[id]`` into ``player_powers``, arms whatever countdown
    # that power uses, plays sound 0x26 and clears the escape timer.
    if obj_type in POWERUP_ITEM_ID:
        # 0x4C762: an already-owned bit makes the grant return 0 without
        # re-ORing or repeating the speech, but the arm's own side-effects
        # below still run -- a second invisibility potion re-arms the timer.
        _player_give_item(state, player_index, obj_type)
        initialize_player_temporary_power(state, player_index, obj_type)
        if obj_type == int(MazeObjIds.POWER_INVULN):
            # 0x5189E arms ``invuln_timer`` (0x905F40), the word that blocks
            # damage and makes main_move_players drain health every eighth
            # frame (0x4A838-0x4A85E).  Its expiry clears this power's bit
            # (0x4A880).
            # 0x518B2: this is the "don't use invulnerability" objective's
            # tell.  Unlike every other trick site it *assigns* 1 rather than
            # bumping (0x518C8 ``move.b #$1``), so picking up a second one
            # cannot push the byte past the value the check expects.
            _secret_trick_set(state, player_index, _TRICK_NOUSEINVUL, 1)
        _sound_play(state, 0x26)                     # 0x5187A/0x51834/0x518A8
        state.escape_timer = 0                       # 0x51882: clr.w (a3)
        # 0x51884 joins the shared tail at 0x51626, past the keys arm's redraw:
        # a power-up never redraws the inventory panel itself.
        _take_tile(state, tile_mob_slot, player_index)
        return -1

    # ── Hidden pot ────────────────────────────────────────────────────────────
    # 0x518D2: the arm reads the tile's picture, derives a power-up ID from it
    # and offers that power first (0x518F2 ``player_give_item_with_message``);
    # only when nothing was granted (0x5191E ``tst.w d5``) does it fall through
    # to the inventory-capacity and solo-score branches.
    if obj_type == int(MazeObjIds.HIDDENPOT):
        picture = state.mobs.picture[tile_mob_slot] & 0xFFFF
        item_id = (picture - 0xA728) >> 2
        granted = (
            picture >= 0xA728
            and (picture - 0xA728) % 4 == 0
            and _player_give_item_id(state, player_index, item_id)
        )
        # 0x518FA/0x51908: two *task* codes share this site, either of which
        # bumps the byte (0x51904 ``beq`` falls into the same ``addq.b #1``).
        # These are objective codes from the 0x50-0x5D band, not the 1-17
        # trick numbering, so they are passed as literals.
        _secret_trick_progress(state, player_index, _TASK_HIDDENPOT_A)
        _secret_trick_progress(state, player_index, _TASK_HIDDENPOT_B)
        if not granted:
            if player.keysnum + player.potionsnum < 12:
                player.potionsnum = (player.potionsnum + 1) & 0xFF
                granted = True
            elif state.level_players_active == 1:
                player_add_score_with_mult(state, player_index, 100)
                granted = True
        if not granted:
            return 0
        _sound_play(state, 0x26)
        state.escape_timer = 0                          # 0x5198C: clr.w (a3)
        _take_tile(state, tile_mob_slot, player_index)
        player_inv_update(state, player_index)
        return -1

    return 0  # unhandled tile type


# ROM: helper | Synchronizes Python logical floor descriptors with MOB deletion for consumed markers; not a separate ROM callable.
def _clear_floor_marker(state: GameState, slot: int) -> None:
    from ..maze import clear_cell_descriptor

    state.mobs.unlink_and_clear(slot)                   # 0x5F36C
    clear_cell_descriptor(state, slot)


# ROM: adapter game:0x5E7A6 | Delegates the trap-family replacement boundary to maze.maze_place_object_types.
def _drop_trap_walls(state: GameState, trap_type: int) -> bool:
    """0x5E7A6 -- replace this trap's remaining triggers and wall group."""
    from ..maze import maze_place_object_types

    return maze_place_object_types(state, trap_type)


# ROM: part game:0x511AC | Shared taken-tile tail at 0x51E36-0x51E72: hero proximity, idle timer, then the record's removal.
def _take_tile(state: GameState, slot: int, player_index: int) -> None:
    _tile_taken(state, player_index)
    state.mobs.unlink_and_clear(slot)                       # 0x51E6A


# ROM: part game:0x511AC | Hero proximity and idle-timer half of the taken-tile tail, 0x51E36-0x51E5C.
def _tile_taken(state: GameState, player_index: int) -> None:
    from .shot_damage import dragon_player_proximity

    dragon_player_proximity(state, state.players[player_index].mob_slot)
    if state.idle_timer > 0:                                # 0x51E4E
        state.idle_timer = 0


# ROM: part game:0x511AC | Shared trap/stun return-arm bookkeeping: clear escape/positive idle timers and notify the dragon; the dragon routine is a callee.
def _tile_contact_progress(state: GameState, player_index: int) -> None:
    state.escape_timer = 0
    if state.idle_timer > 0:
        state.idle_timer = 0
    from .shot_damage import dragon_player_proximity

    dragon_player_proximity(state, state.players[player_index].mob_slot)


# ROM: adapter game:0x4C72A | Converts Python object types to the ROM item-index argument and delegates to _player_give_item_id.
def _player_give_item(state: GameState, player_index: int, obj_type: int) -> bool:
    """0x4C72A ``player_give_item_with_message`` -- OR one power bit in.

    Verified body: the power-up ID indexes ``powerup_bit_masks`` (0x59B64,
    ``constants.POWERUP_BIT_MASKS``); if the player already owns that bit the
    routine returns 0 without touching anything (0x4C762), otherwise it ORs the
    mask into ``player_powers`` (0x4C77C) and, for the high-byte pickups, raises
    a one-shot dialog latch. A nonzero ``powerup_speech_ids[id]`` composes the
    gated name / NOW HAS / item sentence, with the reduced-text shortcut.

    Each grant that gets this far also shows the message box (``score.powerup_box_draw``),
    whose timer freezes the gameplay band like any other box. Returns True when
    the bit was newly granted.
    """
    item_id = POWERUP_ITEM_ID.get(obj_type)
    if item_id is None:
        return False
    return _player_give_item_id(state, player_index, item_id)


# ROM: direct game:0x4C72A | Current defining power-grant body: owned-bit guard, power OR, one-shot latch and speech, with the box in score.powerup_box_draw; legacy players.player_give_item_with_message does not exist.
def _player_give_item_id(
    state: GameState, player_index: int, item_id: int,
) -> bool:
    """0x4C72A for a caller that already decoded the 0-11 item ID."""
    if not 0 <= item_id < len(POWERUP_BIT_MASKS):
        return False
    mask = POWERUP_BIT_MASKS[item_id]
    player = state.players[player_index]
    if player.powers & mask:                 # 0x4C760-0x4C766
        return False
    player.powers |= mask                    # 0x4C77C
    if mask & 0xFF00:
        if state.dialog_once_flags & mask:    # 0x4C79C-0x4C7AA
            return True
        state.dialog_once_flags |= mask       # 0x4C7AE-0x4C7B6
    from .score import powerup_box_draw, powerup_box_finish

    powerup_box_draw(state, player_index, item_id)
    speech = _POWERUP_SPEECH_IDS[item_id]
    if speech:
        if not state.game_settings & _GAME_SETTINGS_REDUCE_TEXT:
            index = (player.character & 0x03) + player_index * 4
            _sound_speech_play(state, _SPEECH_CHARNAME_TBL[index])  # 0x4C8AE
            _sound_speech_play(state, 0x8D)                         # 0x4C8F8
        _sound_speech_play(state, speech)                           # 0x4C940
    powerup_box_finish(state)
    return True


# ROM: part game:0x511AC | Shared treasure/bag award at 0x51A16-0x51AD8 and its escape-timer clear at 0x51882.
def _treasure_award(state: GameState, player_index: int, value: int) -> None:
    """0x51A16-0x51AD8 -- multiplier, sound 0x26, score, then 0x51882."""
    from .score import player_add_score_with_mult

    _treasure_bonus_multiplier(state, player_index)
    _sound_play(state, 0x26)                                # 0x51AB0
    player_add_score_with_mult(state, player_index, value)  # 0x51AC4
    state.health_dirty[player_index] = 1                    # 0x51ACE
    state.escape_timer = 0                                  # 0x51882


# ROM: part game:0x511AC | Multiplayer bonus redistribution at 0x51A16-0x51AAE, before the ordinary score-award call.
def _treasure_bonus_multiplier(state: GameState, player_index: int) -> None:
    """0x51A16-0x51AAE -- the treasure arm's bonus-multiplier redistribution.

    ``player_bonusmult`` (0x90490E) is a 16-bit word per player, and a treasure
    moves it around the table rather than simply raising it:

      1. solo play changes nothing -- the bump is skipped outright when
         ``level_players_active`` is 1 (0x51A16);
      2. otherwise the collector gains **2** (0x51A2A, ``addq.w #2``);
      3. the collector is then clamped to **2 x level_players_active**
         (0x51A3E-0x51A60), an unsigned compare that writes the cap back only
         when the value exceeds it -- so the multiplier a player can hoard is
         bounded by how many players are on the level;
      4. every *other* player who is still alive (non-zero health) and above 1
         loses one (0x51A64-0x51AA8), floored at 1 by the ``bls`` test, and has
         its panel redraw bit raised (0x51AA2).

    Called before the score award, because ``player_add_score_with_mult`` at
    0x51AC4 multiplies by the value this leaves behind.
    """
    player = state.players[player_index]
    active = state.level_players_active

    if active != 1:                                        # 0x51A16
        player.bonusmult = (player.bonusmult + 2) & 0xFFFF  # 0x51A2A

    cap = (active * 2) & 0xFFFF                            # 0x51A46
    if player.bonusmult > cap:                             # 0x51A48, unsigned
        player.bonusmult = cap                             # 0x51A60

    for other in range(NUM_PLAYERS):                       # 0x51A64
        if other == player_index:                          # 0x51A66
            continue
        victim = state.players[other]
        if victim.health == 0:                             # 0x51A74
            continue
        if victim.bonusmult <= 1:                          # 0x51A84
            continue
        victim.bonusmult = (victim.bonusmult - 1) & 0xFFFF  # 0x51A96
        state.health_dirty[other] = 1                      # 0x51AA2

# Movable-wall base picture (§18); maze_convert_walls_to_exits recognises it
# alongside the 0x8000 marker (ROM 0x5E832).
_MOVABLE_WALL_PICTURE = 0x20F6
