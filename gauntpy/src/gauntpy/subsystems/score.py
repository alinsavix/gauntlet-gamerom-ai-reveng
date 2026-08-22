"""Scoring, HUD, and dialogs -- WP-14.

The two numeric HUD renderers (``draw_player_score`` 0x45940 and
``draw_player_health`` 0x459A2) write the alpha (text) layer on real hardware.
gauntpy splits that in the obvious way: **this module decides what the panel
says and when it changes**, latching the result into an ``InfoPanel``, and
``render/hud.py`` turns that latch into pixels. Nothing here imports the
renderer (PLAN.md §3 rule 7 -- rendering reads state, state never reads
rendering).

The panel geometry below is not invented: it is read straight off the ROM's own
drawing coordinates, disassembled from ``row76.bin`` (game address ``A`` maps to
file offset ``A - 0x40000``) --

* ``draw_player_score`` (0x45940) pushes ``display_decimal_value``
  (OS 0x260) ``(column 0x1D, row p*5+9, player_score[p], width 7, pad 1,
  player_text_palette_words[p])`` and then clears ``player_redraw`` bit 0.
* ``draw_player_health`` (0x459A2) writes the bonus multiplier as two alpha
  words at ``0x90503E + (row-1)*128`` (row ``p*5+8``, column 31) and pushes
  ``(column 0x25, row p*5+9, player_health[p], width 5, pad 1, attribute)``.
* ``setup_infopanel`` (0x452D0) clears 13 words per row starting 0x3A bytes
  into the row (columns 29-41), draws the character-name glyph run at column
  0x23, the SCORE/HEALTH label run at column 0x21, and "LEVEL " + a 3-digit
  level at row 6.
* ``player_inv_update`` (0x45ACA) fills 12 cells at column 30 of row ``p*5+10``.

Reference: ``doc/04_game_subsystems.md`` §10, §14, §25;
``doc/05_data_reference.md`` (0x57350 ``player_text_palette_words``, 0x57EBA
``factory_highscore_records``); ``doc/02_os_rom.md`` §8.1/§8.2 (``format_decimal``
padding mode: nonzero pads with **spaces**); ``doc/07_function_index.md``
(0x45940 / 0x459A2 / 0x49BD0 row and attribute notes);
``doc/generated/score_coin_dialog_contracts.csv``;
``book/14_score_and_economics.md``.
"""

from __future__ import annotations

from ..constants import GameMode
from ..coords import hpos_x, vpos_y
from ..state import NUM_PLAYERS, GameState
from .sound import sound_play, sound_speech_play


# score_star_picture_cycle / score_effect_picture_cycle_a/b -- ROM
# 0x576B6 / 0x576D2 / 0x576DA.  Transcribed byte-for-byte from row76.bin
# (28 B + 8 B + 8 B of big-endian words, ending exactly where
# ``shot_velocity_x`` starts at 0x576E2 -- doc/05_data_reference.md).
_TPORT_EFFECT_PICTURES = (
    0x0924, 0x0924, 0x092D, 0x092D, 0x0936, 0x0936, 0x093F,
    0x093F, 0x0948, 0x0948, 0x0951, 0x0951, 0x095A, 0x095A,
)
_PLAYER_IMPACT_PICTURES = (0x0EFC, 0x0EFC, 0x0FFC, 0x10FC)
_MONSTER_IMPACT_PICTURES = (0x1C5C, 0x1C5C, 0x1C60, 0x1C64)

#: ``tport_transition_pictures`` -- ROM 0x578F2, the twelve-word sparkle cycle
#: both transition loops step their animation MOB through (indices 0-11; the
#: sequence expands and contracts symmetrically). Transcribed from row76.bin.
_TPORT_TRANSITION_PICTURES = (
    0x1DCF, 0x1DD8, 0x1DE1, 0x1DEA, 0x1DF3, 0x1E00,
    0x1E00, 0x1DF3, 0x1DEA, 0x1DE1, 0x1DD8, 0x1DCF,
)


def _remove_effect(state: GameState, channel: int) -> None:
    state.mobs.unlink_and_clear(0x0D + channel)


def _advance_effect(state: GameState, channel: int) -> None:
    """Loop 3 of 0x4715E -- age one occupied shared effect channel."""
    slot = 0x0D + channel
    picture = state.mobs.picture[slot]
    if picture == 0:
        return

    counter = (state.mob_effect_anim_counter[channel] + 1) & 0xFF
    state.mob_effect_anim_counter[channel] = counter
    if counter & 1:
        return

    frame = counter // 2
    if 0x0924 <= picture <= 0x095A:
        if frame >= len(_TPORT_EFFECT_PICTURES):
            _remove_effect(state, channel)
        else:
            state.mobs.picture[slot] = _TPORT_EFFECT_PICTURES[frame]
        return

    pictures = (
        _PLAYER_IMPACT_PICTURES
        if 0x0EFC <= picture <= 0x10FC
        else _MONSTER_IMPACT_PICTURES
    )
    if frame >= len(pictures):
        _remove_effect(state, channel)
    else:
        state.mobs.picture[slot] = pictures[frame]


# ---------------------------------------------------------------------------
# The info panel (§14.1/§14.2) -- ROM geometry and the latched draw model.
# ---------------------------------------------------------------------------

#: ``player_text_palette_words`` (ROM 0x57350, doc/05_data_reference.md): four
#: player-indexed alpha attribute words. Bit 15 = opaque, bit 14 = palette
#: bank, bits 13-10 = palette number (doc/01_hardware.md §9), so these select
#: palettes 4, 5, 6, 7 -- one per player, the RED/BLUE/YELLOW/GREEN identities
#: the ROM's own ``player_color_name_strings`` (0x57222) name.
PLAYER_TEXT_PALETTE_WORDS = (0xD000, 0xD400, 0xD800, 0xDC00)
# player_inv_update 0x45AFA-0x45B6E: keys and potions use separate alpha
# palette families, each advanced by player<<10.
KEY_PALETTE_WORDS = (0xE000, 0xE400, 0xE800, 0xEC00)
POTION_PALETTE_WORDS = (0xF000, 0xF400, 0xF800, 0xFC00)

#: Alpha grid: 64 words per row, leftmost 42 columns displayed
#: (doc/01_hardware.md §9). The info panel is the 13-column block
#: ``setup_infopanel``'s clear loop walks: ``a0 += 0x3A`` (29 words) then 13
#: words then ``a0 += 0x2C`` (22 words) = one 64-word row.
PANEL_COLUMN = 29
PANEL_WIDTH = 13
PANEL_LAST_COLUMN = PANEL_COLUMN + PANEL_WIDTH - 1     # 41, the last shown column

#: Panel header (the ``player_selector == -1`` pass): "LEVEL " at row 6 column
#: 0x1F and a 3-digit level number at row 6 column 0x25.
LEVEL_ROW = 6
LEVEL_LABEL_COLUMN = 0x1F
LEVEL_VALUE_COLUMN = 0x25
LEVEL_DIGITS = 3

#: Per-player block: ``d4 = p*5 + 7`` names its first row, and the routine
#: clears four rows from there.
PLAYER_BLOCK_STRIDE = 5
PLAYER_NAME_ROW = 7          # character-name glyph run, column 0x23
PLAYER_LABEL_ROW = 8         # SCORE/HEALTH label run, column 0x21
PLAYER_VALUE_ROW = 9         # the two numeric fields
PLAYER_INV_ROW = 10          # keys/potions, column 30 (pointers at ROM 0x5FC12)
PLAYER_BLOCK_ROWS = 4

PLAYER_NAME_COLUMN = 0x23
PLAYER_LABEL_COLUMN = 0x21
SCORE_COLUMN = 0x1D
SCORE_DIGITS = 7
HEALTH_COLUMN = 0x25
HEALTH_DIGITS = 5
BONUSMULT_COLUMN = 31        # 0x90503E -> byte 0x3E of the row -> word 31
IT_LABEL_COLUMN = 0x24       # 0x905048, two ASCII glyph cells between labels
INVENTORY_COLUMN = 30
INVENTORY_CELLS = 12

#: Health redraw also fires below this value every time the player is selected,
#: which is what makes the low-health warning pulse (§14.2).
HEALTH_PULSE_THRESHOLD = 0xC8

#: Low-health dim: ``draw_player_health`` tests ``player_state_timer & 0xF``
#: against 8 and, on the dim half (and only while the timer is not its 0xFFFF
#: idle sentinel and the player has a live MOB), subtracts 0x1000 from the
#: attribute word. An acid-slowed player instead gets -0x2000.
LOW_HEALTH_PULSE_MASK = 0xF
LOW_HEALTH_DIM_PHASE = 8
STATE_TIMER_IDLE = 0xFFFF
ATTR_LOW_HEALTH_SHIFT = -0x1000
ATTR_ACID_SHIFT = -0x2000


def format_field(value: int, width: int) -> str:
    """OS ``format_decimal`` (0x2ABE) with padding mode 1: right-aligned in
    ``width`` columns, padded with **spaces**, not zeroes (doc/02_os_rom.md
    §8.1). Both HUD numbers are drawn that way; a value too wide for the field
    keeps its low ``width`` digits, matching the fixed-width alpha cells.
    """
    text = str(max(0, int(value)))
    return text[-width:].rjust(width)


def info_panel(state: GameState):
    """The info-panel shadow (``state.info_panel``, VRAM 0x905000).

    A plain accessor kept for call-site readability -- the panel is a real,
    default-constructed ``GameState`` field (``state.InfoPanel``), so there is
    nothing to create here.
    """
    return state.info_panel


# ---------------------------------------------------------------------------
# High-score table (§10.3, highscore_table_init 0x49BD0)
# ---------------------------------------------------------------------------

#: ``factory_highscore_records`` -- ROM 0x57EBA, 40 eight-byte records
#: ``{uint32_be score, char initials[3], uint8 zero}`` arranged as four
#: character-class lists of ten, because ``highscore_table_init`` indexes them
#: with ``class * 0x50 + rank * 8`` (doc/05_data_reference.md; transcribed from
#: row76.bin, which starts the block with score 0x1F40 = 8000 and initials
#: "AWC"). This is what a factory-fresh cabinet shows on its SCORES attract
#: screen.
FACTORY_HIGHSCORE_RECORDS: tuple[tuple[tuple[int, str], ...], ...] = (
    (   # Warrior
        (8000, "AWC"), (7600, "CJS"), (7200, "PAT"), (6800, "GDC"), (6400, "JDM"),
        (6000, "JG "), (5600, "RRC"), (5200, "JLR"), (4800, "TJK"), (4400, "DP "),
    ),
    (   # Valkyrie
        (8000, "RPA"), (7600, "JMR"), (7200, "RSA"), (6800, "MHW"), (6400, "TDL"),
        (6000, "BLK"), (5600, "MWC"), (5200, "SAK"), (4800, "TJG"), (4400, "GSF"),
    ),
    (   # Wizard
        (8000, "GAT"), (7600, "JRM"), (7200, "LCH"), (6800, "DSS"), (6400, "MRJ"),
        (6000, "DAY"), (5600, "MTH"), (5200, "SBH"), (4800, "CMH"), (4400, "SAL"),
    ),
    (   # Elf
        (8000, "T H"), (7600, "APK"), (7200, "BCG"), (6800, "BWH"), (6400, "BEA"),
        (6000, "BEM"), (5600, "MJS"), (5200, "JBD"), (4800, "SP "), (4400, "TRS"),
    ),
)

#: Ranks per class list (``read_high_score_entry`` returns 0 above rank 9).
HIGHSCORE_RANKS = 10


def highscore_table_init(state: GameState) -> None:
    """0x49BD0 -- seed the high-score banks from the ROM factory lists.

    The original reads the EEPROM through the OS high-score APIs and, "when the
    high-score banks are empty, copies the four class-specific ten-entry
    factory lists from ROM 0x57EBA" (doc/07_function_index.md). An empty
    ``state.high_scores[c]`` is that "bank is empty" condition, so this fills
    exactly the banks the EEPROM did not supply and leaves any restored ladder
    alone -- which is what lets an EEPROM load run before this call.
    """
    for character, records in enumerate(FACTORY_HIGHSCORE_RECORDS):
        if not state.high_scores[character]:
            state.high_scores[character] = [
                (value, initials) for value, initials in records
            ]


def high_scores(state: GameState) -> list[list[tuple[int, str]]]:
    """The live per-class high-score ladders, seeded on first use.

    ``high_scores(state)[character][rank]`` is ``(score, initials)``, ranks 0-9
    best first -- the shape ``read_high_score_entry`` (OS 0x1AE) exposes.
    """
    if any(not ladder for ladder in state.high_scores):
        highscore_table_init(state)
    return state.high_scores


def rank_high_score(state: GameState, character: int, value: int) -> int:
    """OS ``rank_high_score`` (0x1C6) -- where ``value`` would place in that
    class's ladder: rank 0-9, or ``HIGHSCORE_RANKS`` when it does not rank.

    §10.3: ``highscore_check`` (0x49D0E) passes the player's 24-bit
    **score-per-coin** value, not the raw score.
    """
    ladder = high_scores(state)[character & 3]
    for rank, (entry_value, _initials) in enumerate(ladder):
        if value > entry_value:
            return rank
    return HIGHSCORE_RANKS


def write_high_score_entry(
    state: GameState, character: int, rank: int, value: int, initials: str
) -> None:
    """OS ``write_high_score_entry`` (0x1B4) -- insert at ``rank``, shifting
    the class's records down and dropping the tenth."""
    if not 0 <= rank < HIGHSCORE_RANKS:
        return
    ladder = high_scores(state)[character & 3]
    ladder.insert(rank, (value, (initials + "   ")[:3]))
    del ladder[HIGHSCORE_RANKS:]


# ---------------------------------------------------------------------------
# The two numeric HUD renderers (§14.2). They latch into the panel shadow;
# render/hud.py draws whatever they last latched.
# ---------------------------------------------------------------------------

def _draw_player_score(state: GameState, player_index: int) -> None:
    """``draw_player_score`` (0x45940) -- 7-digit score via OS 0x260.

    Column 0x1D, row ``player_index * 5 + 9``, field width 7, padding mode 1,
    attribute ``player_text_palette_words[player_index]``.
    """
    field = info_panel(state).players[player_index]
    field.score = state.players[player_index].score
    field.score_attr = PLAYER_TEXT_PALETTE_WORDS[player_index]
    field.score_drawn = True


def _health_attribute(state: GameState, player_index: int) -> int:
    """The attribute word ``draw_player_health`` passes to OS 0x260.

    Disassembly of 0x45A32-0x45A88: the dim half of the low-health pulse is
    ``(player_state_timer & 0xF) < 8``, and it only dims while that timer is
    not its 0xFFFF idle sentinel *and* the player still has a live MOB
    (``active_mob_ids[p] != 0``). Failing that, an acid-slowed player
    (``0x905F40[p] > 0``) shifts by -0x2000 instead.
    """
    player = state.players[player_index]
    attr = PLAYER_TEXT_PALETTE_WORDS[player_index]
    timer = player.state_timer & 0xFFFF
    if (
        (timer & LOW_HEALTH_PULSE_MASK) < LOW_HEALTH_DIM_PHASE
        and timer != STATE_TIMER_IDLE
        and player.mob_slot
    ):
        return attr + ATTR_LOW_HEALTH_SHIFT
    if player.acid_timer > 0:
        return attr + ATTR_ACID_SHIFT
    return attr


def _draw_player_health(state: GameState, player_index: int) -> None:
    """``draw_player_health`` (0x459A2) -- bonus multiplier + 5-digit health.

    The multiplier occupies alpha columns 31-32 of row ``p*5+8`` and is only
    written when it is greater than one (otherwise those two cells are blanked
    with the player's own attribute word); the health field is column 0x25,
    row ``p*5+9``, width 5, padding mode 1.
    """
    player = state.players[player_index]
    field = info_panel(state).players[player_index]
    field.health = player.health
    field.bonusmult = player.bonusmult
    field.health_attr = _health_attribute(state, player_index)
    field.health_drawn = True


# ---------------------------------------------------------------------------
# Dialogs (§10.4). The message-box text lives on GameState, so the renderer
# draws what the game actually said.
# ---------------------------------------------------------------------------

#: Message records reached through the pointer table at ROM 0x5A200, indexed by
#: the *bit number* of the encounter mask. Each ROM record is three longword
#: line pointers (a NULL pointer ends the box early), transcribed here as the
#: lines themselves. The ROM pads each line to a fixed width so the box centres
#: without measuring; the padding is kept.
#: The shared second line of records 8-15, ROM string 0x59D80. Its identity --
#: not the record number -- is what 0x4C63C tests (``cmp.l #$59D80,4(a3)``)
#: before drawing the numeric field, so the port compares the same way.
DIALOG_NUMERIC_LINE = "  PLAYER LOSES    HEALTH  "
#: 0x4C654-0x4C674: ``display_number(column + 0xF, row, value, 2, 1, attr)``.
DIALOG_NUMERIC_COLUMN = 0x0F
DIALOG_NUMERIC_WIDTH = 2

DIALOG_MESSAGES: tuple[tuple[str, ...], ...] = (
    (" FOOD:  HEALTH ", " INCREASED BY  ", "       100     "),
    (" SOME FOOD ", " DESTROYED ", " BY SHOTS  "),
    (" INSERT COINS FOR ", "   MORE HEALTH    "),
    (" SAVE KEYS TO  ", " OPEN DOORS OR ", "   TREASURES   "),
    (" COLLECT MAGIC POTION  ", " BEFORE PRESSING MAGIC "),
    (" SAVE POTIONS  ", " FOR LATER USE "),
    ("  SHOOTING A POTION  ", " HAS A LESSER EFFECT "),
    (" SHOOTING POISON ", "  SLOWS MONSTERS "),
    ("  SHOOT OR AVOID GHOSTS   ", DIALOG_NUMERIC_LINE),
    ("  SHOOT OR FIGHT GRUNTS   ", DIALOG_NUMERIC_LINE),
    ("  SHOOT OR FIGHT DEMONS   ", DIALOG_NUMERIC_LINE),
    ("  SHOOT OR FIGHT LOBBERS  ", DIALOG_NUMERIC_LINE),
    (" SHOOT OR FIGHT SORCERERS ", DIALOG_NUMERIC_LINE),
    ("  POISONED: YOU ARE DIZZY ", DIALOG_NUMERIC_LINE),
    ("   SHOOT DRAGON'S HEAD    ", DIALOG_NUMERIC_LINE),
    ("    AVOID ACID PUDDLES    ", DIALOG_NUMERIC_LINE),
    ("   SHOOT SUPER SORCEROR   ", DIALOG_NUMERIC_LINE),
    ("  USE MAGIC TO KILL DEATH ", DIALOG_NUMERIC_LINE),
    ("  SHOTS DO NOT HURT  ", " OTHER PLAYERS (YET) "),
    (" MAGIC POTIONS AFFECT ", " EVERYTHING ON SCREEN "),
    (" KILL THIEF TO RECOVER ", "     STOLEN ITEM       "),
    ("    FIND STOLEN     ", " ITEM ON NEXT LEVEL "),
    (" SOME WALLS MAY ", "  BE DESTROYED  "),
    ("   TRAPS MAKE    ", " WALLS DISAPPEAR "),
    ("  TRANSPORTERS MOVE  ", " YOU TO THE CLOSEST  ",
     " VISIBLE TRANSPORTER "),
    ("  YOU ARE FULL OF  ", " BOMBS AND/OR KEYS "),
    (" SOME TILES STUN ", "     PLAYERS     "),
    (" USE KEY TO OPEN ", "  TREASURE CHEST "),
    (" YOU ARE NOW IT ",),
    (" KILL MUGGER TO ", "  RECOVER FOOD  "),
    (" FAKE EXIT:       ", "   FIND REAL EXIT "),
    ("    AVOID FORCE FIELDS    ", DIALOG_NUMERIC_LINE),
)

#: The parallel bank at ROM 0x5A300 -- the short forms used when the operator's
#: "Reduce Text" bit is set *and* the game is in an attract mode. Only entry 0
#: is populated in the ROM; a ``None`` falls back to nothing (the record
#: pointer is NULL, so the ROM returns without a box).
DIALOG_MESSAGES_SHORT: tuple[tuple[str, ...] | None, ...] = (
    (" FOOD/DRINK: ", "  100 HEALTH "),
) + (None,) * 31

#: Speech ids at ROM 0x5A280, indexed the same way; 0 = no speech entry. The
#: routine's return value is 1 exactly when it played one.
DIALOG_SPEECH_IDS: tuple[int, ...] = (
    0x00, 0x9D, 0x00, 0x00, 0x00, 0x00, 0xA8, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x9E, 0x00, 0x00, 0xB6, 0x00, 0xB7, 0xB8,
    0x00, 0x00, 0x00, 0xD2, 0x00, 0x00, 0x00, 0x00,
)

#: game_settings (0x904A24) bit 10 -- the operator "Reduce Text" option. It
#: selects the short message bank during attract and shortens the box timer.
GAME_SETTINGS_REDUCE_TEXT = 0x400

#: dialog_timer reload, 0x4C6DC/0x4C6E6: 150 frames normally, 120 with Reduce
#: Text set.
DIALOG_TIMER_FRAMES = 0x96
DIALOG_TIMER_FRAMES_SHORT = 0x78

# ``dialog_tip_ptrs`` at ROM 0x5815C, selected by 0xFF demo records.
DEMO_MESSAGES: tuple[tuple[str, ...], ...] = (
    ("   BLUE   ", " SELECTED ", "   ELF    "),
    ("  PUSH   ", " MOVABLE ", "  WALLS  "),
    ("  SOME TREASURE ", "  REQUIRES KEYS "),
    (" THERE CAN BE  ", " MORE THAN ONE ", "      TRAP     "),
    (" ACID PUDDLES  ", " MOVE RANDOMLY "),
    ("  SOME WALLS CAN  ", " BE SHOT AND TURN ", " INTO GOOD OR BAD "),
    (" DEATH DIES AFTER ", " TAKING UP TO 200 ", "      HEALTH      "),
    (" HAVE FRIENDS ", "   JOIN IN    ", "   ANY TIME   "),
    (" MONSTERS FOLLOW ", "  PLAYER WHO IS  ", "       IT        "),
    (" SOME WALLS MOVE ", "     RANDOMLY    "),
    (" MONSTERS MAY MOVE ", "    DIFFERENTLY    "),
    (" TAG, YOU'RE IT ",),
)

#: Sound 0x1C, "Message appears on screen" (§11.5), played at 0x4C6EE.
SOUND_MESSAGE_APPEARS = 0x1C

#: Box height: three rows plus one per extra line (0x4C54C).
DIALOG_BOX_BASE_ROWS = 3


def dialog_clear_message(state: GameState) -> None:
    """0x4C70A -- blank the message buffer at 0x904AA4.

    The ROM writes spaces over the previous message's cells before drawing the
    new one; here the buffer *is* the message, so clearing it is the whole
    effect and it is also what removes the box from the HUD.
    """
    state.dialog_message = []
    state.dialog_box_width = 0
    state.dialog_box_rows = 0
    state.dialog_player = -1
    state.dialog_box_column = -1
    state.dialog_box_row = -1


def _position_dialog_box(state: GameState, player_index: int) -> None:
    """0x4CB50 -- choose an alpha-cell origin near the owning player."""
    column, row = 14, 15
    if 0 <= player_index < NUM_PLAYERS:
        player = state.players[player_index]
        if player.mob_slot:
            x = hpos_x(state.mobs.hpos[player.mob_slot]) - state.scroll_x
            y = vpos_y(state.mobs.vpos[player.mob_slot]) - state.scroll_y - 8
            column = (x >> 3) & 0x3F
            row = (y >> 3) & 0x3F
            if column > 28 or row > 29:
                column, row = 14, 15

    if row < 15:
        row += 4
    else:
        row -= state.dialog_box_rows + 1
    width = state.dialog_box_width
    if (column > (width >> 1)
            and column < 29 - ((width + 1) >> 1)):
        column -= width >> 1
    elif column >= 29 - ((width + 1) >> 1):
        column = 28 - width
    else:
        column = 1
    state.dialog_box_column = column
    state.dialog_box_row = row


def demo_message_show(state: GameState, player_index: int,
                      message_index: int) -> None:
    """0x4C9A2 -- display one recorded attract-demo tip."""
    if not 0 <= message_index < len(DEMO_MESSAGES):
        return
    if state.dialog_timer:
        state.dialog_timer = 1
        main_msgbox_countdown(state)

    lines = DEMO_MESSAGES[message_index]
    dialog_clear_message(state)
    state.dialog_message = list(lines)
    state.dialog_box_rows = DIALOG_BOX_BASE_ROWS + (len(lines) - 1)
    state.dialog_box_width = len(lines[0])
    state.dialog_player = player_index if 0 <= player_index < NUM_PLAYERS else -1
    _position_dialog_box(state, state.dialog_player)
    state.dialog_timer = (
        DIALOG_TIMER_FRAMES_SHORT
        if state.game_settings & GAME_SETTINGS_REDUCE_TEXT
        else DIALOG_TIMER_FRAMES
    )


def _dialog_line(line: str, numeric_value: int) -> str:
    """0x4C63C-0x4C67A -- splice the numeric field into the shared line.

    After each record line is drawn, the ROM compares the record's *second*
    string pointer against 0x59D80 and, when they match, draws a two-digit
    right-aligned decimal field over that line at ``column + 0xF`` in the
    player's palette shifted by +0x1000 (``display_number``, OS 0x260, width 2,
    padding mode 1).  The line the pointer names is
    ``"  PLAYER LOSES    HEALTH  "``, whose columns 15-16 are the blank gap
    between the two words -- so records 8-15 all read "PLAYER LOSES nn HEALTH"
    with the damage the caller passed in.  Every other line is drawn as it is.
    """
    if line != DIALOG_NUMERIC_LINE:
        return line
    field = format_field(numeric_value, DIALOG_NUMERIC_WIDTH)
    start = DIALOG_NUMERIC_COLUMN
    return line[:start] + field + line[start + DIALOG_NUMERIC_WIDTH:]


def dialog_first_encounter(
    state: GameState, player_index: int, encounter_mask: int, numeric_value: int = 0
) -> int:
    """0x4C440 -- show a first-encounter message box once per game (§10.4).

    Returns 1 when the selected record has a speech entry and 0 otherwise,
    including the already-seen and no-record paths -- the contract checked in
    ``doc/generated/score_coin_dialog_contracts.csv``.

    Verified structure (disassembly of 0x4C440-0x4C708):

    * already-flagged masks return immediately (the 0x40000000 mask has an
      extra one-shot sound branch of its own, which belongs to its caller's
      state and is not reached from here);
    * a box already on screen is force-expired by setting ``dialog_timer`` to 1
      and calling ``main_msgbox_countdown``;
    * the mask's bit number selects the record; the 0x5A300 bank is used only
      when Reduce Text is set *and* ``game_mode`` is negative;
    * a NULL record returns 0 without showing anything;
    * the box is 3 rows plus one per extra line, drawn in the player's text
      palette shifted by -0x1000, and sound 0x1C plays;
    * records 8-15 share the ``PLAYER LOSES __ HEALTH`` line, and the
      ``numeric_value`` argument is drawn into its gap as a two-digit field
      (0x4C63C-0x4C67A) -- see ``_dialog_line``.
    """
    mask = encounter_mask & 0xFFFFFFFF
    if state.dialog_first_encounter_flags & mask:
        return 0

    state.dialog_first_encounter_flags |= mask

    index = 0
    while index < 32 and not (mask & (1 << index)):
        index += 1
    if index >= len(DIALOG_MESSAGES):
        return 0

    reduce_text = bool(state.game_settings & GAME_SETTINGS_REDUCE_TEXT)
    if reduce_text and state.game_mode < 0:
        lines = DIALOG_MESSAGES_SHORT[index]
    else:
        lines = DIALOG_MESSAGES[index]
    if lines is None:
        return 0

    spoken = 0
    speech_id = DIALOG_SPEECH_IDS[index]
    if speech_id:
        sound_speech_play(state, speech_id)
        spoken = 1
    if state.suppress_first_encounter_messages:
        return spoken

    if state.dialog_timer:
        state.dialog_timer = 1              # force the previous box to expire
        main_msgbox_countdown(state)

    dialog_clear_message(state)
    state.dialog_message = [_dialog_line(line, numeric_value) for line in lines]
    state.dialog_box_rows = DIALOG_BOX_BASE_ROWS + (len(lines) - 1)
    state.dialog_box_width = max(len(line) for line in lines)
    state.dialog_player = player_index if 0 <= player_index < NUM_PLAYERS else -1
    _position_dialog_box(state, state.dialog_player)
    state.dialog_timer = (
        DIALOG_TIMER_FRAMES_SHORT if reduce_text else DIALOG_TIMER_FRAMES
    )
    sound_play(state, SOUND_MESSAGE_APPEARS)
    return spoken


# ---------------------------------------------------------------------------
# Main-loop calls (WP-14 owns these three addresses)
# ---------------------------------------------------------------------------

def main_msgbox_countdown(state: GameState) -> None:
    """0x4CCBC -- decrement ``dialog_timer`` and erase the box at zero.

    This is the call that releases the gate in ``game_frame``. A value of 1 is
    also used to force immediate cleanup during screen transitions, which is
    how ``dialog_first_encounter`` retires a box that is still up.
    """
    if state.dialog_timer == 0:
        return
    state.dialog_timer -= 1
    if state.dialog_timer == 0:
        dialog_clear_message(state)


#: Fixed MOB slots the two transition passes drive (constants.SLOT_TPORT_ANIMS
#: is 25-29). Loop 2 animates 25-28, one per player; loop 1b animates the
#: shared slot 29.
_TPORT_ANIM_SLOT = 0x19          # + player index
_THIEF_ANIM_SLOT = 0x1D

#: Milestones of both passes, on ``counter >> 1`` (0x471D8 / 0x472EE); each is
#: acted on only when the counter itself is even.
_TRANSITION_SAVE = 0x05
_TRANSITION_MOVE = 0x0B
_TRANSITION_RESTORE = 0x10
_TRANSITION_LAST = 0x16          # "> 0x16" is the cleanup branch
_TRANSITION_IDLE = -1            # the ROM stores 0xFFFF


def _transition_picture(step: int) -> int | None:
    """The sparkle frame for milestone ``step`` -- table 0x578F2 indexed by
    ``step`` below 0x0B and by ``step - 0x0B`` from 0x0B to 0x16 (0x47296 and
    0x472B4), so the cycle runs twice: once collapsing, once re-forming."""
    if step < _TRANSITION_MOVE:
        return _TPORT_TRANSITION_PICTURES[step]
    if step <= _TRANSITION_LAST:
        return _TPORT_TRANSITION_PICTURES[step - _TRANSITION_MOVE]
    return None


def _advance_thief_transition(state: GameState) -> None:
    """Loop 1b (0x471BA-0x472C6) -- the thief's transporter dissolve.

    Gated on the shared animation MOB (slot 0x1D) having a picture. The counter
    at 0x904BD6 advances every frame; milestones act on even counts only.
    """
    if (
        state.thief_tport_timer < 0
        or state.mobs.picture[_THIEF_ANIM_SLOT] == 0
    ):
        return

    counter = (state.thief_tport_timer + 1) & 0xFFFF
    state.thief_tport_timer = counter
    if counter & 1:
        return
    step = counter >> 1

    if step == _TRANSITION_SAVE:
        # 0x471EC: stash the thief's picture, unlink it, and adopt the
        # destination cell recorded at 0x904BE0 as the thief's new position.
        state.thief_tport_saved_picture = state.mobs.picture[state.thief_current_pos]
        state.mobs.unlink_and_clear(state.thief_current_pos)
        state.thief_current_pos = state.thief_tport_dest
    elif step == _TRANSITION_MOVE:
        # 0x47218: re-stamp the fixed thief animation channel (25 + 4) at the
        # destination through the one implementation of handle_tport.
        from .players import handle_tport
        handle_tport(state, state.thief_tport_dest, 4)
    elif step == _TRANSITION_RESTORE:
        # 0x47236: put the saved picture back at the new position.
        state.mobs.picture[state.thief_current_pos] = state.thief_tport_saved_picture
    elif step > _TRANSITION_LAST:
        # 0x4724A: retire the animation MOB and re-plan the thief's route.
        state.mobs.depth_remove(_THIEF_ANIM_SLOT - 1)      # pea.l $1c.w
        state.mobs.picture[_THIEF_ANIM_SLOT] = 0
        state.thief_tport_timer = _TRANSITION_IDLE
        state.thief_previous_pos = state.thief_current_pos
        return

    picture = _transition_picture(step)
    if picture is not None:
        state.mobs.picture[_THIEF_ANIM_SLOT] = picture


def _advance_player_transition(state: GameState, player_index: int) -> None:
    """Loop 2 (0x472CA-0x473C0) -- one player's transporter transition.

    Identical milestone machine to loop 1b, per player, on the animation MOB at
    slot 25+i and the phase counter ``player_tport_phase[i]`` (0x904BCE). The
    ROM's three helpers are the save (0x50616), the move (0x50662) and the
    restore (``tport_restore_player_picture`` 0x50B88).
    """
    anim_slot = _TPORT_ANIM_SLOT + player_index
    if (
        state.player_tport_phase[player_index] < 0
        or state.mobs.picture[anim_slot] == 0
    ):
        return

    counter = (state.player_tport_phase[player_index] + 1) & 0xFFFF
    state.player_tport_phase[player_index] = counter
    if counter & 1:
        return
    step = counter >> 1

    panel_saved = state.player_tport_saved_picture
    player = state.players[player_index]

    if step == _TRANSITION_SAVE:
        panel_saved[player_index] = state.mobs.picture[player.mob_slot]
        state.mobs.picture[player.mob_slot] = 0x1709
    elif step == _TRANSITION_MOVE:
        from .players import tport_player_move
        tport_player_move(state, player_index)
    elif step == _TRANSITION_RESTORE:
        state.mobs.picture[player.mob_slot] = panel_saved[player_index]
        panel_saved[player_index] = 0
    elif step > _TRANSITION_LAST:
        state.mobs.depth_remove(
            _TPORT_ANIM_SLOT + player_index - 1,
        )  # 0x4734A: d4 + 0x18
        state.mobs.picture[anim_slot] = 0
        state.player_tport_phase[player_index] = _TRANSITION_IDLE
        return

    picture = _transition_picture(step)
    if picture is not None:
        state.mobs.picture[anim_slot] = picture

def main_score_update(state: GameState) -> None:
    """0x4715E -- three indexed loops plus the thief/effect transition pass.

    Popup timers, the shared thief transition, per-player transition MOBs, and
    the four ``mob_effect_anim_counter`` bytes. Projectile movement is **not**
    here; it is ``main_handle_shots``, an independent top-level call.
    """
    # ------------------------------------------------------------------
    # Loop 1: temporary popup timers (0x90493A[i*2]).
    # Each slot maps to a floating score popup channel (slots 17-20 in the
    # MOB table).  Decrement the timer; when it reaches zero, clear the
    # picture at slot 0x11+i and drop that same slot from the depth chain --
    # the ROM's mob_depth_remove(0x10+i) resolves to 0x11+i, see
    # MobTable.depth_remove.
    # ------------------------------------------------------------------
    for i in range(4):
        if state.score_display_timer[i] > 0:
            state.score_display_timer[i] -= 1
            if state.score_display_timer[i] == 0:
                state.mobs.picture[0x11 + i] = 0
                state.mobs.depth_remove(0x10 + i)

    # Loop 1b: the shared thief/effect transition. The ROM runs it inside the
    # first pass of loop 1 only (0x471B4 tests the loop index), so it runs once
    # per frame, not four times.
    _advance_thief_transition(state)

    # Loop 2: per-player transporter/transition MOBs.
    for i in range(4):
        _advance_player_transition(state, i)

    # ------------------------------------------------------------------
    # Loop 3: age the four occupied shared effect MOBs. The byte counter wraps,
    # advances pictures only on even values, and releases the channel at the end
    # of its ROM picture sequence.
    # ------------------------------------------------------------------
    for i in range(4):
        _advance_effect(state, i)


def main_score_display(state: GameState) -> None:
    """0x457C0 -- render scores and the info panel. See §14.

    Called every frame.  Skips TITLE (0xFFFE) and SCORES (0xFFFF) screens.
    Updates one player per frame (``frame_counter & 3``), redrawing only the
    fields whose update conditions are met, and latches each redraw into the
    ``InfoPanel`` the renderer reads.

    **The redraw condition.** The ROM's own condition is ``player_redraw``
    (0x904908) bit 0 for score and bit 1 for health. ``setup_infopanel``
    (0x452D0, in ``players.py``) already sets both, but the individual value
    writers (``player_add_score`` and the coin/health paths) do not yet, so the
    flags are honoured *and* the latched value is compared against the live
    one. The flag being set and the value having changed are the same condition
    on real hardware, and the comparison keeps the panel truthful either way.
    It does not weaken the ROM cadence -- a change is still only picked up on
    this player's own turn in the four-frame rotation.
    """
    # Gate: TITLE and SCORES attract screens do not show the in-game HUD.
    if state.game_mode in (GameMode.TITLE, GameMode.SCORES):
        return

    # Master display gate (0x904007 bit 2).
    if not state.score_display_enabled:
        return

    # One player per frame, round-robin over the four slots.
    player_index = state.frame_counter & 3
    player = state.players[player_index]
    field = info_panel(state).players[player_index]

    # Score redraw: update bit 0 (see the docstring on change detection).
    if (
        state.score_dirty[player_index]
        or not field.score_drawn
        or field.score != player.score
    ):
        _draw_player_score(state, player_index)
        state.score_dirty[player_index] = 0

    # Health redraw: update bit 1 OR health below 0xC8 (the warning pulse).
    if (
        state.health_dirty[player_index]
        or player.health < HEALTH_PULSE_THRESHOLD
        or not field.health_drawn
        or field.health != player.health
        or field.bonusmult != player.bonusmult
    ):
        _draw_player_health(state, player_index)
        state.health_dirty[player_index] = 0
