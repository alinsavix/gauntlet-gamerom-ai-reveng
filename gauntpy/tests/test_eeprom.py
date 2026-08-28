"""EEPROM persistence and configuration decoding -- WP-19.

Pins down the two documented ``game_settings`` (0x904A24) fields this package
owns -- Game Difficulty (bits 5-7) and Coins to Start (bits 8-9), per
``doc/05_data_reference.md`` §1.10/§3.10 -- and that ``eeprom_periodic_write``
actually persists a changed settings word to disk and reloads it.
"""

from __future__ import annotations

import json

import pytest

from gauntpy.constants import GameMode
from gauntpy.mainloop import tick
from gauntpy.state import GameState
from gauntpy.subsystems import eeprom as ee
from gauntpy.subsystems.score import high_scores, write_high_score_entry


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

    # Any word *without* bit 12: that bit is the ROM's "restore factory
    # defaults" request (0x432D8), so a word carrying it never round-trips.
    writer = GameState(game_settings=0x2345, eeprom_save_path=save_path)
    ee.eeprom_save_settings(writer)

    reader = GameState(eeprom_save_path=save_path)
    assert reader.game_settings == 0  # untouched until loaded
    ee.eeprom_load_settings(reader)

    assert reader.game_settings == 0x2345
    assert reader.eeprom_settings_cache == 0x2345


def test_load_with_no_file_uses_the_factory_word(tmp_path):
    """0x432D8-0x432FA: an unprogrammed part reads back with bit 12 set, so
    one_time_init installs ``game_default_settings`` (ROM 0x40070) instead of
    whatever happened to be in RAM."""
    state = GameState(game_settings=0x55AA, eeprom_save_path=str(tmp_path / "missing.json"))
    ee.eeprom_load_settings(state)
    assert state.game_settings == ee.GAME_DEFAULT_SETTINGS == 0xE090
    assert state.eeprom_settings_cache == 0xE090, "the change-detection shadow follows"


def test_a_stored_restore_defaults_request_is_honoured(tmp_path):
    """Bit 12 set in the stored word *is* the operator's restore request."""
    save_path = tmp_path / "eeprom.json"
    save_path.write_text('{"game_settings": 4096}')     # 0x1000
    state = GameState(eeprom_save_path=str(save_path))
    ee.eeprom_load_settings(state)
    assert state.game_settings == 0xE090


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


# ---------------------------------------------------------------------------
# Timer shape (ROM 0x431F2-0x43204)
# ---------------------------------------------------------------------------

def test_the_countdown_never_runs_negative(tmp_path):
    """``tst.l (a0) / beq / subq.l #1,(a0)`` -- the ROM decrements only while
    the counter is nonzero, so a timer parked at zero flushes and reloads
    rather than counting down into negative frames."""
    state = GameState(eeprom_save_path=str(tmp_path / "eeprom.json"), eeprom_write_timer=0)
    state.eeprom_settings_cache = state.game_settings

    ee.eeprom_periodic_write(state)
    assert state.eeprom_write_timer == ee.EEPROM_WRITE_INTERVAL


def test_the_interval_is_a_full_ten_minutes_of_frames(tmp_path):
    """0x8CA0 == 36000 frames == 600 s at 60 Hz (§20)."""
    assert ee.EEPROM_WRITE_INTERVAL == 0x8CA0 == 36000

    save_path = str(tmp_path / "eeprom.json")
    state = GameState(game_settings=0x0BAD, eeprom_save_path=save_path)
    for _ in range(ee.EEPROM_WRITE_INTERVAL - 1):
        ee.eeprom_periodic_write(state)
    assert not (tmp_path / "eeprom.json").exists()

    ee.eeprom_periodic_write(state)
    assert (tmp_path / "eeprom.json").exists()


# ---------------------------------------------------------------------------
# Persistence robustness
# ---------------------------------------------------------------------------

def test_a_corrupt_save_file_falls_back_to_defaults(tmp_path):
    """The physical part is Hamming-redundant precisely so a bad block reads
    as defaults instead of bricking the cabinet (doc/02 §8.9). A truncated or
    garbage save file must not stop the game booting -- and must not leave
    whatever happened to be in RAM in place either."""
    save_path = tmp_path / "eeprom.json"
    save_path.write_text("{ this is not json")

    state = GameState(game_settings=0x0123, eeprom_save_path=str(save_path))
    ee.eeprom_load_settings(state)
    assert state.game_settings == ee.GAME_DEFAULT_SETTINGS == 0xE090
    assert state.eeprom_settings_cache == 0xE090


def test_a_save_file_missing_the_key_falls_back_to_defaults(tmp_path):
    save_path = tmp_path / "eeprom.json"
    save_path.write_text('{"something_else": 1}')

    state = GameState(game_settings=0x0123, eeprom_save_path=str(save_path))
    ee.eeprom_load_settings(state)
    assert state.game_settings == ee.GAME_DEFAULT_SETTINGS


def test_rotation_keys_from_before_the_naming_policy_are_not_migrated(tmp_path):
    save_path = tmp_path / "eeprom.json"
    rotation = {
        "maze_" + "resume": 42,
        "maze_" + "stride": 3,
        "treas_mazerand_num": 110,
        "treas_mazerand_adder": 2,
    }
    save_path.write_text(json.dumps({
        "game_settings": 57584,
        "rotation": rotation,
    }))

    state = GameState(eeprom_save_path=str(save_path))
    ee.eeprom_load_settings(state)

    assert (state.maze_number, state.maze_stride) == (5, 0)
    assert (state.treas_mazerand_num, state.treas_mazerand_adder) == (104, 0)


def test_a_factory_fresh_load_does_not_immediately_re_flush(tmp_path):
    """The cache is the change-detection shadow (0x904B94); installing the
    factory word without syncing it would burn a write cycle on every boot."""
    save_path = tmp_path / "eeprom.json"
    state = GameState(eeprom_save_path=str(save_path), eeprom_write_timer=1)
    ee.eeprom_load_settings(state)
    ee.eeprom_periodic_write(state)
    assert not save_path.exists()


def test_a_directory_where_the_save_file_should_be_is_survivable(tmp_path):
    (tmp_path / "eeprom.json").mkdir()
    state = GameState(game_settings=0x55AA, eeprom_save_path=str(tmp_path / "eeprom.json"))
    ee.eeprom_load_settings(state)
    assert state.game_settings == ee.GAME_DEFAULT_SETTINGS


def test_saving_creates_missing_parent_directories(tmp_path):
    save_path = tmp_path / "nested" / "deeper" / "eeprom.json"
    state = GameState(
        game_settings=0x0F0F,
        two_player_mode=0,
        eeprom_save_path=str(save_path),
    )
    ee.eeprom_save_settings(state)

    reader = GameState(eeprom_save_path=str(save_path))
    ee.eeprom_load_settings(reader)
    assert reader.game_settings == 0x0F0F
    assert reader.two_player_mode == 0


def test_saving_leaves_no_temporary_file_behind(tmp_path):
    save_path = tmp_path / "eeprom.json"
    state = GameState(game_settings=0x1357, eeprom_save_path=str(save_path))
    ee.eeprom_save_settings(state)
    ee.eeprom_save_settings(state)          # a second flush must overwrite cleanly

    assert sorted(p.name for p in tmp_path.iterdir()) == ["eeprom.json"]


def test_a_persisted_word_is_masked_to_sixteen_bits(tmp_path):
    save_path = tmp_path / "eeprom.json"
    save_path.write_text('{"game_settings": 66666}')

    state = GameState(eeprom_save_path=str(save_path))
    ee.eeprom_load_settings(state)
    assert state.game_settings == 66666 & 0xFFFF


def test_loading_syncs_the_change_detection_cache(tmp_path):
    """Otherwise the first periodic write after boot would flush a word that
    had just been read back unchanged -- an EEPROM has finite write cycles."""
    save_path = tmp_path / "eeprom.json"
    writer = GameState(game_settings=0x2468, eeprom_save_path=str(save_path))
    ee.eeprom_save_settings(writer)

    reader = GameState(eeprom_save_path=str(save_path), eeprom_write_timer=1)
    ee.eeprom_load_settings(reader)
    save_path.unlink()

    ee.eeprom_periodic_write(reader)
    assert not save_path.exists()


# ---------------------------------------------------------------------------
# High-score records -- doc/02_os_rom.md §8.11
# ---------------------------------------------------------------------------
#
# read_high_score_entry (0x39B0) reads five bytes at
# config + 0x1E + class * 50 + rank * 5: a three-byte big-endian score and a
# two-byte base-40 pack of the initials. The codec below is transcribed from
# write_high_score_entry's packer (0x3AEC-0x3B40) and that reader's unpacker
# (0x3A2C-0x3A74).

class TestInitialsCodec:
    def test_record_geometry_matches_the_os_api(self):
        assert ee.HIGHSCORE_RANKS == 10          # both APIs reject rank > 9
        assert ee.HIGHSCORE_CLASSES == 4
        assert ee.HIGHSCORE_MAX_SCORE == 0xFFFFFF  # three stored bytes
        assert ee.HIGHSCORE_ALPHABET_BASE ** ee.HIGHSCORE_INITIALS <= 0x10000

    def test_the_documented_alphabet(self):
        """space=0, A-Z=1-26, 0-9=27-36 (doc/02 §8.11)."""
        assert ee.encode_initials("   ") == 0
        assert ee.encode_initials("  A") == 1
        assert ee.encode_initials("  Z") == 26
        assert ee.encode_initials("  0") == 27
        assert ee.encode_initials("  9") == 36

    def test_the_first_initial_is_the_high_digit(self):
        """``d6 = d6 * 40 + c`` accumulates most-significant first (0x3B2C)."""
        base = ee.HIGHSCORE_ALPHABET_BASE
        assert ee.encode_initials("A  ") == 1 * base * base
        assert ee.encode_initials(" A ") == 1 * base
        assert ee.encode_initials("ABC") == (1 * base + 2) * base + 3

    def test_lowercase_is_folded_up(self):
        assert ee.encode_initials("abc") == ee.encode_initials("ABC")

    def test_the_out_of_alphabet_arm_is_the_roms(self):
        """Not a simplification: 0x3B16's else-branch is a bare ``c - 0x15``,
        so a character between ``!`` and ``@`` lands in the letter range, and
        only ``:;<`` produce 37-39. Anything still above 39 becomes a space.
        """
        assert ee.encode_initials("  !") == 0x21 - 0x15
        assert ee.decode_initials(ee.encode_initials("  !")) == "  L"
        assert ee.encode_initials("  :") == 37
        assert ee.encode_initials("  <") == 39
        assert ee.encode_initials("  \x60") == 0     # 0x60-0x20-0x15 > 39 -> space

    def test_short_and_long_names_are_padded_and_truncated(self):
        assert ee.decode_initials(ee.encode_initials("A")) == "A  "
        assert ee.decode_initials(ee.encode_initials("ABCDEF")) == "ABC"

    def test_the_codec_is_a_bijection_over_every_storable_word(self):
        """40**3 = 64000 packed values; every one has to survive a save and a
        reload, or a name quietly changes when the cabinet is power-cycled."""
        limit = ee.HIGHSCORE_ALPHABET_BASE ** ee.HIGHSCORE_INITIALS
        seen = set()
        for packed in range(limit):
            initials = ee.decode_initials(packed)
            assert len(initials) == ee.HIGHSCORE_INITIALS
            assert ee.encode_initials(initials) == packed
            seen.add(initials)
        assert len(seen) == limit

    def test_every_factory_name_round_trips(self):
        from gauntpy.subsystems.score import FACTORY_HIGHSCORE_RECORDS

        for ladder in FACTORY_HIGHSCORE_RECORDS:
            for _score, initials in ladder:
                assert ee.decode_initials(ee.encode_initials(initials)) == initials


class TestHighScorePersistence:
    def _played_state(self, tmp_path, **kwargs):
        state = GameState(eeprom_save_path=str(tmp_path / "eeprom.json"), **kwargs)
        high_scores(state)                       # seed the factory ladders
        return state

    def test_save_and_reload_round_trips_the_ladders(self, tmp_path):
        writer = self._played_state(tmp_path)
        write_high_score_entry(writer, 2, 0, 123456, "ZZZ")
        ee.eeprom_save_settings(writer)

        reader = GameState(eeprom_save_path=str(tmp_path / "eeprom.json"))
        ee.eeprom_load_settings(reader)

        assert high_scores(reader)[2][0] == (123456, "ZZZ")
        assert len(high_scores(reader)[2]) == ee.HIGHSCORE_RANKS
        assert high_scores(reader)[0] == high_scores(writer)[0]

    def test_a_reloaded_ladder_is_not_re_seeded_from_the_factory_table(self, tmp_path):
        """``highscore_table_init`` (0x49BD0) only fills *empty* banks, which
        is what lets an EEPROM load run before it. If the load left the bank
        empty the restored names would be silently replaced by the ROM's."""
        from gauntpy.subsystems.score import FACTORY_HIGHSCORE_RECORDS

        writer = self._played_state(tmp_path)
        write_high_score_entry(writer, 0, 0, 999999, "NEW")
        ee.eeprom_save_settings(writer)

        reader = GameState(eeprom_save_path=str(tmp_path / "eeprom.json"))
        ee.eeprom_load_settings(reader)
        assert reader.high_scores[0][0] == (999999, "NEW")
        assert high_scores(reader)[0][0] != FACTORY_HIGHSCORE_RECORDS[0][0]

    def test_a_file_without_high_scores_leaves_the_banks_empty(self, tmp_path):
        """The settings-only files this module used to write must still load,
        and must hand the factory seeding back to ``highscore_table_init``."""
        save_path = tmp_path / "eeprom.json"
        save_path.write_text('{"game_settings": 57488}')

        state = GameState(eeprom_save_path=str(save_path))
        ee.eeprom_load_settings(state)

        assert state.game_settings == 57488
        assert state.high_scores == [[], [], [], []]

    @pytest.mark.parametrize("payload", [
        '{"game_settings": 0, "high_scores": []}',
        '{"game_settings": 0, "high_scores": [[], [], []]}',
        '{"game_settings": 0, "high_scores": "nope"}',
        '{"game_settings": 0, "high_scores": [[[1]], [], [], []]}',
        '{"game_settings": 0, "high_scores": [[[1, 2]], [], [], []]}',
        '{"game_settings": 0, "high_scores": [[["x", "ABC"]], [], [], []]}',
    ])
    def test_a_malformed_ladder_falls_back_to_the_factory_table(self, tmp_path, payload):
        save_path = tmp_path / "eeprom.json"
        save_path.write_text(payload)

        state = GameState(eeprom_save_path=str(save_path))
        ee.eeprom_load_settings(state)

        assert state.high_scores == [[], [], [], []]

    def test_a_saved_score_is_clamped_to_the_stored_24_bits(self, tmp_path):
        """``write_high_score_entry`` stores 0xFFFFFF and returns -2 for
        anything larger (ROM 0x3ABC-0x3AC6); three bytes is three bytes."""
        writer = self._played_state(tmp_path)
        write_high_score_entry(writer, 1, 0, 0x1234567, "BIG")
        ee.eeprom_save_settings(writer)

        reader = GameState(eeprom_save_path=str(tmp_path / "eeprom.json"))
        ee.eeprom_load_settings(reader)
        assert high_scores(reader)[1][0] == (ee.HIGHSCORE_MAX_SCORE, "BIG")

    def test_saved_initials_survive_the_base40_codec(self, tmp_path):
        writer = self._played_state(tmp_path)
        write_high_score_entry(writer, 3, 0, 5000, "a1 ")
        ee.eeprom_save_settings(writer)

        reader = GameState(eeprom_save_path=str(tmp_path / "eeprom.json"))
        ee.eeprom_load_settings(reader)
        assert high_scores(reader)[3][0] == (5000, "A1 ")


class TestHighScoreChangeDetection:
    def test_a_factory_fresh_cabinet_writes_nothing(self, tmp_path):
        """Nobody has played and nobody has touched the operator menu, so the
        flush must not burn a write cycle -- and must not create a file whose
        only content is the ROM table it would seed anyway."""
        save_path = tmp_path / "eeprom.json"
        state = GameState(eeprom_save_path=str(save_path), eeprom_write_timer=1)
        state.eeprom_settings_cache = state.game_settings
        high_scores(state)                        # seeded, but unchanged

        ee.eeprom_periodic_write(state)
        assert not save_path.exists()

    def test_a_new_high_score_is_flushed_even_when_the_settings_are_untouched(self, tmp_path):
        """The ROM has ``write_high_score_entry`` queue the affected EEPROM
        regions (0x3A7E); comparing against the stored image is how this
        reimplementation reaches the same decision without a dirty flag on
        another package's GameState heading."""
        save_path = tmp_path / "eeprom.json"
        state = GameState(eeprom_save_path=str(save_path), eeprom_write_timer=1)
        state.eeprom_settings_cache = state.game_settings
        write_high_score_entry(state, 0, 0, 12345, "NEW")

        ee.eeprom_periodic_write(state)

        assert save_path.exists()
        reader = GameState(eeprom_save_path=str(save_path))
        ee.eeprom_load_settings(reader)
        assert high_scores(reader)[0][0] == (12345, "NEW")

    def test_an_unchanged_ladder_is_not_rewritten(self, tmp_path, monkeypatch):
        """The saved image *is* the shadow, so a second flush with nothing new
        must not burn a write cycle."""
        save_path = tmp_path / "eeprom.json"
        state = GameState(eeprom_save_path=str(save_path), eeprom_write_timer=1)
        write_high_score_entry(state, 0, 0, 12345, "NEW")
        ee.eeprom_periodic_write(state)
        assert save_path.exists()

        flushes = []
        monkeypatch.setattr(
            ee, "eeprom_save_settings", lambda s: flushes.append(s.game_settings)
        )
        state.eeprom_write_timer = 1
        ee.eeprom_periodic_write(state)

        assert flushes == [], "nothing changed; the flush must be skipped"
        assert state.eeprom_write_timer == ee.EEPROM_WRITE_INTERVAL

    def test_a_further_new_score_flushes_again(self, tmp_path):
        save_path = tmp_path / "eeprom.json"
        state = GameState(eeprom_save_path=str(save_path), eeprom_write_timer=1)
        write_high_score_entry(state, 0, 0, 12345, "ONE")
        ee.eeprom_periodic_write(state)

        write_high_score_entry(state, 0, 0, 23456, "TWO")
        state.eeprom_write_timer = 1
        ee.eeprom_periodic_write(state)

        reader = GameState(eeprom_save_path=str(save_path))
        ee.eeprom_load_settings(reader)
        assert [entry for entry in high_scores(reader)[0][:2]] == [
            (23456, "TWO"), (12345, "ONE")
        ]

    def test_the_ladders_ride_along_when_the_settings_word_changes(self, tmp_path):
        save_path = tmp_path / "eeprom.json"
        state = GameState(eeprom_save_path=str(save_path), eeprom_write_timer=1)
        write_high_score_entry(state, 2, 0, 4242, "RID")
        ee.set_game_difficulty(state, 6)

        ee.eeprom_periodic_write(state)

        reader = GameState(eeprom_save_path=str(save_path))
        ee.eeprom_load_settings(reader)
        assert ee.game_difficulty(reader) == 6
        assert high_scores(reader)[2][0] == (4242, "RID")


def test_the_boot_handshake_restores_scores_before_anything_reads_them(tmp_path):
    """``one_time_init`` loads the EEPROM at §5 step 6, and the first
    ``high_scores()`` call seeds only the banks it did not supply."""
    from gauntpy.subsystems.boot import one_time_init
    from gauntpy.subsystems.score import FACTORY_HIGHSCORE_RECORDS

    save_path = tmp_path / "eeprom.json"
    writer = GameState(game_settings=0xE090, eeprom_save_path=str(save_path))
    high_scores(writer)
    write_high_score_entry(writer, 1, 0, 31337, "BOO")
    ee.eeprom_save_settings(writer)

    booted = GameState(eeprom_save_path=str(save_path))
    one_time_init(booted)

    assert booted.game_settings == 0xE090
    assert high_scores(booted)[1][0] == (31337, "BOO")
    assert high_scores(booted)[0][0] == FACTORY_HIGHSCORE_RECORDS[0][0]


# ---------------------------------------------------------------------------
# Cabinet maze rotation -- doc/06 §3.2 / §3.5, eeprom_load_config (0x42F86)
# ---------------------------------------------------------------------------

class TestRotationValidation:
    """``eeprom_load_config`` range-checks all four values on the way into RAM
    (ROM 0x42FF2-0x43066, read byte by byte in this order)."""

    def test_the_documented_ranges_and_defaults(self):
        assert (ee.MAZE_NUMBER_DEFAULT, ee.MAZE_NUMBER_MIN) == (5, 5)
        assert ee.MAZE_STRIDE_MASK == 0x07
        assert ee.TREASURE_MAZE_DEFAULT == ee.TREASURE_MAZE_MIN == 0x68 == 104
        assert ee.TREASURE_MAZE_MAX == 0x72 == 114
        assert ee.TREASURE_STRIDE_MASK == 0x03

    def test_a_fresh_cabinets_defaults_are_already_valid(self):
        """doc/06 §3.2's fresh-EEPROM column, and the block the ROM builds
        inline at 0x42FC4-0x42FC8."""
        state = GameState()
        before = (state.maze_number, state.maze_stride,
                  state.treas_mazerand_num, state.treas_mazerand_adder)
        assert before == (5, 0, 104, 0)

        ee.eeprom_validate_rotation(state)
        assert (state.maze_number, state.maze_stride,
                state.treas_mazerand_num, state.treas_mazerand_adder) == before

    @pytest.mark.parametrize("value", [0, 1, 4, -3, 117, 500])
    def test_an_out_of_range_resume_position_falls_back_to_five(self, value):
        """0x43002-0x4301C: below 5, or naming no maze record, resets to 5.
        The ROM's upper guard indexes the Slapstic pointer table and rejects a
        zero entry; all 117 shipped mazes have one, so the range check is its
        ROM-free equivalent."""
        state = GameState(maze_number=value)
        ee.eeprom_validate_rotation(state)
        assert state.maze_number == ee.MAZE_NUMBER_DEFAULT

    @pytest.mark.parametrize("value", [5, 6, 50, 101, 116])
    def test_a_valid_resume_position_survives(self, value):
        state = GameState(maze_number=value)
        ee.eeprom_validate_rotation(state)
        assert state.maze_number == value

    def test_the_stride_is_masked_to_three_bits(self):
        for value in range(0, 40):
            state = GameState(maze_stride=value)
            ee.eeprom_validate_rotation(state)
            assert state.maze_stride == value & 0x07

    @pytest.mark.parametrize("value", [0, 103, 115, 200, -1])
    def test_an_out_of_range_treasure_maze_falls_back_to_104(self, value):
        state = GameState(treas_mazerand_num=value)
        ee.eeprom_validate_rotation(state)
        assert state.treas_mazerand_num == ee.TREASURE_MAZE_DEFAULT

    @pytest.mark.parametrize("value", [104, 109, 114])
    def test_a_valid_treasure_maze_survives(self, value):
        state = GameState(treas_mazerand_num=value)
        ee.eeprom_validate_rotation(state)
        assert state.treas_mazerand_num == value

    def test_the_treasure_stride_is_masked_to_two_bits(self):
        for value in range(0, 20):
            state = GameState(treas_mazerand_adder=value)
            ee.eeprom_validate_rotation(state)
            assert state.treas_mazerand_adder == value & 0x03

    def test_validation_runs_even_when_there_is_no_save_file(self, tmp_path):
        """The config read is unconditional in the ROM, so a state built with
        a nonsense rotation is clamped at boot whether or not a file exists."""
        state = GameState(
            eeprom_save_path=str(tmp_path / "missing.json"),
            maze_number=999, maze_stride=0x1F,
            treas_mazerand_num=7, treas_mazerand_adder=0x1F,
        )
        ee.eeprom_load_settings(state)
        assert (state.maze_number, state.maze_stride,
                state.treas_mazerand_num, state.treas_mazerand_adder) == (5, 7, 104, 3)


class TestRotationPersistence:
    def _rotated(self, tmp_path):
        state = GameState(eeprom_save_path=str(tmp_path / "eeprom.json"))
        state.maze_number = 47
        state.maze_stride = 3
        state.treas_mazerand_num = 110
        state.treas_mazerand_adder = 2
        return state

    def test_save_and_reload_round_trips_the_rotation(self, tmp_path):
        writer = self._rotated(tmp_path)
        ee.eeprom_save_settings(writer)

        reader = GameState(eeprom_save_path=str(tmp_path / "eeprom.json"))
        ee.eeprom_load_settings(reader)

        assert (reader.maze_number, reader.maze_stride,
                reader.treas_mazerand_num, reader.treas_mazerand_adder) == (47, 3, 110, 2)

    def test_a_file_without_a_rotation_block_keeps_the_defaults(self, tmp_path):
        """The settings-only and settings+scores files this module used to
        write must still load."""
        save_path = tmp_path / "eeprom.json"
        save_path.write_text('{"game_settings": 57488}')

        state = GameState(eeprom_save_path=str(save_path))
        ee.eeprom_load_settings(state)

        assert state.game_settings == 57488
        assert (state.maze_number, state.maze_stride,
                state.treas_mazerand_num, state.treas_mazerand_adder) == (5, 0, 104, 0)

    @pytest.mark.parametrize("payload", [
        '{"game_settings": 0, "rotation": []}',
        '{"game_settings": 0, "rotation": "nope"}',
        '{"game_settings": 0, "rotation": {"maze_number": 9}}',
        '{"game_settings": 0, "rotation": {"maze_number": "9", "maze_stride": 0,'
        ' "treas_mazerand_num": 104, "treas_mazerand_adder": 0}}',
    ])
    def test_a_malformed_rotation_block_falls_back_to_the_defaults(self, tmp_path, payload):
        save_path = tmp_path / "eeprom.json"
        save_path.write_text(payload)

        state = GameState(eeprom_save_path=str(save_path))
        ee.eeprom_load_settings(state)

        assert (state.maze_number, state.maze_stride,
                state.treas_mazerand_num, state.treas_mazerand_adder) == (5, 0, 104, 0)

    def test_an_out_of_range_value_is_not_written_out(self, tmp_path):
        """``eeprom_load_config`` would clamp it on the next power-up anyway,
        so storing it would only be a lie that survives one power cycle."""
        state = GameState(eeprom_save_path=str(tmp_path / "eeprom.json"))
        state.maze_number = 4
        state.treas_mazerand_num = 200
        state.maze_stride = 0xFF
        ee.eeprom_save_settings(state)

        stored = json.loads((tmp_path / "eeprom.json").read_text())["rotation"]
        assert stored == {
            "maze_number": 5, "maze_stride": 7,
            "treas_mazerand_num": 104, "treas_mazerand_adder": 0,
        }

    def test_the_saved_block_names_the_four_documented_words(self, tmp_path):
        state = self._rotated(tmp_path)
        ee.eeprom_save_settings(state)

        stored = json.loads((tmp_path / "eeprom.json").read_text())["rotation"]
        assert sorted(stored) == sorted(ee._ROTATION_FIELDS)


class TestRotationChangeDetection:
    def test_an_advanced_rotation_is_flushed(self, tmp_path):
        """WP-15 advances the resume position as a lap wraps; that is cabinet
        state and has to outlive the power switch."""
        save_path = tmp_path / "eeprom.json"
        state = GameState(eeprom_save_path=str(save_path), eeprom_write_timer=1)
        state.eeprom_settings_cache = state.game_settings
        state.maze_number = 63

        ee.eeprom_periodic_write(state)

        assert save_path.exists()
        reader = GameState(eeprom_save_path=str(save_path))
        ee.eeprom_load_settings(reader)
        assert reader.maze_number == 63

    @pytest.mark.parametrize("field,value", [
        ("maze_number", 40), ("maze_stride", 5),
        ("treas_mazerand_num", 111), ("treas_mazerand_adder", 3),
    ])
    def test_each_word_alone_is_enough_to_trigger_a_flush(self, tmp_path, field, value):
        """The ROM compares all four against separate cache bytes at
        0x904B8E-0x904B91 (0x4320C-0x4324E); missing any one would strand it."""
        save_path = tmp_path / "eeprom.json"
        state = GameState(eeprom_save_path=str(save_path), eeprom_write_timer=1)
        state.eeprom_settings_cache = state.game_settings
        setattr(state, field, value)

        ee.eeprom_periodic_write(state)

        reader = GameState(eeprom_save_path=str(save_path))
        ee.eeprom_load_settings(reader)
        assert getattr(reader, field) == value

    def test_an_unchanged_rotation_is_not_rewritten(self, tmp_path, monkeypatch):
        save_path = tmp_path / "eeprom.json"
        state = GameState(eeprom_save_path=str(save_path), eeprom_write_timer=1)
        state.maze_number = 30
        ee.eeprom_periodic_write(state)
        assert save_path.exists()

        flushes = []
        monkeypatch.setattr(ee, "eeprom_save_settings", lambda s: flushes.append(s))
        state.eeprom_write_timer = 1
        ee.eeprom_periodic_write(state)
        assert flushes == []

    def test_a_wrapped_lap_lands_on_the_very_next_frame(self, tmp_path):
        """``maze_checknum`` sets ``eeprom_write_timer = 1`` when the rotation
        wraps past 101 (exits.py, ROM 0x52E4C) -- a line that only became
        meaningful once these fields were in the saved image."""
        from gauntpy.subsystems.exits import maze_checknum

        save_path = tmp_path / "eeprom.json"
        state = GameState(eeprom_save_path=str(save_path))
        state.eeprom_settings_cache = state.game_settings
        state.maze_next = 200                       # past the live range

        maze_checknum(state)
        assert state.eeprom_write_timer == 1
        assert state.maze_next == ee.MAZE_NUMBER_DEFAULT

        state.maze_number = 77                      # the lap moved the cabinet on
        ee.eeprom_periodic_write(state)

        reader = GameState(eeprom_save_path=str(save_path))
        ee.eeprom_load_settings(reader)
        assert reader.maze_number == 77


def test_the_boot_handshake_restores_the_rotation_too(tmp_path):
    from gauntpy.subsystems.boot import one_time_init

    save_path = tmp_path / "eeprom.json"
    writer = GameState(eeprom_save_path=str(save_path))
    writer.maze_number = 88
    writer.maze_stride = 6
    writer.treas_mazerand_num = 112
    writer.treas_mazerand_adder = 1
    ee.eeprom_save_settings(writer)

    booted = GameState(eeprom_save_path=str(save_path))
    one_time_init(booted)

    assert (booted.maze_number, booted.maze_stride,
            booted.treas_mazerand_num, booted.treas_mazerand_adder) == (88, 6, 112, 1)
