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
    """``player_status`` (0x9049A0), one byte per player. §4.1."""

    REMOVED = 0x00
    ALIVE_HERE = 0x01
    ALIVE_NEXT = 0x02
    DYING = 0x04
    RESPAWN_WAIT = 0x08
    SELECTING = 0x10
    SECRET_NAME_ENTRY = 0x20


class Character(IntEnum):
    """Character class index. Used to index most per-class ROM tables."""

    WARRIOR = 0
    VALKYRIE = 1
    WIZARD = 2
    ELF = 3


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
NUM_DEPTH_KEYS = 32

# --- timing ---------------------------------------------------------------------

FRAMES_PER_SECOND = 60
HEALTH_DRAIN_MASK = 0x3F        # one point per player per 64 frames (§4.3)
FRAME_OVERFLOW_SET = 8          # ``frame_overflow`` reload value
