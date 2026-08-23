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
    "CHARACTER_HUD_GLYPHS", "LABEL_SCORE_GLYPHS",
    "LABEL_HEALTH_GLYPHS", "LABEL_IT_GLYPHS", "GLYPH_KEY", "GLYPH_POTION",
    "TEXT_LEVEL", "TEXT_LEVEL_SPLASH", "TEXT_INSERT_COIN", "TEXT_PRESS_START",
    "TEXT_SELECT_HERO",
    "TEXT_GAME_OVER", "TEXT_ADD_COIN", "TEXT_ADD_COINS", "TEXT_ATARI_GAMES",
    "TEXT_COPYRIGHT", "TEXT_ON_LEVEL", "CHARACTER_SELECT_LINES",
    "CONTINUE_PROMPT_LINES",
    "TEXT_SCORE_PER_COIN", "TEXT_SCORE_PER_COIN_POS", "HIGHSCORE_QUADRANTS",
    "BONUS_100_X_COINS", "BONUS_TREASURES_X", "BONUS_EQUALS", "BONUS_NONE",
    "BONUS_SECRET_5000", "GAMEPLAY_TIPS",
    "DUNGEON_HEADER_GLYPHS", "LEGEND_RULES_TEXT", "LEGEND_CREDITS_TEXT",
    "LEGEND_MONSTER_TEXT",
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
# player_it_label_set writes the literal alpha codes for "IT" at 0x458BE.
LABEL_IT_GLYPHS = (0x49, 0x54)

#: Inventory cell glyphs written by ``player_inv_update`` (0x45ACA): character
#: 0xA1 per held key, 0xA3 per held potion.
GLYPH_KEY = 0xA1
GLYPH_POTION = 0xA3

# ``M_DUNGEON`` / ``character_glyph_rows`` -- ROM 0x574B8, five rows of
# twelve pre-baked cells written at alpha column 30, rows 0-4.
DUNGEON_HEADER_GLYPHS = tuple(
    tuple(range(start, start + 12))
    for start in (0xBA, 0xC6, 0xD2, 0xDE, 0xEA)
)

# --- panel and front-end strings -------------------------------------------

TEXT_LEVEL = "LEVEL "            # 0x57326, panel header at row 6
TEXT_LEVEL_SPLASH = "LEVEL:"     # descriptor 0x57634, string 0x5763C
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

# show_continue_prompt, ROM 0x57644-0x576A7.
CONTINUE_PROMPT_LINES = (
    ("                   ", 5, 12),
    ("   PRESS START     ", 5, 13),
    (" WITHIN    SECONDS ", 5, 14),
    (" TO CONTINUE GAME  ", 5, 15),
    ("   AT THIS LEVEL   ", 5, 16),
    ("                   ", 5, 17),
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

# ``load_legend_page`` rules page, ROM 0x5A6CE-0x5A8AB. Coordinates are the
# linked descriptor records consumed by draw_legend_rules_page (0x4CFDA).
LEGEND_RULES_TEXT = (
    ("FOOD", 6, 3), ("MAGIC", 6, 5), ("POTIONS", 6, 6),
    ("INVISIBILITY", 6, 11), ("INVULNERABILITY", 6, 12),
    ("REPULSIVENESS", 6, 13), ("REFLECTIVE SHOTS", 6, 15),
    ("10 SUPER SHOTS", 6, 16), ("TRANSPORTABILITY", 6, 18),
    ("WALL/FLOOR TYPES", 6, 20), ("FORCE FIELD", 12, 22),
    ("WALL", 6, 23), ("STUN TILE", 14, 24),
    ("DESTRUCTIBLE", 6, 25), ("TRAP", 19, 26),
    ("MOVABLE", 6, 27), ("EXIT", 19, 28),
    ("TREASURE", 13, 3), ("KEY", 18, 6),
    ("TEMPORARY", 0, 8), ("POTIONS", 0, 9),
    ("PERMANENT", 20, 9), ("POTIONS", 22, 10),
)

# Credits descriptor chains at ROM 0x5A99C/0x5AB0E.
LEGEND_CREDITS_TEXT = (
    ("DESIGNER/PROGRAMMER:", 2, 0), ("ED LOGG", 4, 1),
    ("GAME PROGRAMMER:", 2, 3), ("BOB FLANAGAN", 4, 4),
    ("VIDEO GRAPHICS:", 2, 6), ("SAM COMSTOCK", 4, 7),
    ("SUSAN G. MCBRIDE", 4, 8), ("ALAN MURPHY", 4, 9),
    ("WILL NOBLE", 4, 10), ("ENGINEER:", 2, 12),
    ("PAT MCCARTHY", 4, 13), ("TECHNICIAN:", 2, 15),
    ("CRIS DROBNY", 4, 16), ("SOUND DESIGN:", 2, 18),
    ("HAL CANON", 4, 19), ("BRAD FULLER", 4, 20),
    ("EARL VICKERS", 4, 21), ("CABINET DESIGN:", 2, 23),
    ("KEN HATA", 4, 24), ("SPECIAL THANKS TO:", 2, 26),
    ("MIKE ALBAUGH", 4, 27), ("DAVE THEURER", 4, 28),
    ("AND MANY OTHERS", 4, 29),
)

LEGEND_MONSTER_TEXT = (
    ("MONSTERS", 10, 0), ("Type", 1, 3), ("Type", 1, 18),
    ("Fight", 12, 18), ("Shoot", 18, 18), ("Magic", 24, 18),
    ("GHOST", 0, 4), ("GRUNT", 0, 5), ("DEMON", 0, 6),
    ("LOBBER", 0, 7), ("SORCERER", 0, 8), ("DEATH", 0, 9),
    ("ACID PUDDLE", 0, 10), ("SUPER SORCERER", 0, 11),
    ("IT", 0, 12), ("DRAGON", 0, 15),
)
