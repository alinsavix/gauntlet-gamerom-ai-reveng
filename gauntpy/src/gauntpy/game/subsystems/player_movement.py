"""Player movement, private probes, melee, and live MOB record migration."""

from __future__ import annotations

from ..constants import FIRST_PLAYABLE_SLOT, GENERATOR_TYPES, MONSTER_TYPES, GameMode, MazeObjIds, PlayerPower, PlayerStatus
from ..coords import POS_SHIFT, encode_hpos, encode_vpos, encode_vpos_at_y, hpos_x, mob_cell_of, position_field, replace_position, vpos_v
from ..state import GameState
from .sound import sound_play as _sound_play
from .player_data import (
    _FIGHT_PASS_TYPES as _FIGHT_PASS_TYPES,
    _MAZE_ROWS as _MAZE_ROWS,
    _NO_MOVE as _NO_MOVE,
    _PLAYER_OFFSCREEN as _PLAYER_OFFSCREEN,
    _TOP_PLAYER_BOUNDARY_V as _TOP_PLAYER_BOUNDARY_V,
    _VERTICAL_BOUNDARY as _VERTICAL_BOUNDARY,
    _WALL_PICTURE as _WALL_PICTURE,
)

_DIALOG_LOCKED_TREASURE = 0x08000000  # record 27, mob_collision_test 0x52614


# =============================================================================
# WP-5: player movement and collision helpers
# Reference: doc/04_game_subsystems.md §4.2; player_collision_contracts.csv
# =============================================================================

# Direction bit masks mirror input.JOY_* (05_data_reference.md §3.11). Directions live
# in bits 4-7 of the raw word: RIGHT=4, LEFT=5, DOWN=6, UP=7 (bits 2-3 are the
# unconnected JOY_SPARE lines).
_JOY_RIGHT = 0x10   # bit 4
_JOY_LEFT  = 0x20   # bit 5
_JOY_DOWN  = 0x40   # bit 6
_JOY_UP    = 0x80   # bit 7

# player_speed_normal -- transcribed from ROM 0x580A8 (row76.bin offset
# 0x180A8), 8 words indexed by ``character + 4 * extra_speed_power``.  Verified
# by disassembly of main_move_players (0x4A92C-0x4A942): d2 = character, then
# ``btst #0`` of player_powers (POWER_SPEED_BIT) adds 4, then the word is read
# from 0x580A8.  Base: Warrior/Valkyrie/Wizard = 0x80, Elf = 0x100; with the
# extra-speed power all become 0x100.  These are native position words, one
# pixel per 0x80.
_PLAYER_SPEED_NORMAL = [0x80, 0x80, 0x80, 0x100, 0x100, 0x100, 0x100, 0x100]
# player_anim_rate -- ROM 0x580B8 (row76.bin offset 0x180B8), the 8 words
# parallel to player_speed_normal.  main_move_players ANDs the entry with
# ``frame_counter`` at 0x4A950 and adds a +0x80 boost whenever the result is
# non-zero (0x4A95C), so the rate word is a duty-cycle mask, not a divider:
# Warrior/Wizard boost on every odd frame, the Valkyrie on three frames in
# four, the Elf never -- until the extra-speed power swaps the halves, after
# which only the Elf boosts.  This is the sub-pixel smoothing the port used to
# drop, and it is the difference between 2 and 3 px/frame for a Warrior.
_PLAYER_ANIM_RATE = [0x01, 0x03, 0x01, 0x00, 0x00, 0x00, 0x00, 0x01]
_PLAYER_SPEED_BOOST = 0x80
# Mazes 0x73 and above (the treasure/secret rooms) bypass the tables entirely
# and run everyone at 0x100 (0x4A920-0x4A962).
_SPECIAL_MAZE_FIRST = 0x73
_SPECIAL_MAZE_SPEED = 0x100
# POWER_SPEED_BIT (05_data_reference.md §3): player_powers bit 0.
_POWER_SPEED = int(PlayerPower.SPEED)

# joystick_nibble_to_direction -- ROM 0x580FC, indexed by the active-low
# joystick high nibble. Direction order is up, up-right, right, down-right,
# down, down-left, left, up-left; 8 means no valid direction.
_JOYSTICK_NIBBLE_TO_DIRECTION = [
    8, 8, 8, 8, 8, 7, 1, 0, 8, 5, 3, 4, 8, 6, 2, 8,
]

# direction_column_delta / direction_row_delta -- ROM 0x5B64A / 0x5B65C.
_DIRECTION_COLUMN_DELTA = [0, 1, 1, 1, 0, -1, -1, -1, 0]
_DIRECTION_ROW_DELTA = [-0x20, -0x20, 0, 0x20, 0x20, 0x20, 0, -0x20, 0]


# ROM: part game:0x4A53A | Character/power/frame-mask speed selector extracted from main_move_players at 0x4A920-0x4A962.
def _player_speed_units(state: GameState, player) -> int:  # noqa: ANN001
    """The native position units main_move_players loads into D3 (0x4A920-0x4A962).

    ``mazenum_current >= 0x73`` short-circuits to a flat 0x100.  Otherwise the
    per-character ``player_speed_normal`` word is taken (index shifted by 4 when
    the extra-speed power bit is set) and ``player_anim_rate`` decides whether
    this frame also gets the +0x80 boost.
    """
    if state.mazenum_current >= _SPECIAL_MAZE_FIRST:
        return _SPECIAL_MAZE_SPEED
    idx = (player.character & 0x03) + (4 if player.powers & _POWER_SPEED else 0)
    units = _PLAYER_SPEED_NORMAL[idx]
    if state.frame_counter & _PLAYER_ANIM_RATE[idx]:
        units += _PLAYER_SPEED_BOOST
    return units


# ROM: helper | State-free Python convenience exposing only base pixels per frame; omits the ROM frame-dependent boost and special-maze selection.
def _player_speed(player) -> int:  # noqa: ANN001
    """Base pixels/frame for a player, without the animation-rate boost.

    Kept as the frame-independent form of the same table lookup for callers
    with no ``GameState`` to hand; ``player_try_move`` uses
    ``_player_speed_units`` so the 0x580B8 boost is applied.
    """
    idx = (player.character & 0x03) + (4 if player.powers & _POWER_SPEED else 0)
    return _PLAYER_SPEED_NORMAL[idx] >> POS_SHIFT


# ---------------------------------------------------------------------------
# Slot/pixel helpers (§23)
# ---------------------------------------------------------------------------

# ROM: helper | Python sprite-origin/body-cell conversion used by compatibility collision logic; deliberately differs from native record-cell migration.
def _pixel_to_slot(x: int, y: int) -> int:
    """Convert a hero MOB origin to the cell its *body* is probing from (§23).

    A 3x3 hero is centred in a 16-pixel cell by storing its horizontal origin
    four pixels to the left, so the column takes the ROM's HOFFSET+8 (12 px)
    correction and names the cell under the sprite centre. The row is the plain
    one the collision probes want -- the cell the hero's feet are in.

    This is deliberately *not* ``coords.mob_cell_of``: that one is where the
    record lives (it hands the row over half a cell early, so a hero leaning
    into the next row already owns it), and the two disagree for seven pixels
    per row. ``migrate_player_record`` uses the record rule; the directional
    probes use this one.
    """
    row = (y >> 4) & 0x1F
    col = ((x + 12) >> 4) & 0x1F
    return (row << 5) | col


# ROM: helper | Bridges Python active-high directions to the ROM direction-table representation; 0x580FC is a data table, not a routine.
def _direction_from_input(delta: int) -> int:
    """Translate gauntpy's active-high direction bits through ROM 0x580FC."""
    raw_nibble = (~(delta >> 4)) & 0x0F
    return _JOYSTICK_NIBBLE_TO_DIRECTION[raw_nibble]


# ROM: part game:0x4FEB2,game:0x50224,game:0x50662 | Extracted wrapped row/column neighbor arithmetic shared by corner transport, pad selection and landing-direction selection.
def _direction_neighbor(slot: int, direction: int) -> int:
    """Apply the ROM's independently wrapped row/column direction tables."""
    col = (slot + _DIRECTION_COLUMN_DELTA[direction]) & 0x1F
    row = ((slot & 0x3E0) + _DIRECTION_ROW_DELTA[direction]) & 0x3E0
    return row | col


# ROM: part game:0x41C30 | Record-cell calculation from the movement-core tail at 0x424CA-0x424E4, delegated to the shared coordinate representation.
def _player_record_cell(state: GameState, player_index: int) -> int:
    """0x424CA-0x424E4 -- the cell this player's live record belongs in.

    Read straight off the record's own H/V words, so it is the same answer
    ``monster_loop_core`` computes for a creature and it wraps at both maze
    seams for free.
    """
    slot = state.players[player_index].mob_slot
    return mob_cell_of(state.mobs.hpos[slot], state.mobs.vpos[slot])


# ROM: part game:0x41C30 | Movement-core empty-destination migration tail at 0x424E6-0x42524; move_mob_slot is a callee, not this function's implementing entry.
def migrate_player_record(state: GameState, player_index: int) -> bool:
    """0x424E6-0x42524 -- relocate a hero's MOB record into the cell it entered.

    Identity is location: a live player owns the packed slot it stands in, just
    as a monster does, so "moving" means moving the record. ``move_mob_slot``
    (0x5DE0A) links the destination first, copies the five words -- picture,
    H, V, the object type and the state word carrying the player index -- then
    unlinks and clears the source, which is what keeps the depth chain sorted
    and the vacated cell empty.

    Two guards, and both matter:

    * the destination must be empty (``tst.w (a2,d1.w)`` at 0x424EC). An
      occupied cell is the ROM's cue to run ``player_tile_interact`` first; the
      caller does that and comes back here once the tile is gone, so a record
      never overwrites a live object;
    * the managed low slots 0-0x1F are reservations (shots, popups, exit and
      transporter animations) and the top maze row shares them, so a hero can
      neither migrate into one nor out of one -- ``player_exit_sequence`` parks
      ``mob_slot`` on an exit-animation slot on purpose.

    Returns whether the record moved.
    """
    player = state.players[player_index]
    source = player.mob_slot
    if source < FIRST_PLAYABLE_SLOT:
        return False

    destination = mob_cell_of(
        state.mobs.hpos[source], state.mobs.vpos[source],
    )
    if destination == source:                      # 0x424E8: same cell
        return False
    if destination < FIRST_PLAYABLE_SLOT:
        return False
    if state.mobs.picture[destination] != 0:       # 0x424EC: something is there
        return False

    player.mob_slot = destination                  # 0x4250E: active_mob_ids
    state.mobs.move_slot(source, destination)      # 0x42520
    return True


# ROM: part game:0x41C30 | Movement-core occupied-destination tail at 0x424EC-0x42588 (tile interaction, teleport return, rollback or migration), run after the core's position commit.
def resolve_entered_cell(
    state: GameState, player_index: int,
    origin: tuple[int, int, int],
) -> tuple[int | None, bool]:
    """Offer an occupied newly entered cell to ``player_tile_interact``.

    ``origin`` is the record's ``(slot, H, V)`` before the move. An empty
    entered cell needs nothing: ``migrate_player_record`` already moved the
    record. An occupied one is interacted with once per cell change (Python
    gates on last frame's ``player_tile_or_tport_dest``): -2 (a started
    teleport, 0x42570) keeps the pre-move words; a handled tile lets the
    record migrate (0x42588 -> 0x424F2); anything else refuses the step
    (0x42556). Returns ``(rolled-back cell or None, refused)``.
    """
    from .player_items import TILE_TELEPORTED, player_tile_interact

    player = state.players[player_index]
    source, old_h, old_v = origin
    entered = _player_record_cell(state, player_index)
    if (
        entered == player.mob_slot
        or entered == state.player_tile_or_tport_dest[player_index]
    ):
        return None, False
    handled = player_tile_interact(state, entered, player_index)
    if handled != TILE_TELEPORTED and handled and migrate_player_record(
        state, player_index,
    ):
        return None, False
    if player.mob_slot != source:
        return None, False
    state.mobs.hpos[source] = old_h
    state.mobs.vpos[source] = old_v
    return source, handled != TILE_TELEPORTED


# ROM: part game:0x50662 | Extracted transporter relocation at 0x508BA-0x509C8: old-record removal, landing-occupant tricks and resolution, the exit early return, and hero creation.
def _move_player_to_slot(state: GameState, player_index: int, slot: int) -> int:
    """Commit the transporter move milestone, including landing replacement.

    Returns 0 when the destination is refused, 2 when resolving the landing
    occupant started an exit (0x50940-0x50968: the saved picture goes back on
    the slot and the milestone ends), and 1 when the hero has landed.
    """
    from .player_transport import (
        resolve_move_tile_interaction as resolve_move_tile_interaction,
        tport_check_dest as tport_check_dest,
    )

    player = state.players[player_index]
    source = player.mob_slot
    if slot < FIRST_PLAYABLE_SLOT:
        state.player_tile_or_tport_dest[player_index] = source
        return 0

    if slot != source and tport_check_dest(state, slot, player_index):
        state.player_tile_or_tport_dest[player_index] = source
        return 0

    picture = state.mobs.picture[source]
    old_h = state.mobs.hpos[source]
    old_v = state.mobs.vpos[source]
    obj_type = state.mobs.obj_type(source)
    obj_state = state.mobs.state(source)
    x = ((slot & 0x1F) << 4) - 4
    y = (slot >> 5) << 4

    if slot != source:
        # 0x508BA-0x508D0 removes the old hero record and names the landing
        # cell before resolving whatever occupies it.
        state.mobs.unlink_and_clear(source)
        player.mob_slot = slot
        if state.mobs.picture[slot] != 0:                         # 0x508DE
            occupant = state.mobs.obj_type(slot)
            trick = state.secret_trick_id
            if (
                (trick == 1 and occupant == int(MazeObjIds.MONST_ACID))
                or (trick == 2 and occupant == int(MazeObjIds.MONST_DEATH))
                or (trick == 3 and occupant == int(MazeObjIds.EXIT))
            ):
                state.secret_player = player_index               # 0x508FA-0x50922
            if (
                resolve_move_tile_interaction(state, slot, player_index)
                and player.status == int(PlayerStatus.EXITING)
            ):                                                    # 0x50934-0x5094E
                state.mobs.picture[slot] = state.player_tport_saved_picture[
                    player_index
                ]                                                 # 0x50950-0x50962
                return 2
        if state.mobs.obj_type(slot) != int(MazeObjIds.EXIT):    # 0x5097E
            state.mobs.create(
                slot,
                tile=picture,
                hpos=replace_position(old_h, encode_hpos(x)),
                vpos=replace_position(old_v, encode_vpos_at_y(y)),
                obj_type=obj_type,
                state=obj_state,
            )                                                     # 0x509C8
    else:
        state.mobs.hpos[source] = replace_position(old_h, encode_hpos(x))
        state.mobs.vpos[source] = replace_position(
            old_v, encode_vpos_at_y(y),
        )

    state.player_tile_or_tport_dest[player_index] = slot
    _track_thief_victim_move(state, player_index, player.mob_slot)
    return 1


# ROM: adapter game:0x4E630 | Argument-order/import adapter to thief.thief_track_victim_move; route-grid implementation remains there.
def _track_thief_victim_move(state: GameState, player_index: int,
                             packed_slot: int) -> None:
    """Feed player cell changes into the thief's private low-nibble route grid."""
    from .thief import thief_track_victim_move

    thief_track_victim_move(state, packed_slot, player_index)


#: Wall obj_types that block even though they carry a *real* sprite picture
#: (not the 0x8000 marker), so the picture test alone would miss them. Movable
#: walls (base picture 0x20F6) are solid until pushed/destroyed. The solid
#: static walls (WALL_REGULAR/SECRET/DESTRUCTABLE/TRAPCYC*) and a *present*
#: random walls and forcefield hubs carry the 0x8000 marker and are caught by
#: the picture test.
_BLOCKING_OBJ_TYPES = frozenset((
    int(MazeObjIds.DOOR_HORIZ), int(MazeObjIds.DOOR_VERT),
    int(MazeObjIds.WALL_MOVABLE),
))
_MOVABLE_WALL_PICTURE = 0x20F6                        # 0x41C84
_DOOR_REACT_H_LIMIT = 0x5C0                           # 0x522DC
_DOOR_REACT_V_LIMIT = 0x4C0                           # 0x522D8
_HAND_POWER = (2, 2, 1, 1, 3, 3, 2, 2)                # fight.c handpower
_HAND_RANDOM = (0, 0, 0, 2)                           # fight.c rhandpower
_GENERATOR_FIGHT_POWER = (3, 2, 0, 0, 4, 3, 0, 1)    # fight.c generpwr
# The ROM compares the live MOB anchor against the literal hardware windows.
# Do not inset this by the 24px sprite width: its collision response can validly
# place the anchor at offset 208 beside the non-wrapping right edge.
_SCREEN_H_SPAN = 0x7000
_SCREEN_V_SPAN = 0x7400


# ROM: helper | Python coarse picture/type blocking predicate; not the position-aware mob_probe_candidate or tile_lookup_core boundary.
def _slot_is_blocking(state: GameState, slot: int) -> bool:
    """True when slot physically blocks movement (§4.2).

    A solid wall (mob_picture == 0x8000, the marker the static/trap/random walls
    carry) always blocks. Otherwise a slot with a real sprite blocks only if its
    obj_type is one of ``_BLOCKING_OBJ_TYPES`` -- a door (key traversal is
    reached through the ``mob_collision_test`` door arm) or a movable wall. Items,
    monsters, and empty cells are non-blocking for the probe pass.
    """
    pic = state.mobs.picture[slot]
    if pic == _WALL_PICTURE:
        return True    # solid wall marker (§18)
    if pic == 0:
        return False   # empty slot
    return state.mobs.obj_type(slot) in _BLOCKING_OBJ_TYPES


# ROM: adapter game:0x47DAE | Delegated contact-burst boundary to shot_effects.shot_impact_spawn.
def _fight_effect(state: GameState, slot: int, player_index: int) -> None:
    """The contact burst shared by hand-to-hand monster/generator hits."""
    from .shot_effects import shot_impact_spawn

    shot_impact_spawn(state, slot, player_index)


# ROM: direct game:0x52192 | Current defining mob_collision_test combat dispatch body, with Python result conventions; legacy players.mob_collision_test does not exist.
# ROM: part game:0x41C30 | Also contains the movement core's IT transfer/player-contact arm at 0x41DAC-0x41DEC, rather than an ordinary combat callee.
def _player_fight_collision(
    state: GameState, player_index: int, slot: int,
) -> int | None:
    """``mob_collision_test`` (0x52192) for solid living objects.

    Returns -1 when movement proceeds, 0 when blocked, 1 for an active fight,
    or None when the type is outside this dispatch.
    """
    from .player_items import (
        _dialog as _dialog,
        player_tile_interact as player_tile_interact,
    )
    from .player_lifecycle import (
        player_inv_update as player_inv_update,
    )
    from .score import player_add_score_with_mult

    player = state.players[player_index]
    obj_type = state.mobs.obj_type(slot)
    powered = 4 if player.powers & int(PlayerPower.FIGHT) else 0
    power_index = (player.character & 3) + powered

    if obj_type in _FIGHT_PASS_TYPES:
        return -1

    if obj_type in (int(MazeObjIds.DOOR_HORIZ), int(MazeObjIds.DOOR_VERT)):
        # 0x522D8: a door reacts only inside the 0x5C0 x 0x4C0 box on its open
        # sides, using the separations the probe just recorded; elsewhere the
        # hero passes (0x52308 -> 0x52600) and keeps closing on it.
        from .shot_collision import shot_onscreen_check

        if not shot_onscreen_check(
            state, slot, _DOOR_REACT_H_LIMIT, _DOOR_REACT_V_LIMIT,
        ):
            return -1
        return -1 if player_tile_interact(state, slot, player_index) else 0

    if obj_type == int(MazeObjIds.TREASURE_BAG):
        return -1 if player_tile_interact(state, slot, player_index) else 0

    if obj_type == int(MazeObjIds.TREASURE_LOCKED):
        if player.keysnum == 0:
            _dialog(state, player_index, _DIALOG_LOCKED_TREASURE)
            return 0

        player.keysnum = (player.keysnum - 1) & 0xFF
        player_inv_update(state, player_index)
        _sound_play(state, 0x2A)                         # 0x52644
        player.stundelay = 30                            # 0x52654

        from .shot_damage import _MAZEOBJ_BASE_PICTURE_TBL, dragon_player_proximity
        from .shot_effects import tport_cycle_start

        tport_cycle_start(state, slot, player_index)     # start_poof
        roll = state.getrandom(8 + 2 * state.level_players_active)
        if state.game_mode == int(GameMode.DEMO):          # 0x52688
            reward = int(MazeObjIds.TREASURE_BAG)
        elif roll == 1:
            reward = int(MazeObjIds.MONST_DEATH)
        elif roll < 3:
            reward = int(MazeObjIds.KEY)
        elif roll < 7:
            reward = int(MazeObjIds.TREASURE_BAG)
        elif roll in (7, 9):
            reward = int(MazeObjIds.POT_DESTRUCTABLE)
        else:
            reward = int(MazeObjIds.FOOD_DESTRUCTABLE)

        from ..maze import placement_geometry

        hpos, vpos = placement_geometry(reward, slot)
        state.mobs.create(
            slot, _MAZEOBJ_BASE_PICTURE_TBL[reward],
            hpos, vpos, reward, 0,
        )
        dragon_player_proximity(state, slot)
        return 0

    if (obj_type == int(MazeObjIds.PLAYERSTART)
            and slot == state.thief_mob_slot):
        if state.player_fighting_dir[player_index]:
            from .thief import thief_remove_and_drop_loot

            thief_remove_and_drop_loot(state, player_index, slot)
            return -1
        if state.movement_type == 1:
            state.player_fighting_dir[player_index] = player.direction + 1
            player.anim_counter = 0
        return 1

    if obj_type == int(MazeObjIds.PLAYERSTART):
        target_index = next(
            (
                index for index, target in enumerate(state.players)
                if index != player_index and target.active and target.mob_slot == slot
            ),
            None,
        )
        if target_index is None:
            return None
        # 0x41DAC-0x41DEC: only the current IT player can transfer the curse by
        # running into another live player on a non-recursive movement pass. The
        # target is stunned for 0x40 frames.
        if state.movement_type != 0 and state.player_it == player_index:
            state.player_it = target_index
            from .score import write_it_labels

            write_it_labels(state)
            _sound_play(state, 0x35)
            state.players[target_index].stundelay = 0x40
        return 0

    if obj_type in GENERATOR_TYPES:
        fight_power = _GENERATOR_FIGHT_POWER[power_index]
        if not state.player_fighting_dir[player_index]:
            if fight_power > 0 and state.movement_type == 1:
                state.player_fighting_dir[player_index] = (
                    player.direction + 1
                )
                player.anim_counter = 0
                return 1
            return 0

        if fight_power > state.getrandom(4):
            tier = ((obj_type - int(MazeObjIds.GEN_GHOST1)) % 3) + 1
            _fight_effect(state, slot, player_index)
            player_add_score_with_mult(state, player_index, 10)
            if tier == 1:
                state.mobs.unlink_and_clear(slot)
                from ..maze import clear_cell_descriptor

                clear_cell_descriptor(state, slot)
                state.player_fighting_dir[player_index] = 0
                return -1
            else:
                new_type = obj_type - 1
                state.mobs.set_obj_type(slot, new_type)
                from ..maze import placement_picture, set_cell_descriptor

                state.mobs.picture[slot] = placement_picture(
                    state, new_type,
                )
                set_cell_descriptor(state, slot, new_type)
                return 1
        return 0

    if obj_type not in MONSTER_TYPES:
        return None

    if obj_type in (
        int(MazeObjIds.MONST_GHOST),
        int(MazeObjIds.MONST_ACID),
        int(MazeObjIds.MONST_IT),
    ):
        from .monster_contact import monster_playerhit

        monster_playerhit(state, player_index, slot)
        return -1

    if obj_type == int(MazeObjIds.MONST_DEATH):
        return 0

    if obj_type == int(MazeObjIds.MONST_SUPERSORC):
        if state.mobs.hpos[slot] & 0x30 == 0x20:
            return 0
        from .monster_state import _anim_add_high, monster_update_anim_tile
        from .monster_spawning import supersorc_place

        _anim_add_high(state, slot, 0xE0)
        state.mobs.hpos[slot] &= ~0x30
        destination = supersorc_place(state, slot)
        current = destination if destination is not None else slot
        if state.mobs.picture[current]:
            monster_update_anim_tile(
                state, current, int(MazeObjIds.MONST_SUPERSORC),
            )
        return -1 if destination is not None and destination != slot else 0

    if (obj_type == int(MazeObjIds.MONST_SORC)
            and state.mobs.hpos[slot] & 0x10):
        from .monster_state import monster_update_anim_tile

        state.mobs.hpos[slot] &= ~0x10
        monster_update_anim_tile(state, slot, obj_type)
        return 1

    if not state.player_fighting_dir[player_index]:
        if state.movement_type == 1:
            state.player_fighting_dir[player_index] = player.direction + 1
            player.anim_counter = 0
        return 1

    # fight.c indexes rhandpower by cabinet player slot, not character.
    random_bound = _HAND_RANDOM[player_index & 3]
    damage = _HAND_POWER[power_index] + state.getrandom(random_bound)
    low = state.mobs.hpos[slot] & 0x0F
    low = (low - damage) & 0x0F
    state.mobs.hpos[slot] = (state.mobs.hpos[slot] & ~0x0F) | low
    base = {
        int(MazeObjIds.MONST_GRUNT): 4,
        int(MazeObjIds.MONST_AUX_GRUNT): 4,
        int(MazeObjIds.MONST_DEMON): 8,
        int(MazeObjIds.MONST_LOBBER): 11,
        int(MazeObjIds.MONST_SORC): 11,
    }.get(obj_type, 0)
    _fight_effect(state, slot, player_index)
    player_add_score_with_mult(state, player_index, 25)
    if not 0 <= low - base + 2 < 3:
        state.mobs.unlink_and_clear(slot)
        state.player_fighting_dir[player_index] = 0
        return -1
    return 1


# ROM: merged game:0x4280E,game:0x428A4,game:0x4293A,game:0x429D0,game:0x427B4 | Unifies the four one-pixel movable-wall pushes and their shared 0x427B4 cell-migration tail; ray-march entries remain callees.
def _push_movable_wall(
    state: GameState, player_index: int, slot: int, direction: int,
) -> bool:
    """Push a movable wall one pixel toward ``direction`` (a _JOY_* bit).

    True when the push resolved (``clr.w d0``): the wall moved, or it reached
    an exit or transporter and dissolved. False when the ray march found any
    other blocker. 0x427B4 keeps the new position even when the cell it now
    belongs to is occupied; the record only migrates into an empty cell.
    """
    step_x = {_JOY_RIGHT: 1, _JOY_LEFT: -1}.get(direction, 0)
    step_y = {_JOY_DOWN: 1, _JOY_UP: -1}.get(direction, 0)
    ray_probe = (step_y, 0) if step_y else (0, step_x)

    old_h = state.mobs.hpos[slot]
    old_v = state.mobs.vpos[slot]
    new_h = (old_h + (step_x << POS_SHIFT)) & 0xFFFF
    # The V word grows up the screen, so a downward push subtracts.
    new_v = (old_v - (step_y << POS_SHIFT)) & 0xFFFF
    # 0x42820/0x428B6/0x4294C/0x429E2 call the same ray-march family as monster
    # movement, not the player's directional probes.
    from .monster_movement import _ray_march

    blocker = _ray_march(state, slot, ray_probe, new_h, new_v)
    if blocker is not None:
        blocker_type = state.mobs.obj_type(blocker)
        if blocker_type in (
            int(MazeObjIds.EXIT),
            int(MazeObjIds.TRANSPORTER),
        ):
            if (
                blocker_type == int(MazeObjIds.EXIT)
                and state.secret_trick_id == 10
            ):
                state.secret_player = player_index               # 0x42846-0x42A1A
            from .shot_effects import tport_cycle_start

            tport_cycle_start(state, slot, player_index)
            state.mobs.unlink_and_clear(slot)
            return True
        return False

    state.mobs.hpos[slot] = new_h
    state.mobs.vpos[slot] = new_v
    dest = mob_cell_of(new_h, new_v)                             # 0x427B4-0x427CE
    if dest != slot and state.mobs.picture[dest] == 0:
        if state.monster_iter_ptr == slot:                       # 0x427DC
            state.monster_iter_ptr = dest
        state.mobs.move_slot(slot, dest)                         # 0x42802
    return True


# ROM: part game:0x41C30 | The four movement-core movable-wall arms at 0x41C80, 0x41EB8, 0x420C0 and 0x422F4: push along the move, then across it away from the hero.
def _movable_wall_arm(
    state: GameState, player_index: int, wall: int, delta: int,
    vertical: bool,
) -> bool:
    """Try the core's two pushes; False sends the axis to its wall arm.

    The first push follows the move. If that is blocked the wall is pushed
    across the move, away from the hero: for a vertical move by comparing the
    wall's H with the hero record's (right when not left of it), for a
    horizontal one by comparing V (up when not below it).
    """
    if vertical:
        along = _JOY_UP if delta & _JOY_UP else _JOY_DOWN
    else:
        along = _JOY_LEFT if delta & _JOY_LEFT else _JOY_RIGHT
    if _push_movable_wall(state, player_index, wall, along):
        return True
    hero = state.players[player_index].mob_slot
    if vertical:
        ahead = (state.mobs.hpos[wall] - state.mobs.hpos[hero]) & 0x8000 == 0
        across = _JOY_RIGHT if ahead else _JOY_LEFT
    else:
        ahead = (state.mobs.vpos[wall] - state.mobs.vpos[hero]) & 0x8000 == 0
        across = _JOY_UP if ahead else _JOY_DOWN
    return _push_movable_wall(state, player_index, wall, across)


# ROM: part game:0x425D0,game:0x4260C | Shared three-candidate traversal extracted from private up/down probes; their distinct edge gates remain in the named wrappers.
def _player_probe_vertical(
    state: GameState,
    mob_slot: int,
    target_row: int,
    *,
    hpos: int,
    vpos: int,
) -> int:
    """Private probe_up/down triplet used by player_try_move_core."""
    col = mob_slot & 0x1F
    return _first_probe_contact(
        state, mob_slot,
        [((target_row & 0x1F) << 5) | ((col + dc) & 0x1F) for dc in (0, -1, 1)],
        hpos=hpos, vpos=vpos,
    )


# ROM: part game:0x42648 | Private probes' stop-at-first-overlap traversal; Python resolves a deferred pass-through contact here instead of in mob_collision_test.
def _first_probe_contact(
    state: GameState,
    mob_slot: int,
    candidates: list[int],
    *,
    hpos: int,
    vpos: int,
    defer_interactions: bool = True,
) -> int:
    """The first overlapping candidate, or -1.

    ``tile_lookup_core`` ends the probe at the first overlapping record of
    any kind (``bcs``). When that record is one ordinary movement passes
    through, the later candidates are never examined.
    """
    from .mob_probes import (
        _probe_candidate_deferred as _probe_candidate_deferred,
        _probe_candidate_overlaps as _probe_candidate_overlaps,
    )

    for candidate in candidates:
        if not _probe_candidate_overlaps(
            state, mob_slot, candidate, hpos=hpos, vpos=vpos,
            self_slot=mob_slot,
        ):
            continue
        if defer_interactions and _probe_candidate_deferred(
            state, mob_slot, candidate, self_slot=mob_slot,
        ):
            return -1
        return candidate
    return -1


# ROM: merged game:0x426D4,game:0x4270C | Common private left/right three-candidate probe body parameterized by target column.
def _player_probe_horizontal(
    state: GameState,
    mob_slot: int,
    target_col: int,
    *,
    hpos: int,
    vpos: int,
    defer_interactions: bool = True,
) -> int:
    """Private probe_left/right at 0x426D4/0x4270C.

    The target column is tested in the mover's row, then the row above when
    the mover is at row 2 or lower (``cmpi.w #$80``), then the row below unless
    it is the last row (``cmpi.w #$7C0``); each cell blocks only when its
    anchor overlaps the proposed position.
    """
    row = mob_slot >> 5
    rows = [row]
    if row >= 2:
        rows.append(row - 1)
    if row < _MAZE_ROWS - 1:
        rows.append(row + 1)
    return _first_probe_contact(
        state, mob_slot,
        [(candidate_row << 5) | (target_col & 0x1F) for candidate_row in rows],
        hpos=hpos, vpos=vpos, defer_interactions=defer_interactions,
    )


# ROM: direct game:0x425D0 | Private upward movement probe boundary with row-one coordinate gate and an extracted common triplet traversal.
def _player_probe_up(
    state: GameState, mob_slot: int, *, hpos: int, vpos: int,
) -> int:
    """Private probe_up at 0x425D0, including its row-one coordinate gate."""
    if mob_slot >> 5 == 1 and (vpos & 0xFFFF) > _TOP_PLAYER_BOUNDARY_V:
        return 0
    return _player_probe_vertical(
        state, mob_slot, (mob_slot >> 5) - 1, hpos=hpos, vpos=vpos,
    )


# ROM: direct game:0x4260C | Private downward movement probe boundary with signed bottom gate and an extracted common triplet traversal.
def _player_probe_down(
    state: GameState, mob_slot: int, *, hpos: int, vpos: int,
) -> int:
    """Private probe_down at 0x4260C, including its signed bottom gate."""
    if mob_slot >> 5 == _MAZE_ROWS - 1:
        return 0 if vpos & 0x8000 else -1
    return _player_probe_vertical(
        state, mob_slot, (mob_slot >> 5) + 1, hpos=hpos, vpos=vpos,
    )


# ROM: part game:0x41C30 | Movement-core wall arms: blocked-axis even-pixel retry at 0x41CD2/0x41F08/0x42110/0x42346 and the perpendicular nudges that follow.
def _wall_collision_response(
    state: GameState,
    player_index: int,
    result: int,
    cur_slot: int,
    delta: int,
    *,
    hpos: int,
    vpos: int,
    blocked_vertical: bool,
    requested_axis: int,
) -> tuple[int, int, int, int, bool] | None:
    """Port the wall arms in player_try_move_core.

    Returns ``(hpos, vpos, dx, dv, finished)`` for a wall blocker, or None.
    A wall always rounds the blocked axis to the even pixel on the mover's
    side (``andi.w #$FF7F``), so a two-pixel step into a wall still closes an
    odd one-pixel gap. When the cross-axis overlap exceeds 0x540 and the wall
    sits on a diagonal flank the stick is not pressing toward, the core also
    tries a one-pixel nudge away from that flank; once it tries, it skips the
    remaining axis (``finished``) and keeps the nudge only if the probe is
    clear or ``mob_collision_test`` passes the hero.
    """
    from .mob_probes import (
        _probe_candidate_anchor as _probe_candidate_anchor,
        _wrapped_position_delta as _wrapped_position_delta,
    )

    if (
        blocked_vertical
        and result == 0
        and cur_slot >> 5 in (1, _MAZE_ROWS - 1)
    ):
        # The private top/bottom coordinate gates put zero in D1 without
        # probing slot zero. It is not a wall candidate for the response arms.
        return None
    if not 0 <= result < len(state.mobs.picture):
        return None
    if state.mobs.picture[result] not in (_WALL_PICTURE, _MOVABLE_WALL_PICTURE):
        # A movable wall reaches this arm only after both pushes failed.
        return None

    # ROM: helper | Python step-direction summary of a changed position word; the ROM keeps raw registers.
    def sign(new: int, old: int) -> int:
        if position_field(new) == position_field(old):
            return 0
        return 1 if (new - old) & 0x8000 == 0 else -1

    # ROM: part game:0x41C30 | Nudge acceptance: clear probe or mob_collision_test pass at 0x41D22-0x41D2A and siblings.
    def nudge_passes(slot: int) -> bool:
        return slot == -1 or _player_fight_collision(
            state, player_index, slot,
        ) == -1                                   # 0x42598 mob_collision_test

    wall_h, wall_v = _probe_candidate_anchor(state, result)
    if blocked_vertical:
        # 0x42346 (up) / 0x42112 (down)
        new_v = (vpos + 0x80) & 0xFF7F if requested_axis > 0 else vpos & 0xFF7F
        rounded = (hpos, new_v, 0, sign(new_v, vpos), False)
        if _wrapped_position_delta(wall_h, hpos) <= 0x540:
            return rounded
        col_delta = ((result & 0x1F) - (cur_slot & 0x1F)) & 0x1F
        if col_delta == 0x1F and not delta & _JOY_LEFT:
            nudge = 1
        elif col_delta == 1 and not delta & _JOY_RIGHT:
            nudge = -1
        else:
            return rounded
        new_h = replace_position(
            hpos, encode_hpos((hpos_x(hpos) + nudge) & 0x1FF),
        )
        if not _inside_player_screen_window(state, new_h, new_v)[0]:
            return rounded
        if not nudge_passes(_player_probe_horizontal(
            state, cur_slot, (cur_slot & 0x1F) + nudge,
            hpos=new_h, vpos=new_v,
        )):
            return rounded[:4] + (True,)
        return new_h, new_v, nudge, sign(new_v, vpos), True

    # 0x41CD2 (right) / 0x41F08 (left)
    new_h = (hpos + 0x80) & 0xFF7F if requested_axis > 0 else hpos & 0xFF7F
    rounded = (new_h, vpos, sign(new_h, hpos), 0, False)
    if _wrapped_position_delta(wall_v, vpos) <= 0x540:
        return rounded
    row_delta = ((result >> 5) - (cur_slot >> 5)) & 0x1F
    if row_delta == 1 and not delta & _JOY_DOWN:
        nudge_v = 1
    elif row_delta == 0x1F and not delta & _JOY_UP:
        nudge_v = -1
    else:
        return rounded
    new_v = replace_position(
        vpos, encode_vpos((vpos_v(vpos) + nudge_v) & 0x1FF),
    )
    if not _inside_player_screen_window(state, new_h, new_v)[1]:
        return rounded
    probe = _player_probe_up if nudge_v > 0 else _player_probe_down
    if not nudge_passes(probe(state, cur_slot, hpos=new_h, vpos=new_v)):
        return rounded[:4] + (True,)
    return new_h, new_v, sign(new_h, hpos), nudge_v, True


# ROM: helper | Python masking utility for native unsigned position words.
def _u16_pos(value: int) -> int:
    return value & 0xFFFF


# ROM: part game:0x41C30 | Extracted horizontal/vertical offscreen gates, including 0x41C52-0x41C6A and 0x42092-0x420AA.
def _inside_player_screen_window(
    state: GameState, hpos: int, vpos: int,
) -> tuple[bool, bool]:
    """Return the ROM's horizontal and vertical player-offscreen gates."""
    if state.level_flags_4 & _PLAYER_OFFSCREEN:
        return True, True
    h_origin = _u16_pos((state.scroll_x - 8) << POS_SHIFT)
    # ROM ``scroll_vpos_origin`` = ``(0x108 - pf_vscroll_lo) << 7`` (0x904AC4);
    # ``state.scroll_y`` is that register, and the V word is the hardware's.
    v_delta = (vpos - _u16_pos((0x108 - state.scroll_y) << POS_SHIFT)) & 0xFFFF
    return (
        ((hpos - h_origin) & 0xFFFF) < _SCREEN_H_SPAN,
        v_delta < _SCREEN_V_SPAN,
    )


# ---------------------------------------------------------------------------
# player_try_move  (§4.2, 0x41BF0)
# ---------------------------------------------------------------------------

#: The three outcomes a directional probe can resolve to.  ``CLEAR`` covers
#: both "nothing there" and "a door the player just unlocked"; ``SQUEEZED``
#: means the invulnerability corner phase already relocated the player, so
#: ``player_try_move`` must return without applying a delta on top of it.
_PROBE_CLEAR = "clear"
_PROBE_BLOCKED = "blocked"
_PROBE_SQUEEZED = "squeezed"
_PROBE_PUSHED = "pushed"
_PROBE_FIGHTING = "fighting"


# ROM: part game:0x41C30 | Extracts movement-core probe outcome/squeeze/push/combat dispatch into Python named outcomes; does not implement the D1-preserving ABI wrappers.
def _resolve_probe(state: GameState, player_index: int, result: int,
                   cur_slot: int, delta: int, vertical: bool) -> str:
    """Turn one ``mob_probe_*`` return into a movement outcome (§4.2).

    ``vertical`` selects the up/down reading of 0x0400: those two probes use it
    as the top/bottom boundary sentinel, and a wrapping level treats it as
    clear because native position words wrap at one maze. The left/right probes
    never return it, and callers must not read it as a slot.
    """
    from .player_transport import (
        squeeze_through_check as squeeze_through_check,
    )

    if result == -1:
        return _PROBE_CLEAR
    if vertical and result == _VERTICAL_BOUNDARY:
        return _PROBE_CLEAR if state.wrap_v else _PROBE_BLOCKED
    if squeeze_through_check(state, result, cur_slot, player_index, delta):
        return _PROBE_SQUEEZED
    if state.mobs.picture[result] == _MOVABLE_WALL_PICTURE:   # 0x41C84 etc.
        if _movable_wall_arm(state, player_index, result, delta, vertical):
            return _PROBE_PUSHED
        return _PROBE_BLOCKED
    collision = _player_fight_collision(state, player_index, result)
    if collision == -1:
        return _PROBE_CLEAR
    if collision == 0:
        return _PROBE_BLOCKED
    if collision == 1:
        return _PROBE_FIGHTING
    return _PROBE_BLOCKED


#: 0x41BD0, indexed [target character][mover character]: whether a hero
#: pressing back toward the mover can still be shoved by that class.
_SHOVE_PERMITTED = (
    (0, 0, 0, 0),
    (0, 0, 0, 0),
    (2, 2, 0, 1),
    (1, 1, 0, 0),
)
#: Cross-axis overlap at which a shove also slides sideways (0x41E46 etc.).
_SHOVE_SLIDE_OVERLAP = 0x3C0
_OPPOSITE_DIRECTION = {
    _JOY_RIGHT: _JOY_LEFT, _JOY_LEFT: _JOY_RIGHT,
    _JOY_UP: _JOY_DOWN, _JOY_DOWN: _JOY_UP,
}


# ROM: helper | Resolves a probe result to another live hero from Python player identity rather than the ROM palette nibble.
def _player_index_at(
    state: GameState, slot: int, mover_index: int,
) -> int | None:
    """The other hero whose record a blocked probe hit, if any."""
    if not FIRST_PLAYABLE_SLOT <= slot < len(state.mobs.picture):
        return None
    for index, player in enumerate(state.players):
        if index != mover_index and player.active and player.mob_slot == slot:
            return index
    return None


# ROM: part game:0x41C30 | Player-contact shove arms at 0x41DF6-0x41E7A, 0x41FFE-0x42082, 0x42232-0x422B6 and 0x4243E-0x424C2; the preceding IT transfer stays in mob_collision_test.
def _shove_player(
    state: GameState,
    mover_index: int,
    target_index: int,
    target_slot: int,
    push: int,
    *,
    mover_h: int,
    mover_v: int,
    delta: int,
) -> bool:
    """Push another hero one pixel along ``push``; False when refused.

    ``push`` is the mover's blocked direction. A target that is not pressing
    back toward the mover (its raw switch for the opposite direction is
    released), or that is stunned, is always shoved. Otherwise the class
    table decides, and an allowed shove also cancels that opposing direction
    for the target's next movement call. When the heroes overlap by 0x3C0 or
    more on the cross axis, the shove slides away from the mover's side
    unless the mover is pressing that way itself.
    """
    from .mob_probes import _wrapped_position_delta

    if state.movement_type == 0:                          # tst.w 0x904BF2
        return False
    opposite = _OPPOSITE_DIRECTION[push]
    target = state.players[target_index]
    mover = state.players[mover_index]
    if not (state.player_input_raw[target_index] & opposite or target.stundelay):
        if not _SHOVE_PERMITTED[target.character & 3][mover.character & 3]:
            return False
        state.player_deferred_move_flags[target_index] |= opposite

    target_h = state.mobs.hpos[target_slot] & 0xFFFF
    target_v = state.mobs.vpos[target_slot] & 0xFFFF
    shove = push
    if push in (_JOY_RIGHT, _JOY_LEFT):
        if _wrapped_position_delta(target_v, mover_v) >= _SHOVE_SLIDE_OVERLAP:
            if mover_v & 0xFFFF >= target_v:
                if not delta & _JOY_UP:
                    shove |= _JOY_DOWN
            elif not delta & _JOY_DOWN:
                shove |= _JOY_UP
    elif _wrapped_position_delta(target_h, mover_h) >= _SHOVE_SLIDE_OVERLAP:
        if mover_h & 0xFFFF >= target_h:
            if not delta & _JOY_RIGHT:
                shove |= _JOY_LEFT
        elif not delta & _JOY_LEFT:
            shove |= _JOY_RIGHT

    state.movement_type = (state.movement_type - 1) & 0xFFFF   # 0x424B8
    origin = (target_slot, target_h, target_v)
    player_try_move(
        state, target_index, shove, 0, speed_px=1, core_only=True,
        track_thief=False,
    )
    # The shoved hero's own core call ends in the same occupied-cell tail.
    rolled_back, _ = resolve_entered_cell(state, target_index, origin)
    _track_thief_victim_move(
        state, target_index,
        rolled_back if rolled_back is not None
        else _player_record_cell(state, target_index),
    )
    return True


# ROM: merged game:0x41BF0,game:0x41C30 | Combines the public movement wrapper's setup with its internal register-state core; several collision and migration portions remain extracted.
def player_try_move(
    state: GameState,
    player_index: int,
    delta: int,
    movement_flags: int,
    *,
    track_thief: bool = True,
    speed_px: int | None = None,
    core_only: bool = False,
) -> int:
    """0x41BF0 -- collision-checked player movement (§4.2).

    ``delta`` is the active-high direction bitmask from
    ``input.direction_bits`` (JOY_UP | JOY_LEFT etc.).

    Returns the core's active-low result word: 0x00F0 with the bit of each
    axis that stepped (or shoved another hero) cleared. A wall nudge or
    movable-wall push leaves its bit set.

    ``core_only`` enters ``player_try_move_core`` (0x41C30) directly, as the
    shove arms do with a one-pixel ``speed_px``: the wrapper's deferred-flag
    fold and ``movement_type`` decrement are the caller's.
    """
    if not core_only:
        # 0x41C02-0x41C0C: another hero's shove may have cancelled one of
        # this player's directions for this call only.
        delta &= ~state.player_deferred_move_flags[player_index]
        state.player_deferred_move_flags[player_index] = 0
    player = state.players[player_index]
    if player.mob_slot == 0:
        return _NO_MOVE

    # The ROM wrapper decrements movement_type before entering the collision
    # core. main_move_players seeds 2, so the first pass sees 1; recursive retry
    # paths see zero and cannot trigger another squeeze.
    if not core_only:
        state.movement_type = (state.movement_type - 1) & 0xFFFF

    up    = bool(delta & _JOY_UP)
    down  = bool(delta & _JOY_DOWN)
    left  = bool(delta & _JOY_LEFT)
    right = bool(delta & _JOY_RIGHT)

    if not (up or down or left or right):
        return _NO_MOVE
    direction = _direction_from_input(delta)
    if direction < 8 and not core_only:
        player.direction = (direction - 2) & 0x07

    # Current native position words. player_try_move_core keeps the doubled
    # active_mob_ids entry in D2 for every primary probe, adds the complete D6
    # speed word once per requested axis, and rolls that whole word back when
    # the probe blocks (0x41C30-0x424CA).
    hpos = state.mobs.hpos[player.mob_slot]
    vpos = state.mobs.vpos[player.mob_slot]
    x = hpos_x(hpos)
    v = vpos_v(vpos)
    speed = (
        _player_speed_units(state, player) >> POS_SHIFT     # 0x580A8 + 0x580B8
        if speed_px is None else speed_px
    )
    requested_dx = speed * (int(right) - int(left))
    # The V word grows up the screen, so "down" steps the field down.
    requested_dv = speed * (int(up) - int(down))
    dx = 0
    dv = 0
    fight_contact = False
    collision_response = False

    # ROM: helper | Nested Python closure forwarding captured movement context to _resolve_probe; no independent ROM callable.
    def resolve(result: int, *, vertical: bool) -> str:
        return _resolve_probe(
            state, player_index, result, cur_slot, delta, vertical,
        )

    cur_slot = player.mob_slot
    final_h = hpos
    final_v = vpos
    # 0x41C46 pushes the result word 0xF0. An axis clears its active-low bit
    # only when its own probe resolves clear (0x41E7E/0x42086/0x422BA/
    # 0x424C6); a wall nudge or movable-wall push moves the hero without
    # reporting a step, which main_move_players reads as standing still.
    moved_dirs = _NO_MOVE
    if requested_dx:
        proposed_h = replace_position(
            hpos, encode_hpos((x + requested_dx) & 0x1FF),
        )
        h_on_screen, _ = _inside_player_screen_window(
            state, proposed_h, vpos,
        )
        outcome = _PROBE_BLOCKED
        result = -1
        if h_on_screen:
            result = _player_probe_horizontal(
                state,
                cur_slot,
                (cur_slot & 0x1F) + (1 if requested_dx > 0 else -1),
                hpos=proposed_h,
                vpos=vpos,
            )
            outcome = resolve(
                result,
                vertical=False,
            )
        if outcome is _PROBE_SQUEEZED:
            return moved_dirs                           # 0x42560-0x42580
        fight_contact |= outcome is _PROBE_FIGHTING
        if outcome is _PROBE_CLEAR:
            dx = requested_dx
            final_h = proposed_h
            if requested_dx > 0:
                moved_dirs &= ~_JOY_RIGHT                       # 0x41E7E
            elif result == -1 and _player_probe_horizontal(
                state, cur_slot, (cur_slot & 0x1F) - 1,
                hpos=proposed_h, vpos=vpos, defer_interactions=False,
            ) == -1:
                # 0x41F9A: passing an object leftward through
                # mob_collision_test branches past the 0x42086 clear, so only
                # an empty probe reports the left step.
                moved_dirs &= ~_JOY_LEFT                        # 0x42086
        elif outcome is _PROBE_BLOCKED:
            target_index = _player_index_at(state, result, player_index)
            if target_index is not None:
                push = _JOY_RIGHT if requested_dx > 0 else _JOY_LEFT
                if _shove_player(
                    state, player_index, target_index, result, push,
                    mover_h=hpos, mover_v=vpos, delta=delta,
                ):
                    moved_dirs &= ~push                 # 0x41E7E / 0x42086
            else:
                response = _wall_collision_response(
                    state,
                    player_index,
                    result,
                    cur_slot,
                    delta,
                    hpos=hpos,
                    vpos=vpos,
                    blocked_vertical=False,
                    requested_axis=requested_dx,
                )
                if response is not None:
                    final_h, final_v, dx, dv, collision_response = response

    # The ROM applies H before probing V. A diagonal therefore tests the second
    # axis at the already-updated horizontal position. Each primary axis probes
    # its complete proposed word; a wall arm that tried a nudge goes straight
    # to the commit tail and skips this axis.
    if requested_dv and not collision_response:
        proposed_v = replace_position(
            vpos, encode_vpos((v + requested_dv) & 0x1FF),
        )
        _, v_on_screen = _inside_player_screen_window(
            state, final_h, proposed_v,
        )
        outcome = _PROBE_BLOCKED
        result = -1
        if v_on_screen:
            probe = (
                _player_probe_up if requested_dv > 0 else _player_probe_down
            )
            result = probe(
                state, cur_slot, hpos=final_h, vpos=proposed_v,
            )
            outcome = resolve(result, vertical=True)
        if outcome is _PROBE_SQUEEZED:
            return moved_dirs                           # 0x42560-0x42580
        fight_contact |= outcome is _PROBE_FIGHTING
        if outcome is _PROBE_CLEAR:
            dv = requested_dv
            final_v = proposed_v
            moved_dirs &= ~(_JOY_UP if requested_dv > 0 else _JOY_DOWN)
        elif outcome is _PROBE_BLOCKED:
            target_index = _player_index_at(state, result, player_index)
            if target_index is not None:
                push = _JOY_UP if requested_dv > 0 else _JOY_DOWN
                if _shove_player(
                    state, player_index, target_index, result, push,
                    mover_h=final_h, mover_v=vpos, delta=delta,
                ):
                    moved_dirs &= ~push                 # 0x424C6 / 0x422BA
            else:
                response = _wall_collision_response(
                    state,
                    player_index,
                    result,
                    cur_slot,
                    delta,
                    hpos=final_h,
                    vpos=vpos,
                    blocked_vertical=True,
                    requested_axis=requested_dv,
                )
                if response is not None:
                    final_h, final_v, response_dx, dv, _ = response
                    dx += response_dx

    if not fight_contact and not core_only:
        state.player_fighting_dir[player_index] = 0

    if dx == 0 and dv == 0:
        return moved_dirs

    # 0x424F2/0x4258C commit both resolved words to the still-current record,
    # then the common tail computes and performs any cell migration.
    slot = player.mob_slot
    state.mobs.hpos[slot] = final_h
    state.mobs.vpos[slot] = final_v
    destination = mob_cell_of(final_h, final_v)
    migrate_player_record(state, player_index)
    if track_thief:
        _track_thief_victim_move(state, player_index, destination)
    from .shot_damage import dragon_player_proximity

    dragon_player_proximity(state, destination, cur_slot)
    return moved_dirs
