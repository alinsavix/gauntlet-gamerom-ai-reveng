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

High-score tables and per-level maze/pickup selection also live in the real
EEPROM image (``doc/02_os_rom.md`` §8.11, `read_high_score_entry` /
`write_high_score_entry`), but neither is represented in ``GameState`` yet --
that data belongs to WP-14 (scoring) and WP-3/WP-11 (maze/pickups)
respectively, and ground rule 1 in ``PLAN.md`` §3 reserves adding it to
whichever heading owns it. This module persists exactly what WP-19 owns
today: the ``game_settings`` word. When those other fields land, they should
join ``eeprom_periodic_write``'s change-detection and the saved file the same
way ``game_settings`` does now.

Reference: ``doc/04_game_subsystems.md`` §20; ``doc/02_os_rom.md`` (EEPROM
codec and redundant-block format); ``doc/05_data_reference.md`` §1.10 and
§3.10 (``game_settings`` bit layout); ``nvram/`` for the real physical layout.
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

#: §20: the countdown reloads to this value (36,000 frames, ~10 min @ 60Hz)
#: every time it reaches zero.
EEPROM_WRITE_INTERVAL = 0x8CA0


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
    """Load a previously persisted ``game_settings`` word from ``state.eeprom_save_path``.

    No documented equivalent -- reimplements the *effect* of ``eeprom_init``
    (0x44E8) restoring the settings word at boot, not its redundant-block
    decode. A missing file (first run) leaves ``state`` untouched, matching a
    factory-default EEPROM's already-initialized RAM image.
    """
    path = Path(state.eeprom_save_path)
    if not path.exists():
        return
    data = json.loads(path.read_text())
    state.game_settings = int(data["game_settings"]) & 0xFFFF
    state.eeprom_settings_cache = state.game_settings


def eeprom_save_settings(state: GameState) -> None:
    """Persist the current ``game_settings`` word to ``state.eeprom_save_path``.

    No documented equivalent -- reimplements the *effect* of ``eeprom_write``
    (0x43192) flushing the write buffer via OS 0x24E, not the physical
    Hamming-encoded layout. ``game_difficulty``/``coins_to_start`` are
    included decoded, for a human reading the file; only ``game_settings`` is
    read back by ``eeprom_load_settings``.
    """
    path = Path(state.eeprom_save_path)
    path.write_text(
        json.dumps(
            {
                "game_settings": state.game_settings,
                "game_difficulty": game_difficulty(state),
                "coins_to_start": coins_to_start(state),
            }
        )
    )


def eeprom_periodic_write(state: GameState) -> None:
    """0x431EE -- periodic write timer for the EEPROM shadow.

    doc/04_game_subsystems.md §20: a countdown timer decrements every frame;
    when it reaches zero it reloads to ``EEPROM_WRITE_INTERVAL`` (0x8CA0,
    ~10 min @ 60Hz) and the current settings are compared against the cached
    "last written" copy (0x904B94 in the original, ``state.eeprom_settings_cache``
    here). If they differ, ``eeprom_write`` flushes them and the cache is
    updated; if they match, nothing is written.

    The original also gates this on five statistics/counter RAM values
    (0x904010, 0x90400E, 0x904018, 0x904016, 0x904B86 ``games_played_counter``)
    that are not yet represented in ``GameState`` -- see the module docstring.
    """
    state.eeprom_write_timer -= 1
    if state.eeprom_write_timer > 0:
        return
    state.eeprom_write_timer = EEPROM_WRITE_INTERVAL

    if state.game_settings != state.eeprom_settings_cache:
        eeprom_save_settings(state)
        state.eeprom_settings_cache = state.game_settings
