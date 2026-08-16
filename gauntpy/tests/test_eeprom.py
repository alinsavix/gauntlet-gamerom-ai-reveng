"""EEPROM persistence and configuration decoding -- WP-19.

Pins down the two documented ``game_settings`` (0x904A24) fields this package
owns -- Game Difficulty (bits 5-7) and Coins to Start (bits 8-9), per
``doc/05_data_reference.md`` §1.10/§3.10 -- and that ``eeprom_periodic_write``
actually persists a changed settings word to disk and reloads it.
"""

from __future__ import annotations

from gauntpy.constants import GameMode
from gauntpy.mainloop import tick
from gauntpy.state import GameState
from gauntpy.subsystems import eeprom as ee


def test_default_settings_word_decodes_per_doc():
    """0x40070 game_default_settings = 0xE090 -- doc/05_data_reference.md §1.10.

    MAME's Game Options screen rendered this word's Coins-to-Start as "1",
    which is the doc's worked example for the raw-0-displays-as-1 mapping.
    """
    state = GameState(game_settings=0xE090)
    assert ee.game_difficulty(state) == 4
    assert ee.coins_to_start(state) == 1


def test_game_difficulty_decodes_bits_5_to_7():
    for difficulty in range(8):
        state = GameState(game_settings=difficulty << 5)
        assert ee.game_difficulty(state) == difficulty


def test_coins_to_start_decodes_bits_8_and_9_as_one_indexed():
    for raw in range(4):
        state = GameState(game_settings=raw << 8)
        assert ee.coins_to_start(state) == raw + 1


def test_difficulty_and_coins_bits_do_not_cross():
    """Bits 5-7 and 8-9 are adjacent; a decoder off by one bit would leak."""
    state = GameState(game_settings=(0x7 << 5))  # difficulty maxed, coins bits clear
    assert ee.game_difficulty(state) == 7
    assert ee.coins_to_start(state) == 1

    state = GameState(game_settings=(0x3 << 8))  # coins maxed, difficulty bits clear
    assert ee.game_difficulty(state) == 0
    assert ee.coins_to_start(state) == 4


def test_setters_round_trip_through_the_getters_without_disturbing_other_bits():
    state = GameState(game_settings=0xFFFF)
    ee.set_game_difficulty(state, 3)
    ee.set_coins_to_start(state, 2)

    assert ee.game_difficulty(state) == 3
    assert ee.coins_to_start(state) == 2
    # Every other bit (speech disable, attract sounds, etc.) must survive.
    assert state.game_settings & ~(ee.GSETTING_DIFFICULTY_MASK | ee.GSETTING_COINTOSTART_MASK) == (
        0xFFFF & ~(ee.GSETTING_DIFFICULTY_MASK | ee.GSETTING_COINTOSTART_MASK)
    )


def test_write_then_reload_round_trips_the_settings_word(tmp_path):
    save_path = str(tmp_path / "eeprom.json")

    writer = GameState(game_settings=0x1234, eeprom_save_path=save_path)
    ee.eeprom_save_settings(writer)

    reader = GameState(eeprom_save_path=save_path)
    assert reader.game_settings == 0  # untouched until loaded
    ee.eeprom_load_settings(reader)

    assert reader.game_settings == 0x1234
    assert reader.eeprom_settings_cache == 0x1234


def test_load_with_no_file_leaves_state_untouched(tmp_path):
    state = GameState(game_settings=0x55AA, eeprom_save_path=str(tmp_path / "missing.json"))
    ee.eeprom_load_settings(state)
    assert state.game_settings == 0x55AA


def test_periodic_write_flushes_only_when_the_timer_expires_and_the_word_changed(tmp_path):
    save_path = str(tmp_path / "eeprom.json")
    state = GameState(game_settings=0xABCD, eeprom_save_path=save_path, eeprom_write_timer=3)

    ee.eeprom_periodic_write(state)  # timer -> 2
    ee.eeprom_periodic_write(state)  # timer -> 1
    assert not (tmp_path / "eeprom.json").exists(), "must not write before the timer expires"

    ee.eeprom_periodic_write(state)  # timer -> 0: expires, word changed since cache (0)
    assert (tmp_path / "eeprom.json").exists()
    assert state.eeprom_settings_cache == 0xABCD
    assert state.eeprom_write_timer == ee.EEPROM_WRITE_INTERVAL, "reloads to 0x8CA0 (36,000 frames)"

    reader = GameState(eeprom_save_path=save_path)
    ee.eeprom_load_settings(reader)
    assert reader.game_settings == 0xABCD


def test_periodic_write_skips_the_file_when_nothing_changed(tmp_path):
    save_path = str(tmp_path / "eeprom.json")
    state = GameState(eeprom_save_path=save_path, eeprom_write_timer=1)
    state.eeprom_settings_cache = state.game_settings  # already in sync, e.g. right after boot load

    ee.eeprom_periodic_write(state)

    assert not (tmp_path / "eeprom.json").exists(), "unchanged settings must not trigger a write"
    assert state.eeprom_write_timer == ee.EEPROM_WRITE_INTERVAL, "the timer still reloads"


def test_the_main_loop_actually_calls_it():
    state = GameState(game_mode=GameMode.NORMAL)
    start_timer = state.eeprom_write_timer

    tick(state)

    assert state.eeprom_write_timer == start_timer - 1
