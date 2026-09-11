"""Projectile hit writers for temporary MOBs, audio, and playfield effects."""

from __future__ import annotations

from ..constants import MazeObjIds
from ..coords import mob_words_to_slot, position_field
from ..playfield import pf_replace
from ..state import GameState
from .shot_data import CONSUMED
from .shot_state import _shot_slot, _u16

# ``wall_desc_destructible`` -- ROM 0x5BA5C points at the three stage records
# 0x5D3D0/0x5D3D8/0x5D3E0, each four playfield stamp words. The ROM recovers
# the stage from the stamped first word; the port tracks it in
# destructible_wall_stage and wall_crumble writes the next record to VRAM.
# Byte-identical to gex's ``wall.SHRUB_DESTRUCT_STAMPS``, whose entry 0 is the
# untouched destructible wall.
_WALL_CRUMBLE_DESCS = (
    (0x07A7, 0x07A8, 0x07A9, 0x07AA),
    (0x07AB, 0x07AC, 0x07AD, 0x07AE),
    (0x07AF, 0x07B0, 0x07B1, 0x07B2),
)

# Effect pool (0x0D-0x10) and its two pictures.
_EFFECT_SLOTS = range(0x0D, 0x11)
_TPORT_EFFECT_FIRST = 0x0924
_TPORT_EFFECT_LAST = 0x095A
_PLAYER_IMPACT_PICTURE = 0x0EFC
_MONSTER_IMPACT_PICTURE = 0x1C5C


def _sound(state: GameState, sound_id: int) -> None:
    from .sound import sound_play
    sound_play(state, sound_id)


def _speech(state: GameState, speech_id: int) -> None:
    from .sound import sound_speech_play
    sound_speech_play(state, speech_id)


# =============================================================================
# Effect pool (0x47C0E / 0x47DAE)
# =============================================================================

def _claim_effect_slot(state: GameState, fallback_channel: int,
                       preserve_tport: bool) -> int | None:
    """Claim one of the four shared effect MOBs used by ROM 0x47C0E/0x47DAE."""
    for slot in _EFFECT_SLOTS:
        if state.mobs.picture[slot] == 0:
            return slot

    slot = 0x0D + (fallback_channel & 3)
    picture = state.mobs.picture[slot]
    if preserve_tport and _TPORT_EFFECT_FIRST <= picture <= _TPORT_EFFECT_LAST:
        return None
    state.mobs.unlink_and_clear(slot)
    return slot


def _place_effect(state: GameState, effect_slot: int, source_slot: int,
                  picture: int, vpos_add: int, counter: int, *,
                  hpos_add: int = 0, depth_key: int | None = None) -> None:
    """Install a temporary effect MOB at a tile-aligned source position."""
    state.mobs.picture[effect_slot] = picture
    state.mobs.hpos[effect_slot] = (
        position_field(state.mobs.hpos[source_slot]) + hpos_add + 1
    ) & 0xFFFF
    state.mobs.vpos[effect_slot] = (
        position_field(state.mobs.vpos[source_slot]) + vpos_add
    ) & 0xFFFF
    if depth_key is None:
        depth_key = source_slot
    state.mobs.insert(effect_slot, depth_key=depth_key)
    state.mob_effect_anim_counter[effect_slot - 0x0D] = counter & 0xFF


def _impact_geometry(
    state: GameState, target: int, shooter: int,
) -> tuple[int, int, int]:
    """Return ``(source_slot, hpos_add, depth_key)`` from 0x47E6A-0x47F7E."""
    if target >= 0x400:
        depth_key = target - 0x400
        if depth_key < 0x20:
            depth_key += 0x20
        elif depth_key > 0x400:
            depth_key -= 0x20
        return _shot_slot(shooter), 0, depth_key

    if target & 0x1F or state.level_flags_4 & 0x20:
        hpos_add = 0 if state.mobs.hpos[target] & 0x38 <= 8 else 0x200
        source_slot = target
    else:
        hpos_add = 0
        source_slot = _shot_slot(shooter)

    if target < 0x20:
        hpos = position_field(state.mobs.hpos[source_slot]) + hpos_add + 1
        vpos = position_field(state.mobs.vpos[source_slot]) + 9
        target = mob_words_to_slot(hpos, vpos, x_bias=8)
    return source_slot, hpos_add, target


def shot_impact_spawn(state: GameState, target: int, shooter: int) -> None:
    """0x47DAE -- spawn a sparkle explosion for a MOB or tagged tile hit.

    The first free slot in 0x0D-0x10 wins. With a full pool, the shooter selects
    a fallback channel, but an active transporter dissolve in that channel is
    preserved rather than overwritten. Tagged playfield hits position the effect
    from the live projectile; their normalized cell is only the depth-list key.
    """
    effect_slot = _claim_effect_slot(
        state, shooter, preserve_tport=True,
    )
    if effect_slot is None:
        return
    picture = (
        _PLAYER_IMPACT_PICTURE if shooter < 8 else _MONSTER_IMPACT_PICTURE
    )
    source_slot, hpos_add, depth_key = _impact_geometry(state, target, shooter)
    _place_effect(
        state, effect_slot, source_slot, picture, 9, 0,
        hpos_add=hpos_add, depth_key=depth_key,
    )


def tport_cycle_start(state: GameState, slot: int,
                      animation_channel: int = 0) -> None:
    """0x47C0E -- start a transporter-cycle dissolve effect on ``slot``.

    The ROM always claims a channel, replacing ``animation_channel`` when all
    four are occupied, then seeds the counter with 0xFF so loop 3 of
    ``main_score_update`` begins at frame zero on its next tick.
    """
    effect_slot = _claim_effect_slot(
        state, animation_channel, preserve_tport=False,
    )
    assert effect_slot is not None
    _place_effect(
        state, effect_slot, slot, _TPORT_EFFECT_FIRST, 0x12, 0xFF,
    )


# 0x579F2, the second word of each ``score_popup_tbl`` record: the picture the
# floating score sprite shows.  Entry 0 is the plain "points" burst the shot
# code raises; 1-9 and 10-14 are the score-value and bonus popups.
_SCORE_POPUP_PICTURE_TABLE = (
    0x1C88, 0x1DB4, 0x1DB7, 0x1DBA, 0x1DBD, 0x1DC0, 0x1DC3, 0x1DC6,
    0x1DC9, 0x1DCC, 0x25F6, 0x25F8, 0x25FA, 0x25FC, 0x25FE,
)
_SCORE_POPUP_SLOT = 0x11         # 0x494DC, the first popup MOB slot
_SCORE_POPUP_FRAMES = 0x3C       # 0x494D2


def playfield_showscore(state: GameState, slot: int, popup: int) -> None:
    """``playfield_showscore`` (0x49498) -- float a score sprite over ``slot``.

    Takes the first of the four popup channels whose ``score_display_timer``
    has run out; ``score.main_score_update`` ages the timer and clears the MOB
    again.  The sprite is snapped to the source's cell, lifted one row, then
    nudged by the palette/size bias the ROM picks per popup family.
    """
    mobs = state.mobs
    for channel in range(4):
        if state.score_display_timer[channel]:
            continue
        state.score_display_timer[channel] = _SCORE_POPUP_FRAMES
        popup_slot = _SCORE_POPUP_SLOT + channel
        mobs.picture[popup_slot] = _SCORE_POPUP_PICTURE_TABLE[
            popup % len(_SCORE_POPUP_PICTURE_TABLE)
        ]
        hpos = position_field(mobs.hpos[slot])
        vpos = _u16(position_field(mobs.vpos[slot]) + 0x400)
        if popup < 0x0A:
            hpos += 5           # 0x4954A: palette 5, three tiles wide
            vpos = _u16(vpos + 0x10)
        else:
            hpos += 1           # 0x4956A: palette 1, two tiles wide
            vpos = _u16(vpos + 8)
        mobs.hpos[popup_slot] = _u16(hpos)
        mobs.vpos[popup_slot] = vpos
        mobs.unlink(popup_slot)
        mobs.insert(popup_slot, depth_key=slot)
        return


_playfield_showscore = playfield_showscore


def _potion_blast(state: GameState, shooter_id: int) -> None:
    """Set the shot-triggered potion's playfield flash latch."""
    from .display import ALPHA_PALETTE_INIT

    # resolve_shot_hit 0x4BA6A-0x4BA82 arms the same one-field playfield flash
    # as a drunk potion before storing shooter+4 in potion_player.
    state.playfield_color_latch = ALPHA_PALETTE_INIT[shooter_id * 4 + 7]


def _spawn_maze_object(state: GameState, slot: int, obj_type: int,
                       picture: int) -> None:
    """``mob_create`` (0x5DC58) at the revealed cell (0x4B5FC-0x4B664).

    The ROM rebuilds the H/V words from the master parameter tables inline.
    ``maze.placement_geometry`` is the port's single reviewed copy of exactly
    that arithmetic -- including the fact that 0x5860C carries the packed
    sprite *size*, not a vertical offset -- so reuse it rather than duplicate
    the corrections.  The picture comes from the caller because the secret-wall
    prize randomizes it for a hidden potion, and because this path must not
    gain the extra ``getrandom`` that ``maze.placement_picture`` draws.
    """
    from ..maze import placement_geometry
    hpos, vpos = placement_geometry(obj_type, slot)
    state.mobs.create(slot, picture, hpos, vpos, obj_type, 0)


def wall_crumble(state: GameState, slot: int, damage: int) -> int:
    """0x5303A -- apply shot damage to a destructible wall.

    Returns -1 when the wall is gone and 0 when it only crumbles a step.

    Three ROM branches.  With ``level_flags`` bit 23 (LFLAG2 bit 7) the wall
    vanishes on the first hit (0x53046).  On a shrub level -- ``wallpattern``
    (0x904B5E) >= 6 -- the stage is the tile's own graphic: the ROM matches the
    low 12 bits of the stamped descriptor against ``wall_desc_destructible``
    and destroys the wall outright when nothing matches (0x53084-0x530C6).
    Everywhere else it is a palette crumble (0x530E0-0x53136): the tile starts
    at palette 7 and each hit subtracts ``damage`` from all four quadrant words,
    destroying the wall once the drop would pass the ``(p - 5) & 7`` headroom.
    The port keeps the stage in ``destructible_wall_stage`` and writes each
    surviving step's descriptor or palette to playfield VRAM. The renderer
    consumes the resulting VRAM words, not this bookkeeping dictionary.
    """
    if state.level_flags_2 & 0x80:
        # 0x5305C: this branch clears the four MOB words itself and stamps no
        # replacement tile, so it is not the shared destroy tail.
        state.destructible_wall_stage.pop(slot, None)
        state.mobs.link[slot] = 0
        state.mobs.vpos[slot] = 0
        state.mobs.hpos[slot] = 0
        state.mobs.picture[slot] = 0
        from ..maze import clear_cell_descriptor

        clear_cell_descriptor(state, slot)
        return CONSUMED

    stage = state.destructible_wall_stage.get(slot, 0)
    if _wallpattern(state) >= 6:
        # 0x53096: an unrecognised descriptor reads back as a huge stage, so a
        # tile that was never a destructible shrub crumbles away in one hit.
        if not 0 <= stage < len(_WALL_CRUMBLE_DESCS):
            _wall_destroy(state, slot)
            return CONSUMED
        if stage + damage >= len(_WALL_CRUMBLE_DESCS):
            _wall_destroy(state, slot)
            return CONSUMED
    else:
        # 0x530E8: headroom left in the tile's palette nibble, p = 7 - stage.
        if damage > ((7 - stage) - 5) & 7:
            _wall_destroy(state, slot)
            return CONSUMED

    state.destructible_wall_stage[slot] = stage + damage
    from ..playfield_vram import read_tile_descriptor, write_tile_descriptor

    descriptor = wall_crumble_descriptor(state, slot)
    if descriptor is not None:
        write_tile_descriptor(state, slot, descriptor, 0x7000)
    else:
        palette = wall_crumble_palette(state, slot) & 7
        write_tile_descriptor(
            state,
            slot,
            tuple((word & 0x8FFF) | (palette << 12)
                  for word in read_tile_descriptor(state, slot)),
        )
    return 0


def _wall_destroy(state: GameState, slot: int) -> None:
    """0x530FE -- the crumble ladders' shared "wall is gone" tail."""
    state.destructible_wall_stage.pop(slot, None)
    pf_replace(state, slot, int(MazeObjIds.TILE_FLOOR))


def wall_crumble_descriptor(state: GameState, slot: int) -> tuple[int, ...] | None:
    """The shrub descriptor ``wall_crumble`` writes to playfield VRAM.

    Shrub levels return the four-stamp ``wall_desc_destructible`` record the
    ROM stamps into the playfield; everywhere else the crumble is a palette
    walk and there is no replacement descriptor.  ``None`` also means "not
    damaged", which is the untouched wall.
    """
    stage = state.destructible_wall_stage.get(slot)
    if stage is None or _wallpattern(state) < 6:
        return None
    return _WALL_CRUMBLE_DESCS[min(stage, len(_WALL_CRUMBLE_DESCS) - 1)]


def wall_crumble_palette(state: GameState, slot: int) -> int:
    """The palette nibble ``wall_crumble`` writes to playfield VRAM (0x53120)."""
    return 7 - state.destructible_wall_stage.get(slot, 0)


def _wallpattern(state: GameState) -> int:
    """``wallpattern`` (0x904B5E) -- the level's wall tile set."""
    return int(getattr(state.maze, "wallpattern", 0) or 0)
