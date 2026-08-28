"""EEPROM persistence and operator configuration -- WP-19.

The options word (0x904A24) matters even though the operator menus do not:
bits 5-7 are the operator-facing "Game Difficulty", whose principal gameplay
effect is generator spawn probability (WP-8, not landed yet -- this module
only decodes/encodes the bits), and bits 8-9 are coins to start.

The real hardware stores this word inside a Hamming(15,10)-redundant,
30-byte-per-10-byte-record physical EEPROM image (``doc/02_os_rom.md`` §8.9),
written by ``eeprom_process``/``eeprom_read_block`` and read back by
``eeprom_init`` at boot. That codec is CPU/hardware emulation, which
``PLAN.md`` §1 rules out of scope ("we reimplement behaviour, not
instructions"); this module reimplements the *behaviour* --
``eeprom_periodic_write``'s countdown-timer/change-detection/flush pattern --
against a plain local file instead of the redundant physical layout.

High-score tables also live in the real EEPROM image (``doc/02_os_rom.md``
§8.11, ``read_high_score_entry`` 0x39B0 / ``write_high_score_entry`` 0x3A7E),
and now that WP-14 has landed ``GameState.high_scores`` this module persists
them too -- see ``encode_initials`` for the storage format it reproduces.

The cabinet's maze rotation is the third block: doc/06 §3.2 is explicit that
"the level -> maze mapping is cabinet state", and ``eeprom_load_config``
(0x42F86) reads its four values back as single bytes and range-checks each
one. ``eeprom_validate_rotation`` below is that check, and WP-15's
``maze_checknum`` already sets ``eeprom_write_timer = 1`` to force a save when
a lap wraps -- a line that only started meaning anything once these fields
were actually in the saved image.

What is still not persisted is the statistics block: the four coin/play
counters and ``games_played_counter`` (0x904B86, clamped to 2000 at
0x43076-0x43084) have no ``GameState`` representation at all. They are pure
bookkeeping for the operator screens, so nothing in the simulation reads them.

Reference: ``doc/04_game_subsystems.md`` §20; ``doc/06_maze_catalog.md`` §3.2
and §3.5 (the rotation words, their ranges and fresh-cabinet defaults);
``doc/02_os_rom.md`` §8.11 (the high-score record layout and base-40 initials
codec) and the EEPROM codec / redundant-block format;
``doc/05_data_reference.md`` §1.10 and §3.10 (``game_settings`` bit layout);
``nvram/`` for the real physical layout.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..state import GameState

# --- game_settings (0x904A24) bit layout ---------------------------------
#
# doc/05_data_reference.md §1.10 / §3.10 give the full sixteen bits; only the
# two this package is responsible for decoding get named masks here. The
# default word baked into the game ROM is 0xE090 (0x40070 game_default_settings),
# which decodes to difficulty 4 and coins-to-start 1 -- pinned down in
# tests/test_eeprom.py.

GSETTING_DIFFICULTY_MASK = 0x00E0   # bits 5-7, doc/05_data_reference.md §3.10
GSETTING_DIFFICULTY_SHIFT = 5

GSETTING_COINTOSTART_MASK = 0x0300  # bits 8-9, doc/05_data_reference.md §3.10
GSETTING_COINTOSTART_SHIFT = 8

#: ``game_default_settings`` -- the word baked into the game ROM at 0x40070.
#: ``one_time_init`` (0x432D8-0x432FA) reads the stored configuration item 12
#: and, when its bit 12 is set -- which is what an unprogrammed or
#: factory-fresh part reads back as -- replaces it with this word (clearing
#: 0x1000, which 0xE090 does not carry anyway) and writes it straight back
#: through OS 0x1C0.  It decodes to difficulty 4 and coins-to-start 1.
GAME_DEFAULT_SETTINGS = 0xE090

#: The bit that asks for the factory word (0x432D8 ``andi.l #$1000``).
GSETTING_RESTORE_DEFAULTS = 0x1000

#: §20: the countdown reloads to this value (36,000 frames, ~10 min @ 60Hz)
#: every time it reaches zero.
EEPROM_WRITE_INTERVAL = 0x8CA0


# --- high-score records (doc/02_os_rom.md §8.11) -------------------------
#
# ``read_high_score_entry`` (0x39B0) reads five bytes at
# ``config + 0x1E + class * 50 + rank * 5``: a three-byte big-endian score
# followed by a two-byte big-endian base-40 pack of the three initials. Class
# stride 50 is ten records, and both APIs reject a rank above 9. That fixes
# the four numbers below without a single guess.

#: Records per character class in the EEPROM image (rank 0-9).
HIGHSCORE_RANKS = 10
#: Character classes with their own ladder.
HIGHSCORE_CLASSES = 4
#: Three bytes of score -- ``write_high_score_entry`` stores 0xFFFFFF and
#: returns -2 for anything larger (0x3ABC-0x3AC6).
HIGHSCORE_MAX_SCORE = 0xFFFFFF
#: Initials per record.
HIGHSCORE_INITIALS = 3
#: The base the three initials are packed in: 40**3 = 64000 fits a word.
HIGHSCORE_ALPHABET_BASE = 40


def encode_initials(text: str) -> int:
    """Three initials -> the packed word ``write_high_score_entry`` stores.

    ROM 0x3AEC-0x3B40, transcribed branch for branch. Per character:
    lowercase is folded up (``>= 'a'`` minus 0x20), ``A``-``Z`` become 1-26,
    a space becomes 0, and everything else is ``c - 0x15`` -- which is what
    makes ``'0'``-``'9'`` land on 27-36. Anything still above 39 is replaced
    by a space. The three values are accumulated most-significant first
    (``d6 = d6 * 40 + c``), so the first initial is the high digit.

    That "everything else" arm is the ROM's, not a simplification: a
    character between ``!`` and ``@`` silently maps into the letter range
    (``'!'`` -> 12 -> ``'L'``), and ``:``/``;``/``<`` are the only producers
    of 37/38/39. ``decode_initials`` is its exact inverse, so a round trip is
    stable even for those.
    """
    packed = 0
    for char in (text + "   ")[:HIGHSCORE_INITIALS]:
        code = ord(char) & 0xFF
        if code >= 0x61:                      # fold lowercase up
            code -= 0x20
        if 0x41 <= code <= 0x5A:              # 'A'-'Z' -> 1-26
            value = code - 0x40
        elif code == 0x20:                    # space
            value = 0
        else:
            value = (code - 0x15) & 0xFF
        if value > HIGHSCORE_ALPHABET_BASE - 1:
            value = 0
        packed = packed * HIGHSCORE_ALPHABET_BASE + value
    return packed & 0xFFFF


def decode_initials(packed: int) -> str:
    """The packed word -> three ASCII initials (ROM 0x3A2C-0x3A74).

    Digit 0 is a space, 1-26 are ``A``-``Z``, and 27-39 are ``c + 0x15``
    (``'0'``-``'9'`` then ``:;<``). Read least-significant first, so the
    string comes back in the order ``encode_initials`` took it.
    """
    chars = []
    value = packed & 0xFFFF
    for _ in range(HIGHSCORE_INITIALS):
        digit = value % HIGHSCORE_ALPHABET_BASE
        value //= HIGHSCORE_ALPHABET_BASE
        if digit == 0:
            chars.append(" ")
        elif digit <= 26:
            chars.append(chr(digit + 0x40))
        else:
            chars.append(chr(digit + 0x15))
    return "".join(reversed(chars))


def _stored_record(score: int, initials: str) -> list:
    """One ladder entry as the EEPROM would hold it.

    The file is JSON rather than the physical five-byte record (see the module
    docstring), but the *constraints* of that record are behaviour, not
    layout: a score is clamped to 24 bits and initials are round-tripped
    through the base-40 codec, so what survives a save/reload here is exactly
    what would survive one on the cabinet.
    """
    clamped = min(max(int(score), 0), HIGHSCORE_MAX_SCORE)
    return [clamped, decode_initials(encode_initials(str(initials)))]


def _factory_records() -> tuple:
    """WP-14's ``factory_highscore_records`` (ROM 0x57EBA).

    Imported lazily: ``score.py`` is a subsystem and this module is imported
    by ``boot.py`` before most of them exist.
    """
    from .score import FACTORY_HIGHSCORE_RECORDS

    return FACTORY_HIGHSCORE_RECORDS


def _high_score_image(ladders) -> list:
    """The persistable form of the four ladders.

    An empty bank is the ROM's own "high-score banks are empty" condition
    (``highscore_table_init`` 0x49BD0), and a factory-fresh EEPROM reads back
    as the factory table, so an empty bank is normalised to the factory row
    here. That is what lets change detection compare a never-touched cabinet
    against its saved image and correctly decide there is nothing to write.
    """
    factory = _factory_records()
    image = []
    for character in range(HIGHSCORE_CLASSES):
        ladder = list(ladders[character]) if character < len(ladders) else []
        if not ladder:
            ladder = list(factory[character])
        image.append([_stored_record(*entry) for entry in ladder[:HIGHSCORE_RANKS]])
    return image


def _parse_high_score_image(data) -> list | None:
    """Validate a loaded ``high_scores`` payload, or ``None`` if it is junk."""
    if not isinstance(data, list) or len(data) != HIGHSCORE_CLASSES:
        return None
    image = []
    for ladder in data:
        if not isinstance(ladder, list) or len(ladder) > HIGHSCORE_RANKS:
            return None
        records = []
        for entry in ladder:
            if not isinstance(entry, (list, tuple)) or len(entry) != 2:
                return None
            score, initials = entry
            if not isinstance(score, int) or isinstance(score, bool):
                return None
            if not isinstance(initials, str):
                return None
            records.append(_stored_record(score, initials))
        image.append(records)
    return image


# --- cabinet maze rotation (doc/06 §3.2, §3.5) ---------------------------
#
# ``eeprom_load_config`` (0x42F86) reads four consecutive EEPROM bytes and
# range-checks each before it lets the rotation run. Verified at
# 0x42FF2-0x43066 in row76.bin, in this order:
#
#   0x904010 maze_number       -> maze_number         (>= 5, real maze record)
#   0x90400E maze_stride     -> maze_stride         (& 7)
#   0x904018 treas_mazerand_num -> treas_mazerand_num  (104..114 else 104)
#   0x904016 treas_mazerand_adder -> treas_mazerand_adder (& 3)
#
# The same four are what ``eeprom_periodic_write`` compares against its cache
# bytes at 0x904B8E-0x904B91 (0x4320C-0x4324E) to decide whether to flush --
# so a rotation that has moved on is exactly what makes the cabinet save.

#: Rotation resume position: where this cabinet stands in mazes 5-101.
MAZE_NUMBER_DEFAULT = 5
MAZE_NUMBER_MIN = 5
#: The ROM's upper guard is not a number: it indexes the Slapstic maze-pointer
#: table with the stored byte and rejects a zero entry (0x4300A-0x4301A), i.e.
#: "is there a maze record here at all". Every one of the 117 shipped mazes has
#: one (doc/06 §1; ``gex.constants.MAX_MAZE_NUM``), so a range check is the
#: ROM-free equivalent -- and this module must stay importable with no ROMs,
#: because ``boot.one_time_init`` calls it before anything else exists.
MAZE_NUMBER_MAX = 116

#: Extra mazes advanced per level, masked to three bits (0x43026).
MAZE_STRIDE_MASK = 0x07

#: Treasure-room rotation: the eleven treasure mazes, 0x68-0x72 (0x4303E-0x43054).
TREASURE_MAZE_DEFAULT = 0x68
TREASURE_MAZE_MIN = 0x68
TREASURE_MAZE_MAX = 0x72
#: Treasure stride, masked to two bits (0x43062).
TREASURE_STRIDE_MASK = 0x03

#: The saved-image keys, in the order ``eeprom_load_config`` reads their bytes.
_ROTATION_FIELDS = (
    "maze_number", "maze_stride", "treas_mazerand_num", "treas_mazerand_adder",
)


def _valid_maze_number(value: int) -> int:
    """0x43002-0x4301C: below 5, or naming no maze record, resets to 5."""
    return int(value) if MAZE_NUMBER_MIN <= value <= MAZE_NUMBER_MAX else MAZE_NUMBER_DEFAULT


def _valid_treasure_maze(value: int) -> int:
    """0x4303E-0x43054: outside the eleven treasure mazes resets to the first."""
    return (
        int(value) if TREASURE_MAZE_MIN <= value <= TREASURE_MAZE_MAX
        else TREASURE_MAZE_DEFAULT
    )


def eeprom_validate_rotation(state: GameState) -> None:
    """``eeprom_load_config``'s range checks on the four rotation values.

    Runs on every load, valid file or not, because that is what the original
    does: the config read is unconditional and each value is clamped on the way
    into RAM (0x42FF2-0x43066). A fresh cabinet's defaults already satisfy every
    rule, so this is a no-op there -- it earns its keep on a hand-edited save
    file, and as the one place that states the ranges WP-15's rotation is
    allowed to walk.
    """
    state.maze_number = _valid_maze_number(state.maze_number)
    state.maze_stride &= MAZE_STRIDE_MASK
    state.treas_mazerand_num = _valid_treasure_maze(state.treas_mazerand_num)
    state.treas_mazerand_adder &= TREASURE_STRIDE_MASK


def _rotation_image(state: GameState) -> dict:
    """The four rotation values as they would sit in the EEPROM's config block.

    Validated on the way out as well as in: the stored bytes are what a cabinet
    would come back up with, and ``eeprom_load_config`` would clamp them then,
    so writing an out-of-range value would only be a lie that survives one
    power cycle.
    """
    return {
        "maze_number": _valid_maze_number(state.maze_number),
        "maze_stride": int(state.maze_stride) & MAZE_STRIDE_MASK,
        "treas_mazerand_num": _valid_treasure_maze(state.treas_mazerand_num),
        "treas_mazerand_adder": int(state.treas_mazerand_adder) & TREASURE_STRIDE_MASK,
    }


def _factory_rotation() -> dict:
    """A fresh cabinet's config block (ROM 0x42FC4-0x42FC8 builds it inline)."""
    return {
        "maze_number": MAZE_NUMBER_DEFAULT,
        "maze_stride": 0,
        "treas_mazerand_num": TREASURE_MAZE_DEFAULT,
        "treas_mazerand_adder": 0,
    }


def _parse_rotation_image(data) -> dict | None:
    """Validate a loaded ``rotation`` payload, or ``None`` if it is junk."""
    if not isinstance(data, dict):
        return None
    values = {}
    for name in _ROTATION_FIELDS:
        value = data.get(name)
        if not isinstance(value, int) or isinstance(value, bool):
            return None
        values[name] = value
    return values


def game_difficulty(state: GameState) -> int:
    """Operator "Game Difficulty", 0-7 -- bits 5-7 of ``game_settings``.

    doc/05_data_reference.md §1.10: selects the row of
    ``monster_spawn_probability_table`` (0x40E46) that WP-8's generator
    spawning reads; not wired up by this module.
    """
    return (state.game_settings & GSETTING_DIFFICULTY_MASK) >> GSETTING_DIFFICULTY_SHIFT


def coins_to_start(state: GameState) -> int:
    """Operator "Coins to Start", displayed as 1-4 -- bits 8-9 of ``game_settings``.

    doc/05_data_reference.md §1.10: the raw stored value is 0-3 and the OS
    operator editor displays it as 1-4 (MAME rendered the default word's 0 as
    "1"). No normal game-code reader masks 0x0300.
    """
    raw = (state.game_settings & GSETTING_COINTOSTART_MASK) >> GSETTING_COINTOSTART_SHIFT
    return raw + 1


def set_game_difficulty(state: GameState, difficulty: int) -> None:
    """Set bits 5-7 of ``game_settings`` to ``difficulty`` (0-7), other bits untouched."""
    difficulty &= 0x7
    state.game_settings = (
        (state.game_settings & ~GSETTING_DIFFICULTY_MASK)
        | (difficulty << GSETTING_DIFFICULTY_SHIFT)
    ) & 0xFFFF


def set_coins_to_start(state: GameState, coins: int) -> None:
    """Set bits 8-9 of ``game_settings`` from a displayed 1-4 value, other bits untouched."""
    raw = (coins - 1) & 0x3
    state.game_settings = (
        (state.game_settings & ~GSETTING_COINTOSTART_MASK)
        | (raw << GSETTING_COINTOSTART_SHIFT)
    ) & 0xFFFF


def eeprom_load_settings(state: GameState) -> None:
    """Restore the persisted EEPROM image from ``state.eeprom_save_path``.

    No documented equivalent -- reimplements the *effect* of ``eeprom_init``
    (0x44E8) restoring the saved image at boot, plus ``one_time_init``'s
    factory-default arm (0x432D8-0x432FA), not the redundant-block decode.

    A missing file is a factory-fresh part. The real cabinet reads its
    unprogrammed configuration item 12 back with bit 12 set,
    ``one_time_init`` sees that and installs ``game_default_settings``
    (ROM 0x40070 = 0xE090) instead, then writes it back so the part is
    programmed from then on. That is what this does: the settings word takes
    the factory value and ``eeprom_settings_cache`` is synchronised with it, so
    the first periodic write does not immediately re-flush a word nothing
    changed. Leaving ``game_settings`` on its dataclass default of 0 was wrong
    in a way the whole cabinet could feel -- difficulty 0, attract sound off,
    and a coin-health table index that is not the ROM's.

    A file that exists but is unreadable, truncated, or not the JSON this
    module writes is treated exactly like a missing one, deliberately: the real
    EEPROM's whole point is that a bad block falls back to defaults rather than
    bricking the cabinet (``doc/02_os_rom.md`` §8.9's Hamming redundancy is
    that idea in hardware). Refusing to boot because a save file got truncated
    would be a worse reimplementation than ignoring it. So is carrying on with
    whatever happened to be in RAM.

    A stored word that *itself* has bit 12 set gets the same treatment, because
    that is literally the ROM's test (0x432D8) -- the operator's "restore
    factory defaults" request.

    High-score banks are only overwritten when the file actually carries
    them. An absent or unusable ``high_scores`` payload leaves
    ``state.high_scores`` empty, which is exactly the ROM's "high-score banks
    are empty" condition that ``score.highscore_table_init`` (0x49BD0) fills
    from the factory table -- so the two halves of the boot handshake compose
    without either knowing about the other. ``boot.one_time_init`` calls this
    at §5 step 6, before anything reads a ladder.

    The maze rotation follows the same rule, then goes through
    ``eeprom_validate_rotation`` -- which runs on *every* path, file or no
    file, because ``eeprom_load_config`` (0x42F86) range-checks those four
    values unconditionally on the way into RAM.
    """
    path = Path(state.eeprom_save_path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        settings = int(data["game_settings"]) & 0xFFFF
    except (OSError, ValueError, TypeError, KeyError):
        _install_factory_settings(state)
        eeprom_validate_rotation(state)
        return
    if settings & GSETTING_RESTORE_DEFAULTS:            # 0x432DE
        _install_factory_settings(state)
    else:
        state.game_settings = settings
        state.eeprom_settings_cache = state.game_settings
    try:
        state.two_player_mode = int(
            data.get("two_player_mode", state.two_player_mode)
        ) & 0xFFFF
    except (ValueError, TypeError):
        pass

    ladders = _parse_high_score_image(data.get("high_scores"))
    if ladders is not None:
        state.high_scores = [
            [(score, initials) for score, initials in ladder] for ladder in ladders
        ]

    rotation = _parse_rotation_image(data.get("rotation"))
    if rotation is not None:
        for name, value in rotation.items():
            setattr(state, name, value)
    eeprom_validate_rotation(state)


def _install_factory_settings(state: GameState) -> None:
    """0x432E0-0x432FA -- the ROM word, minus bit 12, written back and cached.

    The ROM's write-back is through OS ``write_config_word(0xC)``; here the
    cache *is* the change-detection shadow ``eeprom_periodic_write`` compares
    against (0x904B94), so synchronising it is the same "the part now holds
    this" statement without a spurious flush.
    """
    state.game_settings = GAME_DEFAULT_SETTINGS & ~GSETTING_RESTORE_DEFAULTS
    state.eeprom_settings_cache = state.game_settings


def eeprom_save_settings(state: GameState) -> None:
    """Persist the current EEPROM image to ``state.eeprom_save_path``.

    No documented equivalent -- reimplements the *effect* of ``eeprom_write``
    (0x43192) flushing the write buffer via OS 0x24E, not the physical
    Hamming-encoded layout. ``game_difficulty``/``coins_to_start`` are
    included decoded, for a human reading the file; ``two_player_mode`` is the
    host-side pricing/DIP seam re-read alongside ``game_settings``.
    ``eeprom_load_settings`` reads back.
    Written to a sibling temporary file and renamed over the target, so a
    process that dies mid-write leaves the previous image intact instead of
    a half-written file. That is the software equivalent of what the real
    part's redundant blocks buy: a flush is either visible or it isn't.
    """
    path = Path(state.eeprom_save_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        {
            "game_settings": state.game_settings,
            "two_player_mode": state.two_player_mode,
            "game_difficulty": game_difficulty(state),
            "coins_to_start": coins_to_start(state),
            "rotation": _rotation_image(state),
            "high_scores": _high_score_image(state.high_scores),
        }
    )
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(payload, encoding="utf-8")
    temp.replace(path)


def _stored_image(state: GameState) -> tuple[int | None, int | None, list, dict]:
    """What the host image holds: ``(settings, pricing, ladders, rotation)``.

    An absent or unusable file is a factory-fresh part, so its ladders read
    back as the factory table, its rotation as the fresh-cabinet block, and its
    settings word is unknown (``None``). Only the ladders and the rotation are
    used for change detection -- the settings half stays on
    ``eeprom_settings_cache``, the RAM shadow the ROM itself compares against
    at 0x43262 -- but returning all three keeps "what is on the part" in one
    place.
    """
    path = Path(state.eeprom_save_path)
    empty_ladders = _high_score_image([[] for _ in range(HIGHSCORE_CLASSES)])
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        settings = int(data["game_settings"]) & 0xFFFF
    except (OSError, ValueError, TypeError, KeyError):
        return None, None, empty_ladders, _factory_rotation()

    try:
        pricing = int(data["two_player_mode"]) & 0xFFFF
    except (ValueError, TypeError, KeyError):
        pricing = None

    ladders = _parse_high_score_image(data.get("high_scores"))
    if ladders is None:
        ladders = empty_ladders
    rotation = _parse_rotation_image(data.get("rotation"))
    if rotation is None:
        rotation = _factory_rotation()
    return settings, pricing, ladders, rotation


def eeprom_periodic_write(state: GameState) -> None:
    """0x431EE -- periodic write timer for the EEPROM shadow.

    doc/04_game_subsystems.md §20, verified against ROM 0x431F2-0x43270: a
    longword countdown at 0x904012 is decremented only while it is nonzero,
    and the flush check runs on the frame it reaches (or already sits at)
    zero. It then reloads to ``EEPROM_WRITE_INTERVAL`` (0x8CA0, ~10 min
    @ 60Hz) and compares the current settings against the cached "last
    written" copy (0x904B94 in the original,
    ``state.eeprom_settings_cache`` here). If they differ, ``eeprom_write``
    flushes them and the cache is updated; if they match, nothing is written
    -- an EEPROM has a finite number of write cycles, and this is what
    protects them.

    High scores and the maze rotation get the same protection by a different
    route. The ROM has ``write_high_score_entry`` *queue* the affected EEPROM
    regions (0x3A7E), and it compares the four rotation values against cache
    bytes at 0x904B8E-0x904B91 (0x4320C-0x4324E); reproducing either would need
    shadow fields on ``GameState`` and a call inside WP-14's writer -- other
    people's headings. Comparing against the saved image instead reaches the
    same decision from this side of the fence, and costs one small read per ten
    minutes of play. An absent file compares as a factory-fresh part, so a
    cabinet nobody has played still writes nothing, while the first new high
    score or the first rotation lap on it does. WP-15's ``maze_checknum``
    already forces the timer to 1 when a lap wraps, so that save lands on the
    very next frame.

    The original also gates this on ``games_played_counter`` (0x904B92 against
    0x904B86), which has no ``GameState`` representation -- see the module
    docstring. It differing also triggers the write, so the original flushes
    strictly more often than this does.
    """
    if not state.eeprom_persistence_enabled:
        return
    if state.eeprom_write_timer > 0:
        state.eeprom_write_timer -= 1
        if state.eeprom_write_timer > 0:
            return
    state.eeprom_write_timer = EEPROM_WRITE_INTERVAL

    _stored_settings, stored_pricing, stored_scores, stored_rotation = _stored_image(state)
    settings_changed = state.game_settings != state.eeprom_settings_cache
    pricing_changed = (
        state.two_player_mode != 1
        if stored_pricing is None
        else state.two_player_mode != stored_pricing
    )
    scores_changed = _high_score_image(state.high_scores) != stored_scores
    rotation_changed = _rotation_image(state) != stored_rotation

    if settings_changed or pricing_changed or scores_changed or rotation_changed:
        eeprom_save_settings(state)
        state.eeprom_settings_cache = state.game_settings
