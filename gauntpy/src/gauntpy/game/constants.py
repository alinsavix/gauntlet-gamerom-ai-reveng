"""Enums and fixed constants.

``MazeObjIds`` mirrors ``gex.constants.MazeObjIds`` value-for-value; gex remains
authoritative for maze decoding, and WP-1 wires the two together. It is
restated here so the simulation core can be imported and tested without the
ROMs present.

Reference: ``doc/04_game_subsystems.md`` §1.2, ``doc/05_data_reference.md``.
"""

from __future__ import annotations

from enum import IntEnum


class MazeObjIds(IntEnum):
    """Maze object types -- ``mob_link`` bits 15-10."""

    TILE_FLOOR = 0
    TILE_STUN = 1
    WALL_REGULAR = 2
    WALL_MOVABLE = 3
    WALL_SECRET = 4
    WALL_DESTRUCTABLE = 5
    WALL_RANDOM = 6
    WALL_TRAPCYC1 = 7
    WALL_TRAPCYC2 = 8
    WALL_TRAPCYC3 = 9
    TILE_TRAP1 = 10
    TILE_TRAP2 = 11
    TILE_TRAP3 = 12
    DOOR_HORIZ = 13
    DOOR_VERT = 14
    PLAYERSTART = 15
    EXIT = 16
    EXITTO6 = 17
    MONST_GHOST = 18
    MONST_GRUNT = 19
    MONST_DEMON = 20
    MONST_LOBBER = 21
    MONST_SORC = 22
    MONST_AUX_GRUNT = 23
    MONST_DEATH = 24
    MONST_ACID = 25
    MONST_SUPERSORC = 26
    MONST_IT = 27
    GEN_GHOST1 = 28
    GEN_GHOST2 = 29
    GEN_GHOST3 = 30
    GEN_GRUNT1 = 31
    GEN_GRUNT2 = 32
    GEN_GRUNT3 = 33
    GEN_DEMON1 = 34
    GEN_DEMON2 = 35
    GEN_DEMON3 = 36
    GEN_LOBBER1 = 37
    GEN_LOBBER2 = 38
    GEN_LOBBER3 = 39
    GEN_SORC1 = 40
    GEN_SORC2 = 41
    GEN_SORC3 = 42
    GEN_AUX_GRUNT1 = 43
    GEN_AUX_GRUNT2 = 44
    GEN_AUX_GRUNT3 = 45
    TREASURE = 46
    TREASURE_LOCKED = 47
    TREASURE_BAG = 48
    FOOD_DESTRUCTABLE = 49
    FOOD_INVULN = 50
    POT_DESTRUCTABLE = 51
    POT_INVULN = 52
    KEY = 53
    POWER_INVIS = 54
    POWER_REPULSE = 55
    POWER_REFLECT = 56
    POWER_TRANSPORT = 57
    POWER_SUPERSHOT = 58
    POWER_INVULN = 59
    MONST_DRAGON = 60
    HIDDENPOT = 61
    TRANSPORTER = 62
    FORCEFIELDHUB = 63


#: Creature types dispatched by the shared monster handler (§3.2).
MONSTER_TYPES = range(MazeObjIds.MONST_GHOST, MazeObjIds.MONST_IT + 1)
#: Generator types (§3.2). ``handle_generate`` owns these.
GENERATOR_TYPES = range(MazeObjIds.GEN_GHOST1, MazeObjIds.GEN_AUX_GRUNT3 + 1)


class GameMode(IntEnum):
    """``game_mode`` (0x904918). See ``doc/03_game_rom_structure.md`` §2.3.

    Non-negative values are gameplay; the four attract-family screens are
    negative. Stored as a signed 16-bit word in the original, and a great deal
    of code branches on the *sign* rather than the value.
    """

    NORMAL = 0          # 0x0000
    TREAS_EXIT = 1   # 0x0001
    SCORES = -1         # 0xFFFF
    TITLE = -2          # 0xFFFE
    DEMO = -3           # 0xFFFD
    LEGEND = -4         # 0xFFFC

    @property
    def is_attract(self) -> bool:
        return self < 0


class PlayerStatus(IntEnum):
    """``player_status`` (0x9049A0), one byte per player. §4.1.

    0x08 carries two meanings that the ROM never has to tell apart because it
    only ever *writes* it from one place: ``player_exit_sequence`` (0x52C66)
    parks a hero in it for the exit animation the status-8 branch of
    ``main_move_players`` (0x4A646-0x4A6E6) runs.  This port also animates a
    dying hero -- the ROM's death path resets the player outright -- so
    ``Player.exit_pending`` says which of the two a status-8 player is in, and
    ``EXITING`` is the name to use at the exit call sites.
    """

    REMOVED = 0x00
    ALIVE_HERE = 0x01
    ALIVE_NEXT = 0x02
    DYING = 0x04
    RESPAWN_WAIT = 0x08
    EXITING = 0x08
    SELECTING = 0x10
    SECRET_NAME_ENTRY = 0x20


class Character(IntEnum):
    """Character class index. Used to index most per-class ROM tables."""

    WARRIOR = 0
    VALKYRIE = 1
    WIZARD = 2
    ELF = 3


class PlayerPower(IntEnum):
    """``player_powers`` (0x9048E0) bit masks -- **ROM authoritative**.

    Transcribed from ``powerup_bit_masks`` (0x59B64), the 12-word table
    ``player_give_item_with_message`` (0x4C72A) indexes by power-up ID and ORs
    straight into ``player_powers`` at 0x4C77C.  Verified end to end: the tile
    jump table at 0x5122A routes each ``MazeObjIds`` power-up type to the arm
    that pushes its ID, and three independent ``bclr`` sites confirm the bit
    numbers from the other side (0x4A80E clears bit 8 when ``invis_timer``
    expires, 0x4A826 bit 9 with ``reflect_timer``, 0x4A880 bit 13 with the
    0x905F40 countdown -- each a ``bclr`` on the *high byte* of the word).

    **Corrected twice.** The six pickup powers are bits 8-13, not bits 0-5 and
    not bits 6-11; ``05_data_reference.md`` §3's "Character Powers enum" lists
    REFLECT/TRANSPORT/SUPERSHOT/INVULN at 8/9/10/11, which is this table shifted
    down by two, and INVISIBILITY at 6 rather than 8.  The six *stat* powers in
    the low byte are unaffected and match that enum.

    The pickup names follow the ``MazeObjIds`` type each bit is granted by,
    because the type -> bit mapping is what the ROM fixes.  Two of the labels
    were checked against what their bits actually *do*:

      * bit 9 (type 0x37) really is **Repulsiveness** -- ``btst #1`` on the high
        byte at 0x4185C is the test that makes a monster flee, and ``btst #0``
        at 0x4176C (bit 8) is the one that hides an invisible player from
        targeting.  Reflection is a different bit: shot reflection reads bit 10
        at 0x4B4B0, which is type 0x38.  What is mislabelled is
        ``05_data_reference.md``'s name for **0x905F38** (``reflect_timer``) --
        that countdown's expiry clears bit 9 (0x4A826), so it is the
        *repulsiveness* timer, and ``character_repulse_timer_init`` (0x5B72C)
        is the repulsiveness duration table.
      * bit 13 (type 0x3B) is not invulnerability -- see ``ACID_AFFLICTION``.
    """

    # Stat powers -- low byte.  Bit numbers are 05_data_reference.md §3's
    # "Character Powers enum", which is right for this half and confirmed at two
    # points: ``btst #0`` of the low byte selects the fast half of
    # player_speed_normal (0x4A932) and ``btst #1`` the armoured half of
    # forcefield_damage_table (0x4AA82).  The table's IDs 0-5 map onto them in
    # its own order: ARMOR, SPEED, MAGIC, SHOTPOWER, SHOTSPEED, FIGHT.
    SPEED = 0x0001        # ID 1
    ARMOR = 0x0002        # ID 0
    FIGHT = 0x0004        # ID 5
    SHOTSPEED = 0x0008    # ID 4
    SHOTPOWER = 0x0010    # ID 3
    MAGIC = 0x0020        # ID 2

    # Pickup powers -- high byte, one per MazeObjIds power-up tile.
    INVIS = 0x0100        # ID 6,  MazeObjIds.POWER_INVIS (0x36)
    REPULSE = 0x0200      # ID 7,  MazeObjIds.POWER_REPULSE (0x37)
    REFLECT = 0x0400      # ID 8,  MazeObjIds.POWER_REFLECT (0x38)
    TRANSPORT = 0x0800    # ID 9,  MazeObjIds.POWER_TRANSPORT (0x39)
    SUPERSHOT = 0x1000    # ID 10, MazeObjIds.POWER_SUPERSHOT (0x3A)
    # ID 11, MazeObjIds.POWER_INVULN (0x3B).  **gex's label misstates this
    # one.** The tile is not protective: its arm loads the 0x905F40 countdown
    # with 900 frames (0x5189E), and while that runs main_move_players takes
    # one health every eighth frame -- two when frame-counter bit 3 is clear
    # (0x4A838-0x4A85E) -- roughly 170 health over fifteen seconds.  The same
    # word is what an acid puddle arms (0x512D0), and no other site in the ROM
    # reads this bit; its only other appearance is the ``bclr #5`` that clears
    # it when the countdown ends (0x4A880).  So the bit marks "the damage-
    # over-time is running", which is what the name says.  ``MazeObjIds`` keeps
    # gex's spelling because this port mirrors that enum value-for-value.
    ACID_AFFLICTION = 0x2000
    INVULN = 0x2000       # alias, kept so gex-facing call sites still resolve


#: ``powerup_bit_masks`` (0x59B64) verbatim, indexed by power-up ID 0-11.
POWERUP_BIT_MASKS: tuple[int, ...] = (
    0x0002, 0x0001, 0x0020, 0x0010, 0x0008, 0x0004,
    0x0100, 0x0200, 0x0400, 0x0800, 0x1000, 0x2000,
)

#: Power-up tile type -> its ID in ``POWERUP_BIT_MASKS``, read off the tile
#: jump table at 0x5122A (each entry lands on the arm that pushes the ID).
POWERUP_ITEM_ID: dict[int, int] = {
    int(MazeObjIds.POWER_INVIS): 6,
    int(MazeObjIds.POWER_REPULSE): 7,
    int(MazeObjIds.POWER_REFLECT): 8,
    int(MazeObjIds.POWER_TRANSPORT): 9,
    int(MazeObjIds.POWER_SUPERSHOT): 10,
    int(MazeObjIds.POWER_INVULN): 11,
}


# --- MOB slot allocation (§1.2) -------------------------------------------------

NUM_MOB_SLOTS = 1024
NULL_SLOT = 0

#: Fixed slots 0-29 -- standing reservations, never allocated.
SLOT_PLAYER_SHOTS = range(1, 5)
SLOT_DEMON_SHOTS = range(5, 9)
SLOT_LOBBER_SHOTS = range(9, 13)
SLOT_SHOT_EXPLOSIONS = range(13, 17)
SLOT_SCORE_POPUPS = range(17, 21)
SLOT_EXIT_ANIMS = range(21, 25)
SLOT_TPORT_ANIMS = range(25, 30)

#: Dynamic slots: a maze object's slot number *is* its packed cell address.
FIRST_DYNAMIC_SLOT = 30

#: Row 0 (slots 0-31) overlaps the reserved block, so ``maze_setupnew`` fills
#: it with solid-wall markers immediately after decode (SOL-02, resolved).
FIRST_PLAYABLE_SLOT = 0x20

# --- depth chain / SLIPs (§24) --------------------------------------------------

NUM_SLIP_BANDS = 64
SLIP_BAND_PIXELS = 8

#: Words in ``mob_depth_key`` (0x904940) -- and, not coincidentally, the ROM's
#: own threshold for "managed low slot". ``moblist_insert`` (0x5DD14) and
#: ``insert_mob_depth_sorted`` (0x5DFFC) both compare a chain node against 0x20
#: to decide whether to order it by its slot number or by its depth key, so
#: this constant is a rule, not just a table size (see ``mob.MobTable.sort_key``).
NUM_DEPTH_KEYS = 32

# --- timing ---------------------------------------------------------------------

FRAMES_PER_SECOND = 60
HEALTH_DRAIN_MASK = 0x3F        # one point per player per 64 frames (§4.3)
FRAME_OVERFLOW_SET = 8          # ``frame_overflow`` reload value
