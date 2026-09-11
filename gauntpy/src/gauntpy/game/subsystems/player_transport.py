"""Shared transporter IDs, player destinations, transitions, and corner squeeze."""

from __future__ import annotations

from ..constants import FIRST_PLAYABLE_SLOT, SLOT_TPORT_ANIMS, MazeObjIds
from ..coords import POS_SHIFT, native_v, position_field
from ..state import NUM_PLAYERS, GameState
from .sound import sound_play as _sound_play
from .player_data import (
    _PLAYER_OFFSCREEN as _PLAYER_OFFSCREEN,
    _POWER_TRANSPORT as _POWER_TRANSPORT,
    _PROBE_OVERLAP as _PROBE_OVERLAP,
    _SHOT_PALETTE_BASE as _SHOT_PALETTE_BASE,
    _WALL_PICTURE as _WALL_PICTURE,
)

# The transporter arrival sparkle's picture, ROM 0x578F2, installed by
# handle_tport (0x47D3E) on the per-player animation channel.
_TPORT_ARRIVAL_PICTURE = 0x1DCF
_DIALOG_TRANSPORTER = 0x01000000    # record 24, 0x50840
#: 0x50C30/0x50C42 -- the two "try transportability" objectives, decided on the
#: spot when the transporter drops the player beside acid (1) or death (2).
_TRICK_TRANSPORT1 = 1
_TRICK_TRANSPORT2 = 2
#: 0x5027E/0x509E4 -- visit every transporter; progress is a pad bitmask.
_TRICK_VISIT_TPORTS = 0x56


# =============================================================================
# Transporters (§4.6, §7.2) -- player_tport and its three screening leaves
# =============================================================================

def _tport_pos_table(state: GameState) -> list[int]:
    """``tport_pos_table`` (0x910700) / ``level_tport_count`` (0x904B84).

    Level setup fills that word array with every transporter's maze slot; the
    port has no such array, but the slot number *is* the cell address, so an
    ascending scan of the MOB table reproduces the same list in the same order.
    """
    return [
        slot for slot in range(FIRST_PLAYABLE_SLOT, 0x400)
        if state.mobs.obj_type(slot) == int(MazeObjIds.TRANSPORTER)
    ]


def tport_find_id(state: GameState, packed_pos: int) -> int:
    """0x4E7C0 -- return a word position's one-based ID, or count + 1.

    The ROM searches the ordered table at 0x910700; its exhausted index
    still receives the increment at 0x4E7F0. This lookup writes no game RAM.
    """
    pads = _tport_pos_table(state)
    try:
        return pads.index(packed_pos & 0xFFFF) + 1
    except ValueError:
        return len(pads) + 1


def tile_on_screen_test(state: GameState, slot: int) -> bool:
    """0x5E584 ``tile_on_screen_test`` -- is a maze slot inside the viewport?

    The ROM works in the native <<7 position domain against the two hardware
    scroll
    shadows: horizontally ``(col * 16 - pf_hscroll)`` must be within 0..0xD8
    pixels (0x6C00 >> 7), vertically the flipped row origin minus
    ``scroll_vpos_origin`` (0x904AC4 = ``(0x108 - pf_vscroll_lo) << 7``) minus
    8 px must be within 0..0xE0 (0x7000 >> 7).  Both comparisons are unsigned,
    so a tile "behind" the camera fails the same test.  Restated in whole
    pixels here; the vertical form collapses to ``scroll_y <= row * 16 <=
    scroll_y + 224``.  Returns True inside the window (the ROM returns -1).
    """
    col = slot & 0x1F
    row = (slot >> 5) & 0x1F
    dx = (col * 16 - state.scroll_x) & 0x1FF
    if dx > 0xD8:
        return False
    dy = (row * 16 - state.scroll_y) & 0x1FF
    return dy <= 0xE0


def tport_check_dest(state: GameState, destination_slot: int,
                     player_index: int) -> int:
    """0x50ADE -- 1 for a blocked landing cell, 0 for a usable one (§7.2).

    Verified body: blocked when the picture is the solid-wall marker 0x8000
    (0x50B20) or 1 (0x50B28, the reserved marker), when the cell already holds
    another player's sprite (hpos palette nibble >= 0x0C and not this player's
    ``0x0C + player``; 0x50B2E-0x50B42), for wall types 0x3E/0x3C/0x2F
    (0x50B46-0x50B5A), and for doors 0x0D/0x0E when the player holds no key
    (0x50B5E-0x50B76).
    """
    picture = state.mobs.picture[destination_slot]
    obj_type = state.mobs.obj_type(destination_slot)
    palette = state.mobs.hpos[destination_slot] & 0x0F

    if picture == _WALL_PICTURE:
        return 1
    if picture == 1:
        return 1
    if palette >= _SHOT_PALETTE_BASE and palette != _SHOT_PALETTE_BASE + player_index:
        return 1
    if obj_type in (0x3E, 0x3C, 0x2F):
        return 1
    if obj_type in (int(MazeObjIds.DOOR_HORIZ), int(MazeObjIds.DOOR_VERT)):
        if state.players[player_index].keysnum == 0:
            return 1
    return 0


def nearby_mob_clearance_test(state: GameState, slot: int,
                              player_index: int) -> bool:
    """0x50D14 -- True when no *other* player is standing next to ``slot``.

    The ROM walks the eight neighbours of ``slot`` (delta tables 0x578A2 /
    0x578B2) and rejects the cell when a neighbour holds a live MOB whose hpos
    palette nibble is >= 0x0C (a player sprite) other than this player's own,
    and whose position is within 0x7C0 of the cell origin -- 15.5 px in the
    native <<7 domain.

    That neighbour scan is exactly what a migrating hero record makes possible:
    ``active_mob_ids`` names the cell the hero occupies, so the eight cells
    around a landing site are the only ones another hero could be standing in.
    """
    from .mob_probes import (
        _wrapped_position_delta as _wrapped_position_delta,
    )
    from .player_movement import (
        _direction_neighbor as _direction_neighbor,
    )

    ref_h = ((((slot & 0x1F) * 16 - 4) << POS_SHIFT)) & 0xFFFF   # 0x50D2E
    ref_v = (native_v(((slot >> 5) & 0x1F) * 16) << POS_SHIFT) & 0xFFFF  # 0x50D42
    own_palette = _SHOT_PALETTE_BASE + player_index
    for direction in range(8):
        cell = _direction_neighbor(slot, direction)
        if state.mobs.picture[cell] == 0:
            continue
        palette = state.mobs.hpos[cell] & 0x0F
        if palette < _SHOT_PALETTE_BASE or palette == own_palette:
            continue
        if (_wrapped_position_delta(state.mobs.hpos[cell], ref_h) < _PROBE_OVERLAP
                and _wrapped_position_delta(
                    state.mobs.vpos[cell], ref_v) < _PROBE_OVERLAP):
            return False
    return True


def handle_tport(state: GameState, source_slot: int, player_index: int) -> None:
    """0x47CFE -- put the transporter arrival sparkle on the player's channel.

    The ROM claims the *fixed* per-player slot ``player_index + 0x19`` out of
    the five transporter-animation MOBs (§1.2, slots 25-29), clearing whatever
    was there, then copies the source MOB's tile-aligned position with the same
    +1 / +0x12 nudges the rest of the effect placement uses (0x47D66/0x47D8A)
    and installs picture 0x1DCF (0x578F2).

    Kept local because the ROM's fixed per-player allocation is not the shared
    0x0D-0x10 pool used by shot explosions.
    """
    effect_slot = player_index + SLOT_TPORT_ANIMS.start   # 0x47D10: +0x19
    if effect_slot not in SLOT_TPORT_ANIMS:
        return
    if state.mobs.picture[effect_slot] != 0:              # 0x47D1E
        state.mobs.unlink_and_clear(effect_slot)
    state.mobs.picture[effect_slot] = _TPORT_ARRIVAL_PICTURE
    state.mobs.hpos[effect_slot] = (
        position_field(state.mobs.hpos[source_slot]) + 1
    ) & 0xFFFF
    state.mobs.vpos[effect_slot] = (
        position_field(state.mobs.vpos[source_slot]) + 0x12
    ) & 0xFFFF
    state.mobs.insert(effect_slot, depth_key=source_slot)  # 0x47D9E


def player_tport(state: GameState, player_index: int,
                 tile_mob_slot: int) -> int:
    """0x50224 -- a player steps onto a transporter (§4.6, §7.2).

    ROM signature is ``player_tport(uint16 transporter_pos, uint16
    player_index)``; the port keeps its existing Python argument order.
    Returns 0 when the teleport is aborted for too few clear landing cells and
    -2 once the move is performed -- the contract
    ``tport_forcefield_contracts.csv`` records for its consumer at 0x513CE.

    Verified body:

      1. record the source in ``player_tport_route_state[p]`` (0x5023E);
      2. ``player_powers & 0x800`` skips destination discovery entirely and
         lands the player back around this same pad (0x5025A -> 0x503AA);
      3. secret trick 0x56 ORs ``1 << tport_find_id(source)`` into
         ``secret_tricks_flags[p]`` (0x5027E);
      4. scan ``tport_pos_table`` up to ``level_tport_count``, skipping the
         source and anything off screen, and keep the nearest by wrap-aware
         Manhattan distance seeded at 0x80; an exact tie only replaces the
         incumbent while ``tport_cycle_dir`` is negative (0x50374);
      5. with no destination found, the source pad is the destination (0x503AA);
      6. count the clear landing cells among the destination's eight
         neighbours: row 0 and out-of-range are rejected (0x503E8/0x503F0), a
         cell that is already another in-flight teleport's destination is
         rejected (0x503F8-0x5045C), then ``tile_on_screen_test``,
         ``tport_check_dest`` and ``nearby_mob_clearance_test`` must all pass;
      7. the required count is 1 plus every other player already bound for
         this same destination with a non-negative phase (0x504BA-0x504E6);
         fewer clear cells than that aborts with 0 (0x504EC);
      8. otherwise ``handle_tport`` spawns the arrival sparkle, the phase/type
         words are armed, sound 0x28 plays, and the landing cell is stored in
         ``player_tile_or_tport_dest[p]`` (0x904BD8 -- WP-13's
         ``player_tile_or_tport_dest``).

    Port note: the ROM hands the motion to the per-frame transition machine and
    so does this port.  ``player_tport`` is purely the producer -- it picks the
    pad and the landing cell, arms the phase, and returns.  WP-14's
    ``main_score_update`` loop 2 then runs the milestones and this file's
    ``tport_player_move`` performs the relocation at step 0x0B.  The ROM's own
    choice *among* the clear landing cells (0x50578-0x505FA) compares two
    registers, ``a1`` and ``a4``, that the routine never initialises -- a
    genuine ROM defect that cannot be reproduced without modelling leftover
    register state -- so the port takes the first clear cell in the ROM's own
    scan order, preferring the four diagonals its final loop restricts itself
    to.
    """
    from .player_movement import (
        _direction_neighbor as _direction_neighbor,
    )

    if not 0 <= player_index < NUM_PLAYERS:
        return 0
    player = state.players[player_index]
    source = tile_mob_slot

    state.player_tport_route_state[player_index] = source        # 0x5023E

    powers_gate = bool(player.powers & _POWER_TRANSPORT)         # 0x50252
    if not powers_gate and state.secret_trick_id == 0x56:        # 0x5025E
        pads = _tport_pos_table(state)
        if source in pads:
            state.secret_tricks_flags[player_index] |= 1 << (
                pads.index(source) + 1
            )

    destination = 0
    if not powers_gate:
        best = 0x80                                              # 0x502AA
        for candidate in _tport_pos_table(state):
            if candidate == source:                              # 0x502CA
                continue
            if not tile_on_screen_test(state, candidate):       # 0x502D8
                continue
            dcol = abs((candidate & 0x1F) - (source & 0x1F))
            if state.wrap_h and dcol >= 0x10:                    # 0x50302
                dcol = 0x20 - dcol
            drow = abs(((candidate >> 5) & 0x1F) - ((source >> 5) & 0x1F))
            # 0x50332 tests LFLAG4 bit 5 -- the *horizontal* wrap flag -- for
            # the vertical term too.  Mirrored rather than "fixed".
            if state.wrap_h and drow >= 0x10:
                drow = 0x20 - drow
            distance = dcol + drow
            if distance < best or (distance == best and state.tport_cycle_dir < 0):
                best = distance
                destination = candidate

    if destination == 0:                                         # 0x503A4
        destination = source

    clear_cells: list[int] = []
    for direction in range(8):                                   # 0x503B4
        cell = _direction_neighbor(destination, direction)
        if cell < 0x20 or cell >= 0x400:                         # 0x503E8/0x503F0
            continue
        if any(state.player_tport_type[i] == 0
               and state.player_tile_or_tport_dest[i] == cell
               and state.player_tport_phase[i] >= 0
               for i in range(NUM_PLAYERS)):                     # 0x503F8-0x5045C
            continue
        if not tile_on_screen_test(state, cell):                # 0x50466
            continue
        if tport_check_dest(state, cell, player_index) != 0:     # 0x50480
            continue
        if not nearby_mob_clearance_test(state, cell, player_index):  # 0x5049A
            continue
        clear_cells.append(cell)

    required = 1                                                 # 0x504B4
    for i in range(NUM_PLAYERS):
        # The ROM does not exclude the arriving player here; its own type word
        # is still zero at this point, so it never counts itself.
        if (state.player_tport_type[i] == destination
                and state.player_tport_phase[i] >= 0):
            required += 1
    if len(clear_cells) < required:                              # 0x504E8
        return 0

    _sound_play(state, 0x28)                                      # 0x50534

    # 0x50578-0x50606 picks the landing cell; the four diagonals are the only
    # candidates it considers (its index runs 1, 3, 5, 7).
    diagonal_cells = {_direction_neighbor(destination, d) for d in (1, 3, 5, 7)}
    diagonals = [c for c in clear_cells if c in diagonal_cells]
    landing = diagonals[0] if diagonals else clear_cells[0]

    # 0x509E4: the "visit every transporter" objective records *both* ends of
    # the hop -- the source pad was ORed in at 0x5027E, and the pad just
    # arrived at goes in here, gated on the same trick and on the destination
    # actually resolving to a known pad (0x509EC ``tst.w d6``).
    _tport_visit_pad(state, player_index, destination)

    # 0x50A18-0x50A66: before handing over to the transition, the arriving
    # player interacts with all four cells around the destination pad -- this is
    # why a transporter can drop you straight onto a potion, and how the two
    # transportability objectives are won.
    scan_move_path_interactions(state, destination, player_index)

    # 0x504F2-0x5052A / 0x50606: arm the transition and hand over.  The hero
    # does not move on this frame -- loop 2 dissolves it, this file's
    # tport_player_move relocates it at the move milestone, and loop 2 re-forms
    # it at the destination.
    tport_transition_arm(state, player_index, destination, landing)
    return -2                                                     # 0x5060A


def _tport_visit_pad(state: GameState, player_index: int, pad_slot: int) -> None:
    """0x5027E / 0x509E4 -- mark one transporter pad as visited.

    Trick 0x56 wants a player to have stood on every pad on the level, so its
    progress byte is a *bitmask* of pad indices rather than a count.  That is
    neither of WP-15's two hook shapes, so the OR stays here; the guard is the
    same ``secret_trick_id`` compare the API applies.
    """
    if state.secret_trick_id != _TRICK_VISIT_TPORTS:
        return
    pad_id = tport_find_id(state, pad_slot)  # shared calls at 0x50278 / 0x509FE
    if pad_id <= len(_tport_pos_table(state)):
        flags = state.secret_tricks_flags
        flags[player_index] |= 1 << pad_id


def scan_move_path_interactions(state: GameState, dest_slot: int,
                           player_index: int) -> None:
    """0x50BB8 -- interact with the four cells around the destination pad.

    ``player_tport`` calls this four times (0x50A1E/0x50A36/0x50A4E/0x50A66),
    once per neighbour-fetch callback (0x406B6, 0x40732, 0x4083A, 0x408A0).
    Each call finds the mob in that cell and, unless it is rejected, runs it
    through ``player_tile_interact`` (0x50C96) exactly as walking into it
    would.  Three rejects, in ROM order:

      * no mob there at all (0x50BD8, the callback returned negative);
      * ``mob_hpos & 0x0F >= 0x0C`` -- mid-cell, so not really in this one
        (0x50BF2, the same sub-tile gate the movement probes use);
      * picture 0x8001 or 0x8000 (0x50C02/0x50C16) -- the two placeholder
        pictures that mean "nothing drawn here".
    """
    from .player_items import (
        player_tile_interact as player_tile_interact,
    )
    from .player_movement import (
        _direction_neighbor as _direction_neighbor,
    )

    for direction in (0, 2, 4, 6):
        cell = _direction_neighbor(dest_slot, direction)
        if cell < 0x20 or cell >= 0x400:
            continue
        # The ROM's callbacks return a MOB slot and reject a negative one
        # (0x50BD8); in this port a maze cell *is* its MOB slot, so the
        # equivalent "nothing there" test is an empty object type.
        if state.mobs.obj_type(cell) == 0:
            continue
        if (state.mobs.hpos[cell] & 0x0F) >= 0x0C:               # 0x50BF2
            continue
        if state.mobs.picture[cell] in (0x8000, 0x8001):         # 0x50C02/0x50C16
            continue
        _tport_landing_trick(state, player_index, cell)          # 0x50C30
        player_tile_interact(state, cell, player_index)          # 0x50C96


def _tport_landing_trick(state: GameState, player_index: int,
                         slot: int) -> None:
    """0x50C30-0x50C52 -- the two "try transportability" objectives.

    Both are decided on the spot rather than accumulated: being dropped next
    to the right monster writes this player straight into ``secret_player``
    (0x50C52 ``move.b d2,secret_player``), no progress byte involved.  Trick 1
    wants MONST_ACID (0x19) and trick 2 wants MONST_DEATH (0x18) -- the two
    things you could never survive walking into.
    """
    trick = state.secret_trick_id
    obj_type = state.mobs.obj_type(slot)
    if trick == _TRICK_TRANSPORT1 and obj_type == int(MazeObjIds.MONST_ACID):
        state.secret_player = player_index
    elif trick == _TRICK_TRANSPORT2 and obj_type == int(MazeObjIds.MONST_DEATH):
        state.secret_player = player_index


def corner_squeeze_geometry(state: GameState, packed_slot: int,
                            player_index: int, delta: int) -> int:
    """0x4FEB2 -- resolve the player branch of corner-squeeze geometry.

    An empty neighbour is the destination; an occupied but permitted neighbour
    advances once more in the same direction.  The result is handed to the
    transporter transition machinery exactly as the ROM does -- 0x500F0-0x5015C
    write the same phase/type/dest words ``player_tport`` writes -- so the hero
    dissolves, slides through the corner and re-forms over the transition's own
    frames rather than jumping.  Returns -2 on success, 0 when the shape blocks.
    """
    from .player_movement import (
        _direction_from_input as _direction_from_input,
        _direction_neighbor as _direction_neighbor,
    )

    direction = _direction_from_input(delta)
    if direction == 8:
        return 0
    state.player_tport_route_state[player_index] = packed_slot  # 0x4FEDA

    target = _direction_neighbor(packed_slot, direction)
    if target >= FIRST_PLAYABLE_SLOT:
        target_hpos = state.mobs.hpos[target]
        target_type = state.mobs.obj_type(target)
        if (target_hpos & 0x0F) >= 0x0C:
            return 0
        if target_type in {
            int(MazeObjIds.PLAYERSTART),
            int(MazeObjIds.EXIT),
            int(MazeObjIds.EXITTO6),
            int(MazeObjIds.TREASURE_LOCKED),
            int(MazeObjIds.MONST_DRAGON),
            int(MazeObjIds.TRANSPORTER),
        }:
            return 0
        if int(MazeObjIds.MONST_GHOST) <= target_type <= int(MazeObjIds.MONST_IT):
            return 0

    if (target < FIRST_PLAYABLE_SLOT
            or state.mobs.picture[target] != 0):
        target = _direction_neighbor(target, direction)
        if target < FIRST_PLAYABLE_SLOT:
            return 0

    if (
        not state.level_flags_4 & _PLAYER_OFFSCREEN
        and not tile_on_screen_test(state, target)
    ):
        return 0
    if (state.mobs.hpos[target] & 0x0F) > 0x0C:
        return 0
    if state.mobs.obj_type(target) == int(MazeObjIds.TRANSPORTER):
        return 0

    _sound_play(state, 0x28)
    # 0x5015C clears the destination-pad word for a corner squeeze.  The zero is
    # significant at 0x50788: it enables the pf_replace path that can erase a
    # normal wall at the selected landing cell.
    tport_transition_arm(state, player_index, 0, target)
    return -2


def tport_transition_arm(state: GameState, player_index: int,
                         destination_pad: int, landing_cell: int) -> None:
    """Start one player's transporter transition -- the *producer* half.

    Both entries into the transition machinery end here: ``player_tport``
    (0x50510-0x5052A) after it has picked a pad, and ``corner_squeeze_geometry``
    (0x500F0-0x5015C) after it has picked the cell on the far side of a corner.
    Each writes the same three words and arms the same animation MOB:

      * ``player_tport_type[p]`` (0x904BE2) -- the destination pad, or zero for
        corner transport;
      * ``player_tile_or_tport_dest[p]`` (0x904BD8, this port's
        ``player_tile_or_tport_dest``) -- the *cell the hero lands on*, which
        ``tport_player_move`` reads and which ``main_scroll_playfield`` pans the
        camera towards while the hero is in flight;
      * ``player_tport_phase[p]`` (0x904BCE) -- 0, which both starts loop 2's
        milestone counter and, being non-negative, freezes this player's
        gameplay at 0x4A7E8 until the transition retires;

    plus ``handle_tport`` for the per-player animation MOB at slot 25+p, whose
    picture is loop 2's own gate (``main_score_update`` 0x472CA).

    **Nothing moves here.**  The save, the move, the restore and the teardown
    are milestones 5, 0x0B, 0x10 and >0x16 of that counter, one every other
    frame, and WP-14's loop 2 drives all four.
    """
    state.player_tport_type[player_index] = destination_pad      # 0x5051A
    state.player_tile_or_tport_dest[player_index] = landing_cell           # 0x50606
    state.player_tport_phase[player_index] = 0                   # 0x5052A
    handle_tport(state, state.players[player_index].mob_slot, player_index)


def tport_player_move(state: GameState, player_index: int) -> None:
    """0x50662 -- the move milestone of the transition (step 0x0B).

    Loop 2 reaches this step at 0x47324, between the picture save at 0x50616
    and the restore at 0x50B88, so the hero is invisible for exactly the frames
    it is being relocated.  WP-14 owns the counter and the two picture helpers;
    the *position* is this file's, so the milestone is watched here rather than
    called back into.

    The landing cell is the one the producer stored in
    ``player_tile_or_tport_dest`` -- the same word the camera is already
    panning towards.
    """
    from .player_items import (
        _dialog as _dialog,
    )
    from .player_movement import (
        _direction_from_input as _direction_from_input,
        _direction_neighbor as _direction_neighbor,
        _move_player_to_slot as _move_player_to_slot,
    )
    from .player_input import _joystick_direction_bits

    landing = state.player_tile_or_tport_dest[player_index] & 0x3FF
    destination_pad = state.player_tport_type[player_index] & 0x3FF
    corner_transport = (
        destination_pad == 0
        and state.player_tport_route_state[player_index] != 0
    )
    direction = _direction_from_input(
        _joystick_direction_bits(state, player_index),
    )
    if destination_pad and destination_pad != landing and direction < 8:
        # 0x50708 indexes tport_direction_rotation (0x5B71C): requested
        # direction, then alternating left/right offsets until a usable
        # neighbour of the destination pad is found.
        for rotation in (0, 7, 1, 6, 2, 5, 3, 4):
            candidate = _direction_neighbor(
                destination_pad, (direction + rotation) & 7,
            )
            if candidate < FIRST_PLAYABLE_SLOT:
                continue
            if not tile_on_screen_test(state, candidate):
                continue
            if tport_check_dest(state, candidate, player_index):
                continue
            if not nearby_mob_clearance_test(state, candidate, player_index):
                continue
            landing = candidate
            state.player_tile_or_tport_dest[player_index] = candidate
            break
    if (
        corner_transport
        and state.mobs.picture[landing] == _WALL_PICTURE
        and state.mobs.obj_type(landing) != int(MazeObjIds.FORCEFIELDHUB)
    ):
        # 0x5078E-0x507E8: corner transport may land on an ordinary software
        # wall marker. pf_replace turns both the logical tile and descriptor
        # VRAM into floor before the normal destination check and player move.
        from ..playfield import pf_replace

        if (
            state.secret_trick_id == 4
            and state.mobs.obj_type(landing) == int(MazeObjIds.WALL_SECRET)
        ):
            state.secret_player = player_index                   # 0x507B8-0x507D4
        pf_replace(state, landing, int(MazeObjIds.TILE_FLOOR))
    if destination_pad:
        _dialog(state, player_index, _DIALOG_TRANSPORTER)  # 0x50840-0x5084C
    if _move_player_to_slot(state, player_index, landing):
        source_pad = state.player_tport_route_state[player_index] & 0x3FF
        if (
            player_index == state.thief_victim
            and source_pad
            and destination_pad
        ):
            from .thief import tport_route_connect

            tport_route_connect(
                state, source_pad, destination_pad, landing,
            )                                           # 0x5085C-0x5087A
            state.thief_victim_pos = landing           # 0x50880
        # 0x509DE creates the arrival sparkle from the newly installed player
        # record. The earlier 0x5050A effect remains at the source for dissolve.
        handle_tport(state, landing, player_index)


def squeeze_through_check(state: GameState, candidate_slot: int,
                          current_slot: int, player_index: int,
                          delta: int) -> int:
    """0x42744 -- gate and dispatch invulnerable corner squeezing."""
    player = state.players[player_index]
    if not (player.powers & _POWER_TRANSPORT):
        return 0
    if state.movement_type == 0:
        return 0
    if (state.mobs.hpos[candidate_slot] & 0x0F) >= 0x0C:
        return 0

    obj_type = state.mobs.obj_type(candidate_slot)
    if obj_type in {
        int(MazeObjIds.PLAYERSTART),
        int(MazeObjIds.EXIT),
        int(MazeObjIds.EXITTO6),
    }:
        return 0
    if int(MazeObjIds.MONST_GHOST) <= obj_type <= int(MazeObjIds.MONST_IT):
        return 0
    return corner_squeeze_geometry(
        state, current_slot, player_index, delta,
    )
