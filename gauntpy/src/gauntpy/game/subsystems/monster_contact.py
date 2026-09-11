"""Monster/player contact damage, afflictions, tagging, and hurt feedback."""

from __future__ import annotations

from ..constants import MONSTER_TYPES, MazeObjIds, PlayerPower
from ..state import GameState
from .secret_rooms import TRICK_NOUSEINVUL, secret_trick_progress, secret_trick_set
from .score import dialog_first_encounter, player_add_score_with_mult
from .shot_damage import death_damage_accumulate
from .sound import sound_play as _sound_play
from .monster_data import _HPOS_FLAG_MOVING, _MAZEOBJ_HSIZE_TIER_TBL
from .monster_state import _aim_direction, _delta_units, _set_direction

# Contact-hurt feedback, from monster_playerhit (0x49876-0x4988A / 0x4967A).
_SOUND_MONSTER_HIT = 0x1E       # "Monster Hits Player"
_SOUND_GHOST_HIT = 0x1F         # "Ghost Hits Player" (type 18 only)
_SOUND_IT_TAG = 0x35            # "Player Touches IT"
_SOUND_ACID_SLIME = 0x36        # "Acid Puddle Slimes Player"
_HURT_COOLDOWN = 0x12           # hurt_cooldown reload (0x49788)

# player_hurt_speech_timer, ROM 0x49A98. The four longword sound-ID banks at
# 0x57AAE are selected by player_character; 0x57B4C gives their exact lengths.
_CHARACTER_HURT_SOUND_BANKS = (
    (0x83, 0x84, 0x85, 0x86),
    (0xAA, 0xAB, 0xAC, 0xAD, 0xAE, 0xAF, 0xB0, 0xB2, 0xB3, 0xB4),
    (0x6D, 0x6E, 0x70, 0x72, 0x73, 0x74, 0x75, 0x95, 0x96, 0x97),
    (0x78, 0x79, 0x7A, 0x7B, 0x7C, 0x79, 0x7E, 0x7F, 0x80),
)
# hurt_speech_cooldown_base, ROM 0x57B32, indexed by active player count.
_HURT_SPEECH_COOLDOWN_BASE = (0, 8, 12, 14, 20)

_POWER_ARMOR = PlayerPower.ARMOR        # selects the powered half of a table

# monster_contact_damage_table -- transcribed from ROM 0x57A2E (row76.bin
# offset 0x17A2E), 64 words = 16 rows × 4 character columns (Warrior, Valkyrie,
# Wizard, Elf).  Rows 0-7 are the eight unpowered contact classes; rows 8-15 are
# the powered-player half (lower damage).  Valkyrie (col 1) always takes the
# least, Wizard (col 2) the most.  §3.7.
_MONSTER_CONTACT_DAMAGE_TABLE = [
    8, 7, 10, 9,      # class 0
    16, 14, 20, 18,   # class 1
    24, 21, 30, 27,   # class 2
    4, 4, 5, 4,       # class 3
    6, 5, 7, 6,       # class 4
    8, 7, 10, 9,      # class 5
    4, 4, 4, 4,       # class 6
    48, 42, 60, 54,   # class 7
    7, 6, 9, 8,       # class 0 powered
    14, 12, 18, 16,   # class 1 powered
    21, 18, 27, 24,   # class 2 powered
    4, 3, 4, 4,       # class 3 powered
    6, 5, 6, 6,       # class 4 powered
    7, 6, 9, 8,       # class 5 powered
    3, 3, 3, 3,       # class 6 powered
    42, 36, 54, 48,   # class 7 powered
]

# Per-type damage-row offset, from the 10-way jump table at 0x49620.  The row
# is ``(hpos & 0xF) - mazeobj_hsize_tier_tbl[type] + 2 + offset`` (0x495E8) and
# the damage is ``table[row*4 + character (+0x20 when armored)]`` (0x497CE).
# Lobber (0x49A32, the empty epilogue) and IT (the tagging path) are absent:
# neither deals table damage.
_CONTACT_ROW_OFFSET = {
    int(MazeObjIds.MONST_GHOST): 0,       # 0x49634, and explodes on contact
    int(MazeObjIds.MONST_GRUNT): 3,       # 0x4964C
    int(MazeObjIds.MONST_DEMON): 3,       # 0x49654
    int(MazeObjIds.MONST_SORC): 3,        # 0x4965C
    int(MazeObjIds.MONST_AUX_GRUNT): 3,   # 0x4964C (shares the grunt entry)
    int(MazeObjIds.MONST_DEATH): 4,       # 0x4970A
    int(MazeObjIds.MONST_SUPERSORC): 4,   # 0x4970A (shares Death's entry)
    int(MazeObjIds.MONST_ACID): 5,        # 0x4966E
}

#: Score awarded when the Acid puddle is consumed (0x498BA).
_ACID_CONTACT_SCORE = 0x1E
#: Score awarded for touching IT (0x496E4), plus the stun it applies (0x496DE).
_IT_TAG_SCORE = 0x0A
_IT_TAG_STUN = 0x10
#: death_touch_timer reload values (0x49730/0x49746/0x49752).  Negative means
#: "new contact" to WP-6, which negates it into a countdown.
_DEATH_TOUCH_NEW = -0x10        # 0xFFF0
_DEATH_TOUCH_REFRESH = 0x10
_DEATH_TOUCH_WHILE_ACID = 1
#: Death-damage accumulator rows (0x497A6/0x497AA): row 6 col 0 unarmored, row
#: 14 col 0 armored -- 4 and 3.
_DEATH_DAMAGE_ROW = 0x18
_DEATH_DAMAGE_ROW_ARMORED = 0x38

# ``dialog_first_encounter`` masks -- the "you have now met a ..." box, shown
# once per game.  The value is loaded into A4 alongside the damage row by each
# arm of the 0x49620 jump table (0x49644 ghost, 0x4964E grunt and aux grunt,
# 0x49656 demon, 0x4965E sorcerer, 0x49670 acid, 0x4970C Death and the Super
# Sorcerer) and handed to the dialog at 0x4986A; IT passes its own literal at
# 0x496F4.  A lobber never reaches the call.
_FIRST_ENCOUNTER_MASK = {
    int(MazeObjIds.MONST_GHOST): 0x00000100,
    int(MazeObjIds.MONST_GRUNT): 0x00000200,
    int(MazeObjIds.MONST_AUX_GRUNT): 0x00000200,
    int(MazeObjIds.MONST_DEMON): 0x00000400,
    int(MazeObjIds.MONST_SORC): 0x00001000,
    int(MazeObjIds.MONST_ACID): 0x00008000,
    int(MazeObjIds.MONST_DEATH): 0x00020000,
    int(MazeObjIds.MONST_SUPERSORC): 0x00020000,
}
_IT_ENCOUNTER_MASK = 0x10000000

# Secret-room progress (§10.6).  ``secret_trick_id`` (gex ``secret_trick_id``,
# 0x904065) holds the maze's trick outside a secret room and the challenge
# task inside one, and the per-player progress bytes live at 0x904872.  A
# search of the whole ROM for either address finds exactly two sites inside the
# monster code: the IT tag at 0x496AC and the immune contact path at 0x49892 --
# the dispatcher and the movement engine never touch them.
_TRICK_TASK_WHILE_IT = 0x5C     # secret_rooms._CHALLENGE_WHILE_IT; passes on any bump

# =============================================================================
# Player contact (0x495A6)
# =============================================================================

def _contact_damage(p, row: int) -> int:  # noqa: ANN001
    """``monster_contact_damage_table[row*4 + character (+0x20 armored)]``.

    The powered half of the 64-word table is the +0x20 (eight-row) block
    (0x497D4-0x49824).  Every live tier of every family lands inside rows 0-7,
    so a row outside that window means the caller was handed a corrupt tier;
    the ROM would read neighbouring data, we deal nothing.
    """
    if not 0 <= row <= 7:
        return 0
    armored = 0x20 if (p.powers & _POWER_ARMOR) else 0
    return _MONSTER_CONTACT_DAMAGE_TABLE[row * 4 + (p.character & 0x03) + armored]


def monster_playerhit(state: GameState, player_index: int,
                      monster_slot: int) -> None:
    """0x495A6 -- resolve a monster walking into a player (§3.7).

    The damage row scales with the creature's *live* strength tier:
    ``row = (hpos & 0xF) - mazeobj_hsize_tier_tbl[type] + 2 + offset``, where
    the offset comes from the ten-way jump table at 0x49620. A lobber's handler
    is the empty epilogue (0x49A32), and IT tags instead of hurting (0x4967A).
    Ghosts are consumed before applying damage; acid is consumed when its
    splash resolves.
    """
    obj_type = state.mobs.obj_type(monster_slot)
    if obj_type not in MONSTER_TYPES:
        return

    tier = state.mobs.hpos[monster_slot] & 0x0F
    row = tier - _MAZEOBJ_HSIZE_TIER_TBL.get(obj_type, 0) + 2

    if obj_type == int(MazeObjIds.MONST_IT):
        _it_tag(state, player_index, monster_slot)
        return

    offset = _CONTACT_ROW_OFFSET.get(obj_type)
    if offset is None:
        return          # lobber: no contact damage, only its thrown rocks hurt
    row += offset

    if obj_type == int(MazeObjIds.MONST_GHOST):
        # 0x49634: the ghost explodes on contact, pays (row+1)*10, and only
        # then applies its damage -- no attack-state windup for ghosts.
        state.mobs.unlink_and_clear(monster_slot)
        player_add_score_with_mult(state, player_index, (row + 1) * 10)
        _contact_apply(state, player_index, monster_slot, obj_type, row)
        return

    if obj_type in (int(MazeObjIds.MONST_DEATH),
                    int(MazeObjIds.MONST_SUPERSORC)):
        # 0x4970A -- Death and the Super Sorcerer share one handler; both bump
        # the looping death-touch timer before the damage gate.
        _death_touch_update(state, player_index)

    # Attack-state windup (0x498EE): a creature that is not yet in its moving
    # state only *enters* it on this contact and deals nothing this frame.
    if not (state.mobs.hpos[monster_slot] & _HPOS_FLAG_MOVING):
        state.mobs.hpos[monster_slot] |= _HPOS_FLAG_MOVING
        if obj_type == int(MazeObjIds.MONST_ACID):
            _acid_windup(state, player_index, monster_slot, row)
        return

    if (obj_type == int(MazeObjIds.MONST_ACID)
            and (state.mobs.state_link[monster_slot] & 0xE000)):
        return          # 0x49904: the puddle is mid-animation, no damage yet

    _contact_apply(state, player_index, monster_slot, obj_type, row)


def _contact_apply(state: GameState, player_index: int, monster_slot: int,
                   obj_type: int, row: int) -> None:
    """0x4977E-0x498EA -- charge the hit and run its side effects."""
    p = state.players[player_index]
    p.hurt_cooldown = _HURT_COOLDOWN

    if obj_type == int(MazeObjIds.MONST_DEATH):
        # 0x4979E: Death also feeds the per-player Death-damage counter, which
        # dismisses the MOB past 200 (§3.6 / §26).  The amount is read from the
        # same contact table: row 6 column 0, or row 14 when armored -- 4 / 3.
        index = (_DEATH_DAMAGE_ROW_ARMORED if (p.powers & _POWER_ARMOR)
                 else _DEATH_DAMAGE_ROW)
        death_damage_accumulate(state, player_index, monster_slot,
                                _MONSTER_CONTACT_DAMAGE_TABLE[index])

    if p.acid_timer == 0:                       # 0x497EE: acid grants immunity
        damage = _contact_damage(p, row)
        p.health = max(0, p.health - damage)
        p.pending_damage += damage
        state.health_dirty[player_index] = 1    # player_redraw |= 2
        # 0x4986A: the once-per-game "you have met a ..." box, keyed by the
        # family mask the jump table loaded into A4, with the damage as its
        # numeric field.
        mask = _FIRST_ENCOUNTER_MASK.get(obj_type)
        if mask is not None:
            dialog_first_encounter(state, player_index, mask, damage)
        if obj_type == int(MazeObjIds.MONST_GHOST):
            _sound_play(state, _SOUND_GHOST_HIT)            # 0x1F
        elif obj_type != int(MazeObjIds.MONST_DEATH):
            _sound_play(state, _SOUND_MONSTER_HIT)          # 0x1E
    else:
        # 0x49892: the branch taken at 0x497F8 lands past the damage, the
        # dialog and the sound and runs one extra test -- being touched while
        # the invulnerability/affliction timer is up fails "don't use
        # invulnerability", so the level's progress byte is cleared.  The
        # damage path never reaches this (0x49890 jumps over it).
        secret_trick_set(state, player_index, TRICK_NOUSEINVUL, 0)

    if obj_type == int(MazeObjIds.MONST_ACID):
        # 0x498AE: the puddle is used up by the splash and pays 30 points.
        state.mobs.unlink_and_clear(monster_slot)
        player_add_score_with_mult(state, player_index, _ACID_CONTACT_SCORE)

    player_hurt_speech_timer(state, player_index)         # 0x498D0

    # 0x498D6: any contact resets the trap-wall escape timer and wakes the
    # idle timer that opens timed doors.
    state.escape_timer = 0
    if state.idle_timer > 0:
        state.idle_timer = 0


def player_hurt_speech_timer(state: GameState, player_index: int) -> None:
    """0x49A98 -- tick and, on expiry, announce one hurt voice.

    The cooldown is reloaded before the acid-affliction test, so an acid-slowed
    player consumes only the first random draw and remains silent. Ordinary
    expiry then draws once more from the selected character's literal sound
    bank and submits that command through the normal sound path.
    """
    timer = (state.hurt_speech_timer[player_index] - 1) & 0xFFFF
    state.hurt_speech_timer[player_index] = timer
    if not timer & 0x8000:
        return

    active = max(0, min(int(state.level_players_active), 4))
    state.hurt_speech_timer[player_index] = (
        state.getrandom(8) + _HURT_SPEECH_COOLDOWN_BASE[active]
    ) & 0xFFFF

    if state.players[player_index].acid_timer:
        return

    character = int(state.players[player_index].character) & 0x03
    sounds = _CHARACTER_HURT_SOUND_BANKS[character]
    _sound_play(state, sounds[state.getrandom(len(sounds))])


def _acid_windup(state: GameState, player_index: int, monster_slot: int,
                 row: int) -> None:
    """0x49922 -- the frame a puddle latches onto a player.

    In attract mode (``game_mode`` negative) the splash resolves immediately:
    the puddle is removed and its damage charged without the armor bias
    (0x499BC).  In play it stuns for 0x20 frames, turns to face the victim and
    starts its splash animation with sound 0x36 (0x4993E).

    Later acid contact is gated by the live state word's animation bits in
    ``monster_playerhit``. This wind-up routine does not seed those bits.
    """
    p = state.players[player_index]
    if state.game_mode < 0:
        state.mobs.unlink_and_clear(monster_slot)
        if 0 <= row <= 7:
            damage = _MONSTER_CONTACT_DAMAGE_TABLE[row * 4 + (p.character & 0x03)]
            p.health = max(0, p.health - damage)
            state.health_dirty[player_index] = 1
            dialog_first_encounter(
                state, player_index,
                _FIRST_ENCOUNTER_MASK[int(MazeObjIds.MONST_ACID)],
                damage,
            )
        return

    p.stundelay = 0x20
    dx = _delta_units(state.mobs.hpos[p.mob_slot], state.mobs.hpos[monster_slot])
    dv = _delta_units(state.mobs.vpos[p.mob_slot], state.mobs.vpos[monster_slot])
    _set_direction(state, monster_slot, _aim_direction(dx, dv, 0, 4))
    if p.acid_timer == 0:
        _sound_play(state, _SOUND_ACID_SLIME)   # 0x36


def _death_touch_update(state: GameState, player_index: int) -> None:
    """0x49712-0x49752 -- arm/refresh the looping death-touch sound timer."""
    p = state.players[player_index]
    timer = state.death_touch_timer[player_index]
    if p.acid_timer != 0:
        state.death_touch_timer[player_index] = _DEATH_TOUCH_WHILE_ACID
    elif timer == 0:
        state.death_touch_timer[player_index] = _DEATH_TOUCH_NEW   # 0xFFF0
    elif 0 < timer < _DEATH_TOUCH_REFRESH:
        state.death_touch_timer[player_index] = _DEATH_TOUCH_REFRESH


def _it_tag(state: GameState, player_index: int, monster_slot: int) -> None:
    """0x4967A -- touching IT transfers the curse instead of dealing damage.

    The ROM also swaps the on-screen IT name label here (0x4590E clears the old
    holder's, 0x45866 sets the new one); synchronize those two alpha cells here.
    """
    p = state.players[player_index]
    _sound_play(state, _SOUND_IT_TAG)           # 0x35
    # 0x496AC: the "be IT" challenge only needs one tag, and the bump lands
    # before player_it is reassigned, so the *new* holder is credited.
    secret_trick_progress(state, player_index, _TRICK_TASK_WHILE_IT)
    state.player_it = player_index
    from .score import write_it_labels
    write_it_labels(state)
    state.mobs.unlink_and_clear(monster_slot)
    p.stundelay = _IT_TAG_STUN
    player_add_score_with_mult(state, player_index, _IT_TAG_SCORE)
    dialog_first_encounter(state, player_index, _IT_ENCOUNTER_MASK)   # 0x496F4
    state.escape_timer = 0
    if state.idle_timer > 0:
        state.idle_timer = 0
