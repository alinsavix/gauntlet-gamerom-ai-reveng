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
    "SECRET_CHARACTER_NAMES",
    "CHARACTER_HUD_GLYPHS", "LABEL_SCORE_GLYPHS",
    "LABEL_HEALTH_GLYPHS", "LABEL_IT_GLYPHS", "GLYPH_KEY", "GLYPH_POTION",
    "TEXT_LEVEL", "TEXT_LEVEL_SPLASH", "TEXT_INSERT_COIN", "TEXT_PRESS_START",
    "TEXT_SELECT_HERO",
    "TEXT_GAME_OVER", "TEXT_ADD_COIN", "TEXT_ADD_COINS", "TEXT_ATARI_GAMES",
    "TEXT_TIME",
    "TEXT_COPYRIGHT", "TEXT_ON_LEVEL", "CHARACTER_SELECT_LINES",
    "CONTINUE_PROMPT_LINES",
    "TEXT_SCORE_PER_COIN", "TEXT_SCORE_PER_COIN_POS", "HIGHSCORE_QUADRANTS",
    "BONUS_100_X_COINS", "BONUS_TREASURES_X", "BONUS_EQUALS", "BONUS_NONE",
    "BONUS_SECRET_5000", "LEVEL_FLAG_HINTS", "GAMEPLAY_TIPS",
    "TREASURE_ROOM_TITLE", "TREASURE_ROOM_LINES",
    "SECRET_ROOM_TITLE", "SECRET_ROOM_LINES", "SECRET_CHALLENGE_QUALIFIERS",
    "SECRET_HINT_HEADER", "SECRET_OBJECTIVE_HINTS",
    "DUNGEON_HEADER_GLYPHS", "LEGEND_RULES_TEXT", "LEGEND_CREDITS_TEXT",
    "LEGEND_MONSTER_ROWS",
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
PLAYER_COLOR_NAMES = (" RED  ", " BLUE ", "YELLOW", "GREEN ")

#: ``character_name_strings`` -- ROM 0x57252, fixed-width labels used by the
#: secret-room invitation's OS large-text call at 0x44FD4.
SECRET_CHARACTER_NAMES = ("WARRIOR ", "VALKYRIE", " WIZARD ", "  ELF   ")

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
DUNGEON_HEADER_GLYPHS = (
    (0xBA, 0xBB, 0xBC, 0xBD, 0xBE, 0xBF, 0xC0, 0xC1, 0xC2, 0xC3, 0xC4, 0xC5),
    (0xC6, 0xC7, 0xC8, 0xC9, 0xCA, 0xCB, 0xCC, 0xCD, 0xCE, 0xCF, 0xD0, 0xD1),
    (0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0xD9, 0xDA, 0xDB, 0xDC, 0xDD),
    (0xDE, 0xDF, 0xE0, 0xE1, 0xE2, 0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9),
    (0xEA, 0xEB, 0xEC, 0xED, 0xEE, 0xEF, 0xF0, 0xF1, 0xF2, 0xF3, 0xF4, 0xF5),
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
TEXT_TIME = "TIME:"                  # 0x57596, bonus-room panel header
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

# ``level_splash`` flag/cadence records, ROM 0x598B8-0x5999B. Each tuple is
# ``(text, column, row, alpha attribute)``; their speech gates remain in the
# routine because several records share the one-speech-per-splash latch.
LEVEL_FLAG_HINTS = {
    "hidden_potion": ("FIND THE HIDDEN POTION", 3, 21, 0x8400),
    "shots_stun": ("PLAYER SHOTS STUN OTHERS", 3, 22, 0x8800),
    "shots_hurt": ("PLAYER SHOTS HURT OTHERS", 3, 23, 0x8C00),
    "player_offscreen": ("PLAYERS CAN GO OFF SCREEN", 2, 24, 0x9000),
    "all_walls_invisible": ("ALL WALLS ARE INVISIBLE", 3, 25, 0x8400),
    "trap_walls_invisible": ("TRAP WALLS ARE INVISIBLE", 2, 25, 0x8400),
    "exit_moves": ("THE EXIT WILL MOVE", 5, 26, 0x8800),
}

# show_level_start_screen treasure-room branch, ROM 0x572C6-0x57325.
TREASURE_ROOM_TITLE = "TREASURE ROOM"
TREASURE_ROOM_LINES = (
    ("YOU HAVE    SECONDS", 5, 11, 0x8400),
    ("TO COLLECT TREASURES", 5, 12, 0x8400),
    ("YOU MUST EXIT TO", 7, 14, 0x8C00),
    ("RECEIVE BONUS POINTS", 5, 15, 0x8C00),
)

# show_level_start_screen's secret-room branch, ROM 0x5727A-0x572C5 and the
# optional qualifier descriptors/strings at 0x573D4-0x574B7.
SECRET_ROOM_TITLE = "SECRET ROOM"
SECRET_ROOM_LINES = (
    ("YOU HAVE PERFORMED", 6, 10, 0x8000),
    ("A SECRET TRICK", 8, 11, 0x8000),
    ("YOU HAVE    SECONDS TO EXIT", 1, 13, 0x8400),
)
SECRET_CHALLENGE_QUALIFIERS = (
    ("AFTER COLLECTING 6 TREASURES", 1, 14),
    ("AFTER COLLECTING ALL POTIONS", 1, 14),
    ("AFTER SHOOTING 3 SECRET WALLS", 0, 14),
    None,
    None,
    None,
    ("AFTER USING 5 TRANSPORTERS", 2, 14),
    None,
    None,
    None,
    ("AFTER REMOVING ALL TREASURE", 1, 14),
    ("AFTER SHOOTING 3 SECRET WALLS", 0, 14),
    ("WHILE YOU ARE IT", 6, 14),
    ("AFTER COLLECTING ALL POTIONS", 1, 14),
)

# level_splash's secret_need_hint branch, ROM 0x59786 and the 17 pointers at
# 0x597D8. The first four objectives deliberately share one hint.
SECRET_HINT_HEADER = "TO ENTER SECRET ROOM:"
SECRET_OBJECTIVE_HINTS = (
    "TRY TRANSPORTABILITY",
    "TRY TRANSPORTABILITY",
    "TRY TRANSPORTABILITY",
    "TRY TRANSPORTABILITY",
    "WATCH WHAT YOU SHOOT",
    "WATCH WHAT YOU SHOOT",
    "SAVE SUPER SHOTS",
    "DON'T USE INVULNERABILITY",
    "DON'T GET HIT",
    "TRY PUSHING A WALL",
    "DON'T BE FOOLED",
    "DON'T BE GREEDY",
    "GO ON A DIET",
    "DON'T BE GREEDY",
    "BE PUSHY",
    "IT COULD BE NICE",
    "DON'T HURT FRIENDS",
)

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
    ("FOOD", 6, 3, 0x9000), ("MAGIC", 6, 5, 0x9000),
    ("POTIONS", 6, 6, 0x9000), ("INVISIBILITY", 6, 11, 0x9000),
    ("INVULNERABILITY", 6, 12, 0x9000),
    ("REPULSIVENESS", 6, 13, 0x9000),
    ("REFLECTIVE SHOTS", 6, 15, 0x9000),
    ("10 SUPER SHOTS", 6, 16, 0x9000),
    ("TRANSPORTABILITY", 6, 18, 0x9000),
    ("WALL/FLOOR TYPES", 6, 20, 0x8000),
    ("FORCE FIELD", 12, 22, 0x8800), ("WALL", 6, 23, 0x9000),
    ("STUN TILE", 14, 24, 0x8800),
    ("DESTRUCTABLE", 6, 25, 0x9000), ("TRAP", 19, 26, 0x8800),
    ("MOVEABLE", 6, 27, 0x9000), ("EXIT", 19, 28, 0x8800),
    ("TREASURE", 13, 3, 0x8800), ("KEY", 18, 6, 0x8800),
    ("TEMPORARY", 0, 8, 0x8000), ("POTIONS", 0, 9, 0x8000),
    ("PERMANENT", 20, 9, 0x8000), ("POTIONS", 22, 10, 0x8000),
)

# ``draw_legend_monsters_page`` table, ROM 0x5A56E-0x5A669. Each row is
# (monster, Fight, Shoot, Magic); the routine writes the name beside the maze
# art and repeats it in the lower capability table.
LEGEND_MONSTER_ROWS = (
    ("GHOST", "NO", "YES", "YES"),
    ("GRUNT", "YES", "YES", "YES"),
    ("DEMON", "YES", "YES", "YES"),
    ("LOBBER", "YES", "YES", "YES"),
    ("SORCERER", "YES", "YES", "YES"),
    ("DEATH", "NO", "NO", "YES"),
    ("ACID PUDDLE", "NO", "NO", "STUN"),
    ("SUPER SORCERER", "NO", "YES", "STUN"),
    ("    IT", "NO", "STUN", "NO"),
    ("DRAGON", "NO", "YES", "STUN"),
)
LEGEND_MONSTER_VALUE_ATTRIBUTES = {
    "NO": 0x8800,
    "YES": 0x8400,
    "STUN": 0x8C00,
}

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
