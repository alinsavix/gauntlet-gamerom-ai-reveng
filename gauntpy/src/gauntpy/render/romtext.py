"""ROM-transcribed HUD and front-end text.

Every string, glyph run and coordinate in this module comes out of the game
ROM, transcribed from ``row76.bin`` (game address ``A`` maps to file offset
``A - 0x40000``, big-endian) with the ROM address of each block in a comment --
the same convention ``subsystems/potions.py``, ``dragon.py`` and ``shots.py``
use for their tables (gauntpy ISSUES.md, "ROM tables transcribed from
row76.bin"). It exists so no module under ``render/`` has to invent front-end
copy: before this, the HUD carried its own ``WARRIOR/VALKYRIE/...`` labels and
the attract screens carried made-up ladder entries and instruction lines.

Two kinds of text live here.

**ASCII strings** are drawn with the ROM alpha font by ``render/text.py``.
Several are stored padded to a fixed field width (the cabinet centres them by
padding, e.g. ``" INSERT COIN "``); the padding is kept so the transcription is
literal, and call sites ``strip()`` when they do their own centring.

**Glyph runs** are sequences of raw alpha-ROM character codes rather than
ASCII. The alpha character ROM holds pre-baked HUD words above the ASCII range
(``gex.alphafont``'s own docstring: "plus prebaked HUD word glyphs higher up"),
each cell holding two half-width letters, and the info panel draws its labels
from those. ``character_hud_text_ptrs`` (0x57340) and the SCORE/HEALTH label
string at 0x574FE are both such runs; the ASCII spellings alongside them are
the fallback for a headless run with no ROM (and are themselves the ROM's
``character_name_strings``).
"""

from __future__ import annotations

__all__ = [
    "CHARACTER_NAMES", "CHARACTER_NAME_PLURALS", "PLAYER_COLOR_NAMES",
    "PLAYER_COLOR_RGBA", "CHARACTER_HUD_GLYPHS", "LABEL_SCORE_GLYPHS",
    "LABEL_HEALTH_GLYPHS", "GLYPH_KEY", "GLYPH_POTION",
    "TEXT_LEVEL", "TEXT_INSERT_COIN", "TEXT_PRESS_START", "TEXT_SELECT_HERO",
    "TEXT_GAME_OVER", "TEXT_ADD_COIN", "TEXT_ADD_COINS", "TEXT_ATARI_GAMES",
    "TEXT_COPYRIGHT", "TEXT_ON_LEVEL", "CHARACTER_SELECT_LINES",
    "TEXT_SCORE_PER_COIN", "HIGHSCORE_QUADRANTS",
    "BONUS_100_X_COINS", "BONUS_TREASURES_X", "BONUS_EQUALS", "BONUS_NONE",
    "BONUS_SECRET_5000", "GAMEPLAY_TIPS",
]

# --- character and player identity ----------------------------------------

#: ``character_name_strings`` -- ROM 0x57252, four fixed-width ten-byte labels
#: (``" WIZARD "`` and ``"  ELF   "`` are padded in the ROM; stripped here
#: because every call site centres them itself).
CHARACTER_NAMES = ("WARRIOR", "VALKYRIE", "WIZARD", "ELF")

#: The plural forms the high-score attract screen heads its four quadrants
#: with -- ROM 0x5801A / 0x5802C / 0x5803E / 0x5804E.
CHARACTER_NAME_PLURALS = ("WARRIORS", "VALKYRIES", "WIZARDS", "ELVES")

#: ``player_color_name_strings`` -- ROM 0x57222, the four padded colour labels
#: the game uses to name players ("RED WARRIOR" ... "GREEN ELF", the speech
#: table at 0xBD-0xCC in doc/04 §11.5).
PLAYER_COLOR_NAMES = ("RED", "BLUE", "YELLOW", "GREEN")

#: The one host-side choice in this module: an RGBA realisation of those four
#: names. The cabinet's actual alpha palettes live in colour RAM
#: (0x910000-0x9101FF, doc/01_hardware.md §6.2), written at runtime rather
#: than stored as a ROM table gex can read, so the exact IRGB values are not
#: recoverable from the ROMs. The four *names* are ROM data; these primaries
#: are the obvious rendering of them, and are the only place the HUD picks a
#: colour rather than reading one.
PLAYER_COLOR_RGBA = (
    (255, 64, 64, 255),      # RED
    (96, 128, 255, 255),     # BLUE
    (255, 224, 64, 255),     # YELLOW
    (96, 224, 96, 255),      # GREEN
)

#: ``character_hud_text_ptrs`` -- ROM 0x57340, four longword pointers to the
#: name runs at 0x57508 / 0x5750E / 0x57514 / 0x5751A. Each run is a NUL
#: terminated list of alpha glyph codes, indexed by character class, and is
#: what ``setup_infopanel`` draws at column 0x23 of the player's first row.
CHARACTER_HUD_GLYPHS = (
    (0xAB, 0xAC, 0xAD, 0xAE),              # WARRIOR
    (0xAF, 0xB0, 0xB1, 0xB2, 0xB3),        # VALKYRIE
    (0xB4, 0xB5, 0xB6, 0xB7),              # WIZARD
    (0xB8, 0xB9),                          # ELF
)

#: ROM 0x574FE, the run ``setup_infopanel`` draws at column 0x21 of the
#: player's second row: ``A8 A9 AA 20 20 A4 A5 A6 A7`` -- "SCORE", two blank
#: cells, "HEALTH".
LABEL_SCORE_GLYPHS = (0xA8, 0xA9, 0xAA)
LABEL_HEALTH_GLYPHS = (0xA4, 0xA5, 0xA6, 0xA7)

#: Inventory cell glyphs written by ``player_inv_update`` (0x45ACA): character
#: 0xA1 per held key, 0xA3 per held potion.
GLYPH_KEY = 0xA1
GLYPH_POTION = 0xA3

# --- panel and front-end strings -------------------------------------------

TEXT_LEVEL = "LEVEL "            # 0x57326, panel header at row 6
TEXT_ON_LEVEL = "ON LEVEL:"      # 0x57572
TEXT_SELECT_HERO = " SELECT HERO "   # 0x5751E
TEXT_PRESS_START = " PRESS START "   # 0x5752C
TEXT_ADD_COIN = "  ADD   COIN "      # 0x5753A
TEXT_ADD_COINS = "  ADD   COINS"     # 0x57548
TEXT_INSERT_COIN = " INSERT COIN "   # 0x57556
TEXT_GAME_OVER = "  GAME OVER  "     # 0x57564
TEXT_ATARI_GAMES = "ATARI GAMES"     # 0x575DE
#: 0x575F6. The leading '@' is not an at-sign: alpha glyph 0x40 is the
#: copyright mark, so this renders as "(c)1986" through the ROM font.
TEXT_COPYRIGHT = "@1986"

#: ``character_select_instruction_chain`` -- ROM 0x57072, three linked
#: ``{column, row, string_ptr, flags[, previous]}`` descriptors. Transcribed as
#: ``(text, column, row)`` in the order the chain links them.
CHARACTER_SELECT_LINES = (
    ("USE JOYSTICK", 2, 15),     # desc at 0x57090, string 0x570A6
    ("TO SELECT", 5, 18),        # desc at 0x57084, string 0x57090
    ("CHARACTER", 5, 21),        # desc at 0x57072, string 0x5707A
)

#: ``attract_highscores``'s screen text -- the descriptor block at 0x57FFA
#: opens with ``{column 6, row 14, 0x58002}`` for the title, then one
#: descriptor per class quadrant.
TEXT_SCORE_PER_COIN = "SCORE PER COIN"   # 0x58002, column 6, row 14
TEXT_SCORE_PER_COIN_POS = (6, 14)

#: ``(character_class, column, row)`` for the four-way split, straight off the
#: descriptors at 0x58004+ -- WARRIORS top left, ELVES top right, VALKYRIES
#: bottom left, WIZARDS bottom right.
HIGHSCORE_QUADRANTS = (
    (0, 2, 1),      # WARRIORS
    (3, 28, 1),     # ELVES
    (1, 1, 17),     # VALKYRIES
    (2, 26, 17),    # WIZARDS
)

#: ``show_level_end_bonus_screen`` (0x4D476) strings, ROM 0x5AB1A-0x5AB63.
BONUS_100_X_COINS = "100 x COINS"
BONUS_TREASURES_X = "TREASURES x"
BONUS_EQUALS = "BONUS ="
BONUS_NONE = "NO BONUS !!"
BONUS_SECRET_5000 = "5,000 x COINS = "

#: Gameplay tip strings, ROM 0x5999C-0x59B53, paired into the two-line units
#: the game shows them as. The final entry is a single line.
GAMEPLAY_TIPS = (
    ("MORE PLAYERS ALLOWS HIGHER", "BONUS MULTIPLIER"),
    ("ADD MORE PLAYERS FOR", "GREATER FIREPOWER"),
    ("ADD COINS ANYTIME", "FOR EXTRA HEALTH"),
    ("SHOOTING MAGIC POTIONS", "HAS A LESSER EFFECT"),
    ("STALLING WILL CAUSE", "DOORS TO OPEN"),
    ("FIGHT HAND TO HAND BY", "RUNNING INTO MONSTERS"),
    ("EXTRA FOOD ADDED", "FOR 3 OR 4 PLAYERS"),
    ("FIND SECRET WALLS FOR", "EXTRA FOOD/POTIONS"),
    ("SAVE KEYS FOR CLOSED", "TREASURE CHESTS"),
    ("JOYSTICK CONTROLS", "EXIT FROM TRANSPORTER"),
    ("FIND EXIT TO NEXT LEVEL", ""),
)
