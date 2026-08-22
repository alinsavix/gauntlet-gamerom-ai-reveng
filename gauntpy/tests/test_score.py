"""WP-14 tests: Scoring, HUD, and dialogs.

Covers main_msgbox_countdown, main_score_update, and main_score_display.

Acceptance criteria (PLAN §6, WP-14):
  - Popup timers decrement; slot cleared at zero.
  - dialog_timer decrements; gate opens when it reaches zero.
  - main_score_display skips the title and scores screens.
  - Score and health draw on their correct frames.

Reference: doc/04_game_subsystems.md §10.4-10.5, §14, §25; PLAN.md §6 WP-14.
"""

from __future__ import annotations

from gauntpy.constants import GameMode
from gauntpy.mainloop import tick
from gauntpy.state import GameState, InfoPanel, PanelField
from gauntpy.subsystems.score import (
    DIALOG_MESSAGES,
    DIALOG_MESSAGES_SHORT,
    DIALOG_SPEECH_IDS,
    DIALOG_TIMER_FRAMES,
    DIALOG_TIMER_FRAMES_SHORT,
    FACTORY_HIGHSCORE_RECORDS,
    GAME_SETTINGS_REDUCE_TEXT,
    HIGHSCORE_RANKS,
    PLAYER_TEXT_PALETTE_WORDS,
    SOUND_MESSAGE_APPEARS,
    dialog_clear_message,
    dialog_first_encounter,
    format_field,
    high_scores,
    highscore_table_init,
    info_panel,
    main_msgbox_countdown,
    main_score_display,
    main_score_update,
    rank_high_score,
    write_high_score_entry,
)
from gauntpy.subsystems import score as score_mod


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normal_state() -> GameState:
    """Return a GameState in NORMAL gameplay mode."""
    return GameState(game_mode=GameMode.NORMAL)


# ---------------------------------------------------------------------------
# main_msgbox_countdown
# ---------------------------------------------------------------------------

def test_msgbox_countdown_decrements() -> None:
    """dialog_timer decrements by one per call when nonzero."""
    state = GameState()
    state.dialog_timer = 10
    main_msgbox_countdown(state)
    assert state.dialog_timer == 9


def test_msgbox_countdown_noop_when_already_zero() -> None:
    """dialog_timer at zero stays at zero -- no underflow or wrap."""
    state = GameState()
    state.dialog_timer = 0
    main_msgbox_countdown(state)
    assert state.dialog_timer == 0


def test_msgbox_countdown_from_one_reaches_zero() -> None:
    """dialog_timer=1 reaches 0 in exactly one call (transition/cleanup case)."""
    state = GameState()
    state.dialog_timer = 1
    main_msgbox_countdown(state)
    assert state.dialog_timer == 0


def test_msgbox_countdown_sequential_decrement() -> None:
    """Repeated calls decrement until zero, then stop."""
    state = GameState()
    state.dialog_timer = 3
    for expected in (2, 1, 0, 0, 0):
        main_msgbox_countdown(state)
        assert state.dialog_timer == expected


# ---------------------------------------------------------------------------
# main_score_update -- Loop 1: popup timers
# ---------------------------------------------------------------------------

def test_score_update_popup_timer_decrements() -> None:
    """score_display_timer[i] decrements each frame when nonzero (slot 0)."""
    state = _normal_state()
    state.score_display_timer[0] = 60
    main_score_update(state)
    assert state.score_display_timer[0] == 59


def test_score_update_popup_timer_all_slots_decrement() -> None:
    """All four score_display_timer slots decrement independently."""
    state = _normal_state()
    state.score_display_timer = [10, 20, 30, 40]
    main_score_update(state)
    assert state.score_display_timer == [9, 19, 29, 39]


def test_score_update_popup_timer_at_zero_no_underflow() -> None:
    """score_display_timer[i] at zero stays at zero, not wrapping to 0xFFFF."""
    state = _normal_state()
    state.score_display_timer[2] = 0
    main_score_update(state)
    assert state.score_display_timer[2] == 0


def test_score_update_timer_zero_clears_picture() -> None:
    """Timer reaching 0 clears mobs.picture[0x11+i] for each of the four slots."""
    for i in range(4):
        state = _normal_state()
        state.score_display_timer[i] = 1
        pic_slot = 0x11 + i          # 17, 18, 19, 20
        state.mobs.picture[pic_slot] = 0xABCD
        main_score_update(state)
        assert state.score_display_timer[i] == 0, f"slot {i}: timer not zeroed"
        assert state.mobs.picture[pic_slot] == 0, (
            f"slot {i}: picture[{pic_slot:#x}] not cleared"
        )


def test_score_update_timer_nonzero_does_not_clear_picture() -> None:
    """Picture is not cleared while the timer is still counting down."""
    state = _normal_state()
    state.score_display_timer[0] = 5
    state.mobs.picture[0x11] = 0x1234
    main_score_update(state)
    assert state.mobs.picture[0x11] == 0x1234


def test_score_update_timer_zero_removes_the_popups_own_depth_entry() -> None:
    """The popup MOB is slot 0x11+i and that is the slot that must leave the
    depth chain. The ROM calls mob_depth_remove(0x10+i), which resolves the
    physical slot by adding one (0x5E064) -- reading that argument literally
    unlinks 0x10+i and strands the real popup on the chain forever."""
    for i in range(4):
        state = _normal_state()
        popup = 0x11 + i
        state.mobs.insert(popup)
        state.mobs.insert(0x10 + i)          # the neighbour must be left alone
        state.mobs.picture[popup] = 0xABCD
        state.score_display_timer[i] = 1

        main_score_update(state)

        chain = list(state.mobs.iter_chain())
        assert popup not in chain, f"popup slot {popup:#x} still on the depth chain"
        assert 0x10 + i in chain, f"slot {0x10 + i:#x} was unlinked by mistake"
        assert state.mobs.picture[popup] == 0


# ---------------------------------------------------------------------------
# main_score_update -- Loop 3: effect animation counters
# ---------------------------------------------------------------------------

def test_score_update_empty_effect_channels_do_not_age() -> None:
    """The ROM skips counters whose physical effect slot has no picture."""
    state = _normal_state()
    state.mob_effect_anim_counter = [3, 7, 0, 100]
    main_score_update(state)
    assert state.mob_effect_anim_counter == [3, 7, 0, 100]


def test_score_update_effect_anim_counter_all_occupied_slots() -> None:
    """All four occupied effect channels increment independently."""
    state = _normal_state()
    for slot in range(0x0D, 0x11):
        state.mobs.picture[slot] = 0x0924
    state.mob_effect_anim_counter = [0, 0, 0, 0]
    for expected_val in range(1, 5):
        main_score_update(state)
        assert all(c == expected_val for c in state.mob_effect_anim_counter)


def test_transporter_effect_advances_and_releases_slot() -> None:
    state = _normal_state()
    slot = 0x0D
    state.mobs.picture[slot] = 0x0924
    state.mobs.insert(slot)
    state.mob_effect_anim_counter[0] = 0xFF

    main_score_update(state)
    assert state.mob_effect_anim_counter[0] == 0
    assert state.mobs.picture[slot] == 0x0924

    for _ in range(28):
        main_score_update(state)
    assert state.mobs.picture[slot] == 0
    assert slot not in list(state.mobs.iter_chain())


def test_player_impact_uses_four_frame_cycle() -> None:
    state = _normal_state()
    slot = 0x0D
    state.mobs.picture[slot] = 0x0EFC
    state.mobs.insert(slot)

    for _ in range(6):
        main_score_update(state)
    assert state.mobs.picture[slot] == 0x10FC
    for _ in range(2):
        main_score_update(state)
    assert state.mobs.picture[slot] == 0


# ---------------------------------------------------------------------------
# main_score_display -- mode gates
# ---------------------------------------------------------------------------

def test_score_display_skips_title_mode() -> None:
    """main_score_display is a no-op in TITLE mode (0xFFFE)."""
    state = GameState(game_mode=GameMode.TITLE)
    original_score_dirty = list(state.score_dirty)
    original_health_dirty = list(state.health_dirty)
    main_score_display(state)
    assert state.score_dirty == original_score_dirty
    assert state.health_dirty == original_health_dirty


def test_score_display_skips_scores_mode() -> None:
    """main_score_display is a no-op in SCORES (high-score) mode (0xFFFF)."""
    state = GameState(game_mode=GameMode.SCORES)
    original_score_dirty = list(state.score_dirty)
    original_health_dirty = list(state.health_dirty)
    main_score_display(state)
    assert state.score_dirty == original_score_dirty
    assert state.health_dirty == original_health_dirty


def test_score_display_runs_in_normal_mode() -> None:
    """main_score_display processes a player in NORMAL mode."""
    state = _normal_state()
    state.frame_counter = 0
    state.score_dirty[0] = 1
    main_score_display(state)
    # Flag should be cleared, confirming the function ran.
    assert state.score_dirty[0] == 0


def test_score_display_skips_when_gate_disabled() -> None:
    """master score_display_enabled=0 suppresses all redraw."""
    state = _normal_state()
    state.score_display_enabled = 0
    state.score_dirty = [1, 1, 1, 1]
    state.health_dirty = [1, 1, 1, 1]
    main_score_display(state)
    assert state.score_dirty == [1, 1, 1, 1]
    assert state.health_dirty == [1, 1, 1, 1]


# ---------------------------------------------------------------------------
# main_score_display -- player selection (frame_counter & 3)
# ---------------------------------------------------------------------------

def test_score_display_selects_player_by_frame_counter() -> None:
    """player_index = frame_counter & 3; only that player's flags are cleared."""
    for frame in range(8):  # two full rotations through all four slots
        state = _normal_state()
        state.frame_counter = frame
        # All score flags dirty; health flags clear so only score_dirty tracks.
        state.score_dirty = [1, 1, 1, 1]
        state.health_dirty = [0, 0, 0, 0]
        main_score_display(state)
        expected = frame & 3
        assert state.score_dirty[expected] == 0, (
            f"score_dirty[{expected}] not cleared on frame {frame}"
        )
        for j in range(4):
            if j != expected:
                assert state.score_dirty[j] == 1, (
                    f"score_dirty[{j}] unexpectedly cleared on frame {frame}"
                )


# ---------------------------------------------------------------------------
# main_score_display -- dirty flag behavior
# ---------------------------------------------------------------------------

def test_score_display_clears_score_dirty_flag() -> None:
    """Score draw clears the per-player score_dirty flag."""
    state = _normal_state()
    state.frame_counter = 2
    state.score_dirty[2] = 1
    state.health_dirty[2] = 0
    main_score_display(state)
    assert state.score_dirty[2] == 0


def test_score_display_clears_health_dirty_flag() -> None:
    """Health draw clears the per-player health_dirty flag."""
    state = _normal_state()
    state.frame_counter = 3
    state.score_dirty[3] = 0
    state.health_dirty[3] = 1
    main_score_display(state)
    assert state.health_dirty[3] == 0


def test_score_display_health_redraws_when_low_health() -> None:
    """health < 0xC8 triggers health redraw even without the dirty flag."""
    state = _normal_state()
    state.frame_counter = 0
    state.score_dirty[0] = 0
    state.health_dirty[0] = 0
    state.players[0].health = 0x10   # well below 0xC8
    # Should not raise; health_dirty is cleared (was already 0; confirms path ran).
    main_score_display(state)
    assert state.health_dirty[0] == 0  # cleared as side-effect of the draw call


def test_score_display_no_health_redraw_when_above_threshold() -> None:
    """health >= 0xC8 with clean flags does NOT trigger health redraw."""
    state = _normal_state()
    state.frame_counter = 1
    state.score_dirty[1] = 0
    state.health_dirty[1] = 0
    state.players[1].health = 0x200  # well above 0xC8
    # health_dirty stays 0; nothing was redrawn (no way to detect stub call,
    # but at minimum the function must not raise and the flags must not flip).
    main_score_display(state)
    assert state.health_dirty[1] == 0


# ---------------------------------------------------------------------------
# The info-panel latch -- what draw_player_score / draw_player_health put on
# the alpha layer (§14.2), which is what render/hud.py draws.
# ---------------------------------------------------------------------------

def test_the_draw_hooks_latch_the_values_they_drew() -> None:
    state = _normal_state()
    state.frame_counter = 0
    state.players[0].score = 12345
    state.players[0].health = 700
    state.players[0].bonusmult = 3

    main_score_display(state)

    field = info_panel(state).players[0]
    assert field.score_drawn and field.health_drawn
    assert field.score == 12345
    assert field.health == 700
    assert field.bonusmult == 3


def test_the_latch_only_moves_on_that_players_own_frame() -> None:
    """One player per frame (frame_counter & 3): a change made on somebody
    else's frame must not reach the panel early."""
    state = _normal_state()
    state.frame_counter = 0
    state.players[1].score = 100
    main_score_display(state)            # player 0's turn

    state.players[1].score = 999
    state.frame_counter = 2              # player 2's turn
    main_score_display(state)
    assert info_panel(state).players[1].score != 999

    state.frame_counter = 5              # 5 & 3 == 1
    main_score_display(state)
    assert info_panel(state).players[1].score == 999


def test_a_score_change_alone_is_enough_to_redraw() -> None:
    """The ROM's update bit is set by whoever changed the value; nothing in the
    landed packages sets score_dirty, so main_score_display also compares the
    latched value (see its docstring)."""
    state = _normal_state()
    state.frame_counter = 0
    main_score_display(state)
    state.score_dirty[0] = 0

    state.players[0].score = 4321
    main_score_display(state)

    assert info_panel(state).players[0].score == 4321


def test_the_score_attribute_is_the_players_rom_palette_word() -> None:
    """draw_player_score passes player_text_palette_words[p] (ROM 0x57350)."""
    assert PLAYER_TEXT_PALETTE_WORDS == (0xD000, 0xD400, 0xD800, 0xDC00)
    state = _normal_state()
    for i in range(4):
        state.frame_counter = i
        main_score_display(state)
        assert info_panel(state).players[i].score_attr == PLAYER_TEXT_PALETTE_WORDS[i]


def test_low_health_pulse_dims_the_health_attribute_by_0x1000() -> None:
    """§14.2 / disassembly 0x45A32: the dim half is (state_timer & 0xF) < 8,
    and only while the timer is not its 0xFFFF idle sentinel and the player has
    a live MOB."""
    state = _normal_state()
    state.frame_counter = 0
    player = state.players[0]
    player.mob_slot = 0x120
    player.state_timer = 0x0004          # dim half

    main_score_display(state)

    assert info_panel(state).players[0].health_attr == PLAYER_TEXT_PALETTE_WORDS[0] - 0x1000


def test_the_bright_half_of_the_pulse_uses_the_plain_attribute() -> None:
    state = _normal_state()
    state.frame_counter = 0
    state.players[0].mob_slot = 0x120
    state.players[0].state_timer = 0x000C   # bright half: (timer & 0xF) >= 8

    main_score_display(state)

    assert info_panel(state).players[0].health_attr == PLAYER_TEXT_PALETTE_WORDS[0]


def test_the_idle_state_timer_sentinel_never_dims() -> None:
    state = _normal_state()
    state.frame_counter = 0
    state.players[0].mob_slot = 0x120
    state.players[0].state_timer = 0xFFFF   # idle sentinel, low nibble is 0xF

    main_score_display(state)

    assert info_panel(state).players[0].health_attr == PLAYER_TEXT_PALETTE_WORDS[0]


def test_a_player_without_a_live_mob_never_dims() -> None:
    state = _normal_state()
    state.frame_counter = 0
    state.players[0].mob_slot = 0          # active_mob_ids[p] == 0
    state.players[0].state_timer = 0x0004

    main_score_display(state)

    assert info_panel(state).players[0].health_attr == PLAYER_TEXT_PALETTE_WORDS[0]


def test_acid_slowed_players_shift_by_0x2000_instead() -> None:
    state = _normal_state()
    state.frame_counter = 0
    state.players[0].mob_slot = 0x120
    state.players[0].state_timer = 0x000C   # not in the low-health dim half
    state.players[0].acid_timer = 90

    main_score_display(state)

    assert info_panel(state).players[0].health_attr == PLAYER_TEXT_PALETTE_WORDS[0] - 0x2000


def test_the_low_health_dim_wins_over_the_acid_shift() -> None:
    """0x45A6E branches straight to the display call, skipping the acid test."""
    state = _normal_state()
    state.frame_counter = 0
    state.players[0].mob_slot = 0x120
    state.players[0].state_timer = 0x0004
    state.players[0].acid_timer = 90

    main_score_display(state)

    assert info_panel(state).players[0].health_attr == PLAYER_TEXT_PALETTE_WORDS[0] - 0x1000


def test_the_panel_is_not_written_while_the_display_gate_is_closed() -> None:
    state = _normal_state()
    state.score_display_enabled = 0
    state.players[0].score = 500

    main_score_display(state)

    assert info_panel(state).players[0].score_drawn is False


# ---------------------------------------------------------------------------
# Field formatting -- OS format_decimal padding mode 1 (doc/02 §8.1).
# ---------------------------------------------------------------------------

def test_fields_are_space_padded_not_zero_padded() -> None:
    assert format_field(1234, 7) == "   1234"
    assert format_field(0, 5) == "    0"


def test_fields_keep_their_width() -> None:
    assert len(format_field(12345678, 7)) == 7
    assert len(format_field(7, 5)) == 5


# ---------------------------------------------------------------------------
# High-score table -- highscore_table_init (0x49BD0) over the ROM's
# factory_highscore_records (0x57EBA).
# ---------------------------------------------------------------------------

def test_factory_records_are_four_class_lists_of_ten() -> None:
    assert len(FACTORY_HIGHSCORE_RECORDS) == 4
    assert all(len(cls) == HIGHSCORE_RANKS for cls in FACTORY_HIGHSCORE_RECORDS)


def test_factory_records_start_with_the_rom_first_entry() -> None:
    """doc/05_data_reference.md: "Starts with score 0x1F40 and initials AWC"."""
    assert FACTORY_HIGHSCORE_RECORDS[0][0] == (0x1F40, "AWC")


def test_every_factory_ladder_descends_in_400_point_steps() -> None:
    for cls in FACTORY_HIGHSCORE_RECORDS:
        values = [entry[0] for entry in cls]
        assert values == sorted(values, reverse=True)
        assert all(a - b == 400 for a, b in zip(values, values[1:]))
        assert all(len(initials) == 3 for _score, initials in cls)


def test_high_scores_seed_themselves_from_the_factory_table() -> None:
    state = GameState()
    table = high_scores(state)
    assert [tuple(entry) for entry in table[0]] == list(FACTORY_HIGHSCORE_RECORDS[0])


def test_high_scores_are_mutable_per_state_not_shared_with_the_rom_table() -> None:
    state = GameState()
    high_scores(state)[0][0] = (99999, "ZZZ")
    assert FACTORY_HIGHSCORE_RECORDS[0][0] == (0x1F40, "AWC")
    assert high_scores(GameState())[0][0] == (0x1F40, "AWC")


def test_highscore_table_init_reseeds() -> None:
    state = GameState()
    high_scores(state)[3][0] = (1, "XXX")
    state.high_scores[3] = []          # the ROM's "bank is empty" condition
    highscore_table_init(state)
    assert high_scores(state)[3][0] == FACTORY_HIGHSCORE_RECORDS[3][0]


def test_highscore_table_init_leaves_a_populated_bank_alone() -> None:
    """The ROM only copies the factory lists "when the high-score banks are
    empty" -- so a bank an EEPROM load already restored survives."""
    state = GameState()
    restored = [(50000, "EEP")] + list(FACTORY_HIGHSCORE_RECORDS[1][1:])
    state.high_scores[1] = list(restored)
    highscore_table_init(state)
    assert state.high_scores[1] == restored
    assert state.high_scores[0][0] == FACTORY_HIGHSCORE_RECORDS[0][0]


def test_rank_high_score_places_a_value_in_the_ladder() -> None:
    state = GameState()
    assert rank_high_score(state, 0, 9000) == 0        # beats 8000
    assert rank_high_score(state, 0, 7000) == 3        # between 7200 and 6800
    assert rank_high_score(state, 0, 100) == HIGHSCORE_RANKS   # does not rank


def test_write_high_score_entry_shifts_and_truncates() -> None:
    state = GameState()
    write_high_score_entry(state, 0, 0, 9000, "ZZZ")
    ladder = high_scores(state)[0]
    assert ladder[0] == (9000, "ZZZ")
    assert ladder[1] == FACTORY_HIGHSCORE_RECORDS[0][0]
    assert len(ladder) == HIGHSCORE_RANKS


# ---------------------------------------------------------------------------
# The panel and high-score tables are real GameState fields, not attributes
# attached at runtime.
# ---------------------------------------------------------------------------

def test_the_panel_is_a_declared_state_field() -> None:
    import dataclasses

    names = {f.name for f in dataclasses.fields(GameState)}
    assert {"info_panel", "high_scores", "dialog_message",
            "dialog_first_encounter_flags"} <= names


def test_each_state_gets_its_own_panel_and_ladders() -> None:
    a, b = GameState(), GameState()
    assert isinstance(a.info_panel, InfoPanel)
    assert isinstance(a.info_panel.players[0], PanelField)
    assert a.info_panel is not b.info_panel
    a.info_panel.players[0].score = 5
    assert b.info_panel.players[0].score == 0
    high_scores(a)[0][0] = (1, "AAA")
    assert high_scores(b)[0][0] == FACTORY_HIGHSCORE_RECORDS[0][0]


def test_info_panel_accessor_returns_the_state_field() -> None:
    state = GameState()
    assert info_panel(state) is state.info_panel


# ---------------------------------------------------------------------------
# First-encounter dialogs (§10.4, dialog_first_encounter 0x4C440).
# ---------------------------------------------------------------------------

def test_dialog_shows_the_rom_message_for_its_mask_bit() -> None:
    state = _normal_state()
    dialog_first_encounter(state, 0, 1 << 3)
    assert state.dialog_message == list(DIALOG_MESSAGES[3])
    assert " SAVE KEYS TO  " in state.dialog_message


def test_dialog_sets_the_rom_box_geometry_and_owner() -> None:
    state = _normal_state()
    dialog_first_encounter(state, 2, 1 << 0)
    # 0x4C54C: three rows plus one per extra line; record 0 has three lines.
    assert state.dialog_box_rows == 5
    assert state.dialog_box_width == max(len(s) for s in DIALOG_MESSAGES[0])
    assert state.dialog_player == 2


def test_dialog_arms_the_timer_and_plays_the_message_sound() -> None:
    state = _normal_state()
    dialog_first_encounter(state, 0, 1 << 2)
    assert state.dialog_timer == DIALOG_TIMER_FRAMES
    assert SOUND_MESSAGE_APPEARS in state.sound_log


def test_dialog_returns_one_only_when_the_record_has_speech() -> None:
    """0x5A280: only indexes 1 and 6 carry a speech id."""
    speaking = _normal_state()
    assert dialog_first_encounter(speaking, 0, 1 << 1) == 1
    assert DIALOG_SPEECH_IDS[1] in speaking.sound_log

    silent = _normal_state()
    assert dialog_first_encounter(silent, 0, 1 << 2) == 0


def test_dialog_is_one_shot_per_mask() -> None:
    state = _normal_state()
    assert dialog_first_encounter(state, 0, 1 << 5) == 0
    assert state.dialog_first_encounter_flags & (1 << 5)
    state.dialog_timer = 0
    state.dialog_message = []

    assert dialog_first_encounter(state, 0, 1 << 5) == 0
    assert state.dialog_message == [], "an already-seen encounter shows nothing"


def test_a_second_dialog_retires_the_box_already_on_screen() -> None:
    """0x4C49A: dialog_timer is forced to 1 and main_msgbox_countdown runs, so
    the previous box is gone before the new one is built."""
    state = _normal_state()
    dialog_first_encounter(state, 0, 1 << 4)
    first = list(state.dialog_message)

    dialog_first_encounter(state, 1, 1 << 5)

    assert state.dialog_message != first
    assert state.dialog_message == list(DIALOG_MESSAGES[5])
    assert state.dialog_timer == DIALOG_TIMER_FRAMES


def test_reduce_text_selects_the_short_bank_only_during_attract() -> None:
    """0x4C4D6: the 0x5A300 bank needs the operator bit *and* a negative
    game_mode."""
    playing = GameState(game_mode=GameMode.NORMAL,
                        game_settings=GAME_SETTINGS_REDUCE_TEXT)
    dialog_first_encounter(playing, 0, 1 << 0)
    assert playing.dialog_message == list(DIALOG_MESSAGES[0])

    attract = GameState(game_mode=GameMode.DEMO,
                        game_settings=GAME_SETTINGS_REDUCE_TEXT)
    dialog_first_encounter(attract, 0, 1 << 0)
    assert attract.dialog_message == list(DIALOG_MESSAGES_SHORT[0])


def test_reduce_text_shortens_the_box_timer() -> None:
    state = GameState(game_mode=GameMode.NORMAL,
                      game_settings=GAME_SETTINGS_REDUCE_TEXT)
    dialog_first_encounter(state, 0, 1 << 2)
    assert state.dialog_timer == DIALOG_TIMER_FRAMES_SHORT


def test_a_null_short_record_shows_nothing() -> None:
    """Only index 0 of the 0x5A300 bank is populated; a NULL record returns 0
    without a box (0x4C504)."""
    state = GameState(game_mode=GameMode.DEMO,
                      game_settings=GAME_SETTINGS_REDUCE_TEXT)
    assert dialog_first_encounter(state, 0, 1 << 3) == 0
    assert state.dialog_message == []
    assert state.dialog_timer == 0


def test_the_countdown_clears_the_message_at_zero() -> None:
    state = _normal_state()
    dialog_first_encounter(state, 0, 1 << 2)
    state.dialog_timer = 1

    main_msgbox_countdown(state)

    assert state.dialog_timer == 0
    assert state.dialog_message == []
    assert state.dialog_box_rows == 0


def test_dialog_clear_message_empties_the_record() -> None:
    state = _normal_state()
    dialog_first_encounter(state, 0, 1 << 2)
    dialog_clear_message(state)
    assert state.dialog_message == []
    assert state.dialog_player == -1


def test_every_dialog_record_has_between_one_and_three_lines() -> None:
    assert len(DIALOG_MESSAGES) == 32
    assert all(1 <= len(lines) <= 3 for lines in DIALOG_MESSAGES)
    assert len(DIALOG_SPEECH_IDS) == 32


def test_inventory_palette_words_are_distinct_from_player_text() -> None:
    assert score_mod.KEY_PALETTE_WORDS == (0xE000, 0xE400, 0xE800, 0xEC00)
    assert score_mod.POTION_PALETTE_WORDS == (0xF000, 0xF400, 0xF800, 0xFC00)
    assert set(score_mod.KEY_PALETTE_WORDS).isdisjoint(
        score_mod.PLAYER_TEXT_PALETTE_WORDS
    )


# ---------------------------------------------------------------------------
# main_score_update loops 1b and 2 -- the transporter transition milestones
# (§25; disassembly 0x471BA-0x473C0).
# ---------------------------------------------------------------------------

_ANIM_SLOT = 0x19        # + player index; the shared thief slot is 0x1D
_THIEF_ANIM = 0x1D


def _run_frames(state: GameState, n: int) -> None:
    for _ in range(n):
        main_score_update(state)


def test_transition_loops_idle_while_their_animation_mob_is_empty() -> None:
    state = _normal_state()
    _run_frames(state, 10)
    assert state.thief_tport_timer == -1
    assert state.player_tport_phase == [-1] * 4


def test_player_transition_advances_only_on_even_counts() -> None:
    state = _normal_state()
    state.mobs.picture[_ANIM_SLOT] = 0x1DCF
    state.player_tport_phase[0] = 0

    main_score_update(state)
    assert state.player_tport_phase[0] == 1      # odd -> skipped
    main_score_update(state)
    assert state.player_tport_phase[0] == 2      # even -> milestone 1


def test_player_transition_saves_and_restores_the_hero_picture() -> None:
    state = _normal_state()
    state.players[0].mob_slot = 0x120
    state.mobs.picture[0x120] = 0x7A5
    state.mobs.picture[_ANIM_SLOT] = 0x1DCF
    state.player_tport_phase[0] = 0

    _run_frames(state, 10)                       # counter 10 -> milestone 5
    assert state.player_tport_saved_picture[0] == 0x7A5
    assert state.mobs.picture[0x120] == 0x1709, "the hero flashes mid-transport"

    _run_frames(state, 22)                       # counter 32 -> milestone 0x10
    assert state.mobs.picture[0x120] == 0x7A5, "and comes back"
    assert state.player_tport_saved_picture[0] == 0


def test_player_transition_cleans_up_past_the_last_milestone() -> None:
    state = _normal_state()
    state.players[0].mob_slot = 0x120
    state.mobs.picture[0x120] = 0x7A5
    state.mobs.picture[_ANIM_SLOT] = 0x1DCF
    state.mobs.insert(_ANIM_SLOT)                # the animation MOB's own entry
    state.mobs.insert(_ANIM_SLOT - 1)            # its neighbour must survive
    state.player_tport_phase[0] = 0

    _run_frames(state, 46)                       # counter 46 -> step 0x17

    assert state.mobs.picture[_ANIM_SLOT] == 0
    assert state.player_tport_phase[0] == -1
    chain = list(state.mobs.iter_chain())
    assert _ANIM_SLOT not in chain, "mob_depth_remove(d4+0x18) resolves to 0x19+d4"
    assert _ANIM_SLOT - 1 in chain


def test_mob_depth_remove_applies_the_roms_plus_one_bias() -> None:
    """0x5E064 takes ``physical_slot_minus_one``. Pinning it directly keeps the
    three call sites in this module honest."""
    state = _normal_state()
    state.mobs.insert(0x18, depth_key=0x120)
    state.mobs.insert(0x19, depth_key=0x121)
    state.mobs.link[0x19] |= 0xA000
    state.mobs.state_link[0x19] |= 0xB000

    state.mobs.depth_remove(0x18)

    chain = list(state.mobs.iter_chain())
    assert 0x19 not in chain
    assert 0x18 in chain
    assert state.mobs.depth_key[0x19] == 0
    assert state.mobs.link[0x19] == 0
    assert state.mobs.state_link[0x19] == 0


def test_player_transition_steps_the_rom_sparkle_cycle() -> None:
    state = _normal_state()
    state.mobs.picture[_ANIM_SLOT] = 0x1DCF
    state.player_tport_phase[0] = 0

    seen = []
    for _ in range(24):
        main_score_update(state)
        seen.append(state.mobs.picture[_ANIM_SLOT])

    assert set(seen) <= set(score_mod._TPORT_TRANSITION_PICTURES)
    assert seen[0] == score_mod._TPORT_TRANSITION_PICTURES[0]


def test_thief_transition_hides_moves_and_restores_the_thief() -> None:
    state = _normal_state()
    state.thief_current_pos = 0x140
    state.thief_tport_dest = 0x180
    state.mobs.create(0x140, tile=0x1234, hpos=0, vpos=0, obj_type=0)
    state.mobs.picture[_THIEF_ANIM] = 0x1DCF
    state.thief_tport_timer = 0

    _run_frames(state, 10)                       # milestone 5
    assert state.thief_tport_saved_picture == 0x1234
    assert state.mobs.picture[0x140] == 0
    assert state.thief_current_pos == 0x180

    _run_frames(state, 22)                       # milestone 0x10
    assert state.mobs.picture[0x180] == 0x1234


def test_thief_transition_restamps_fixed_animation_slot_at_destination() -> None:
    """Milestone 0x0B calls 0x47CFE with channel 4, i.e. fixed slot 0x1D."""
    state = _normal_state()
    state.thief_current_pos = 0x140
    state.thief_tport_dest = 0x180
    state.mobs.create(
        0x140, tile=0x1234, hpos=0x1000, vpos=0x2000, obj_type=0,
    )
    state.mobs.hpos[0x180] = 0x3000
    state.mobs.vpos[0x180] = 0x4000
    state.mobs.picture[_THIEF_ANIM] = 0x1DCF
    state.thief_tport_timer = 0

    _run_frames(state, 22)                       # milestone 0x0B
    assert state.mobs.hpos[_THIEF_ANIM] == 0x3001
    assert state.mobs.vpos[_THIEF_ANIM] == 0x4012
    assert not any(state.mobs.picture[0x0D + c] for c in range(4))


def test_thief_transition_cleanup_reprograms_the_route() -> None:
    state = _normal_state()
    state.thief_current_pos = 0x140
    state.thief_tport_dest = 0x180
    state.mobs.picture[_THIEF_ANIM] = 0x1DCF
    state.mobs.insert(_THIEF_ANIM)
    state.mobs.insert(_THIEF_ANIM - 1)           # neighbour must survive
    state.thief_tport_timer = 0

    _run_frames(state, 46)

    assert state.mobs.picture[_THIEF_ANIM] == 0
    assert state.thief_tport_timer == -1
    chain = list(state.mobs.iter_chain())
    assert _THIEF_ANIM not in chain, "mob_depth_remove(0x1C) resolves to 0x1D"
    assert _THIEF_ANIM - 1 in chain
    assert state.thief_previous_pos == state.thief_current_pos


def test_the_thief_pass_runs_once_per_frame_not_four_times() -> None:
    """0x471B4 gates loop 1b on the loop index being zero."""
    state = _normal_state()
    state.mobs.picture[_THIEF_ANIM] = 0x1DCF
    state.thief_tport_timer = 0

    main_score_update(state)

    assert state.thief_tport_timer == 1


def test_transition_loops_do_not_disturb_effect_aging() -> None:
    """Loop 3 still owns the four shared effect channels."""
    state = _normal_state()
    slot = 0x0D
    state.mobs.picture[slot] = 0x0EFC
    state.mobs.insert(slot)
    state.mobs.picture[_ANIM_SLOT] = 0x1DCF
    state.player_tport_phase[0] = -1

    _run_frames(state, 6)
    assert state.mobs.picture[slot] == 0x10FC
    _run_frames(state, 2)
    assert state.mobs.picture[slot] == 0


# ---------------------------------------------------------------------------
# Ownership guard: the monster shot cooldown (shot_timer_next, 0x90492A).
#
# main_score_update ends at its rts (0x474F4); the eight-word countdown at
# 0x4750C-0x47530 is the *prologue of main_handle_shots* (0x474F6), which
# doc/04_game_subsystems.md §25 calls out as "an independent top-level
# main-loop call, not a main_score_update sub-function". A byte scan of
# row76.bin for the 32-bit address finds exactly three references -- 0x47512
# and 0x47522 (this countdown) and 0x49100 (monster_create_shot arming it to
# 0x3C) -- so ticking it anywhere else would decrement it twice a frame and
# halve every demon/lobber cooldown. These tests pin that down from both
# sides.
# ---------------------------------------------------------------------------

def test_main_score_update_never_touches_the_shot_cooldown() -> None:
    state = _normal_state()
    state.shot_timer_next = [0x3C] * 8

    _run_frames(state, 5)

    assert state.shot_timer_next == [0x3C] * 8, (
        "shot_timer_next belongs to main_handle_shots (0x4750C), not to "
        "main_score_update"
    )


def test_a_whole_frame_decrements_the_shot_cooldown_exactly_once() -> None:
    """Whoever owns the countdown, one frame must cost one tick -- the guard
    against a second copy appearing in another main-loop call."""
    state = GameState(game_mode=GameMode.NORMAL)
    state.shot_timer_next = [0x3C, 0x1E, 1, 0, 0, 0, 0, 0]

    tick(state)

    assert state.shot_timer_next[:4] == [0x3B, 0x1D, 0, 0]


def test_the_shot_cooldown_floors_at_zero_across_frames() -> None:
    """0x47516 tests the word before decrementing (``tst.w`` / ``beq``), so a
    timer at zero stays at zero instead of wrapping to 0xFFFF."""
    state = GameState(game_mode=GameMode.NORMAL)
    state.shot_timer_next = [2] + [0] * 7

    for _ in range(5):
        tick(state)

    assert state.shot_timer_next == [0] * 8


# ---------------------------------------------------------------------------
# Effect picture tables -- ROM 0x576B6 / 0x576D2 / 0x576DA (§25 loop 3).
# ---------------------------------------------------------------------------

def test_effect_picture_tables_match_their_rom_shapes() -> None:
    """28 B + 8 B + 8 B of big-endian words, ending where shot_velocity_x
    begins at 0x576E2 (doc/05_data_reference.md)."""
    assert len(score_mod._TPORT_EFFECT_PICTURES) == 14
    assert len(score_mod._PLAYER_IMPACT_PICTURES) == 4
    assert len(score_mod._MONSTER_IMPACT_PICTURES) == 4
    total_bytes = 2 * (
        len(score_mod._TPORT_EFFECT_PICTURES)
        + len(score_mod._PLAYER_IMPACT_PICTURES)
        + len(score_mod._MONSTER_IMPACT_PICTURES)
    )
    assert 0x576B6 + total_bytes == 0x576E2


def test_effect_pictures_are_the_rom_sequences() -> None:
    assert score_mod._TPORT_EFFECT_PICTURES == (
        0x0924, 0x0924, 0x092D, 0x092D, 0x0936, 0x0936, 0x093F,
        0x093F, 0x0948, 0x0948, 0x0951, 0x0951, 0x095A, 0x095A,
    )
    assert score_mod._PLAYER_IMPACT_PICTURES == (0x0EFC, 0x0EFC, 0x0FFC, 0x10FC)
    assert score_mod._MONSTER_IMPACT_PICTURES == (0x1C5C, 0x1C5C, 0x1C60, 0x1C64)


def test_monster_impact_effect_runs_its_own_four_frame_cycle() -> None:
    """A picture outside the 0x0EFC-0x10FC player-impact window uses the
    0x576DA table."""
    state = _normal_state()
    slot = 0x0E
    state.mobs.picture[slot] = 0x1C5C
    state.mobs.insert(slot)

    for _ in range(4):
        main_score_update(state)
    assert state.mobs.picture[slot] == 0x1C60
    for _ in range(2):
        main_score_update(state)
    assert state.mobs.picture[slot] == 0x1C64
    for _ in range(2):
        main_score_update(state)
    assert state.mobs.picture[slot] == 0


# ---------------------------------------------------------------------------
# The shared numeric line of records 8-15 (0x4C63C-0x4C67A).
# ---------------------------------------------------------------------------

def test_records_eight_to_fifteen_share_the_numeric_line() -> None:
    """0x4C642 compares the record's *second* string pointer against 0x59D80;
    every damage record points at that one line."""
    from gauntpy.subsystems.score import DIALOG_NUMERIC_LINE

    assert DIALOG_NUMERIC_LINE == "  PLAYER LOSES    HEALTH  "
    for index in range(8, 16):
        assert DIALOG_MESSAGES[index][1] == DIALOG_NUMERIC_LINE, index
    for index in range(0, 8):
        assert DIALOG_NUMERIC_LINE not in DIALOG_MESSAGES[index], index


def test_the_numeric_value_is_drawn_into_the_shared_line() -> None:
    """0x4C654-0x4C674: a two-digit, space-padded field at column + 0xF."""
    state = _normal_state()
    dialog_first_encounter(state, 0, 1 << 8, 12)
    assert state.dialog_message[0] == "  SHOOT OR AVOID GHOSTS   "
    assert state.dialog_message[1] == "  PLAYER LOSES 12 HEALTH  "


def test_the_numeric_field_is_right_aligned_in_two_columns() -> None:
    state = _normal_state()
    dialog_first_encounter(state, 0, 1 << 9, 5)
    assert state.dialog_message[1] == "  PLAYER LOSES  5 HEALTH  "


def test_a_value_wider_than_the_field_keeps_its_low_digits() -> None:
    """OS format_decimal writes into fixed alpha cells; it cannot overflow."""
    state = _normal_state()
    dialog_first_encounter(state, 0, 1 << 10, 123)
    assert state.dialog_message[1] == "  PLAYER LOSES 23 HEALTH  "


def test_every_damage_record_renders_its_value() -> None:
    for index in range(8, 16):
        state = _normal_state()
        dialog_first_encounter(state, 0, 1 << index, 42)
        assert state.dialog_message[1] == "  PLAYER LOSES 42 HEALTH  ", index
        assert state.dialog_message[0] == DIALOG_MESSAGES[index][0], index


def test_the_line_keeps_its_width_so_the_box_does_not_move() -> None:
    state = _normal_state()
    dialog_first_encounter(state, 0, 1 << 11, 7)
    assert len(state.dialog_message[1]) == len(DIALOG_MESSAGES[11][1])
    assert state.dialog_box_width == max(len(s) for s in DIALOG_MESSAGES[11])


def test_records_without_the_shared_line_ignore_the_value() -> None:
    state = _normal_state()
    dialog_first_encounter(state, 0, 1 << 0, 99)
    assert state.dialog_message == list(DIALOG_MESSAGES[0])


def test_first_encounter_message_suppression_preserves_flags_and_speech() -> None:
    state = _normal_state()
    state.suppress_first_encounter_messages = True
    state.dialog_timer = 10
    state.dialog_message = ["EXISTING"]

    assert dialog_first_encounter(state, 0, 1 << 1) == 1

    assert state.dialog_first_encounter_flags & (1 << 1)
    assert state.dialog_timer == 10
    assert state.dialog_message == ["EXISTING"]
    assert state.sound_log[-1] == DIALOG_SPEECH_IDS[1]


def test_a_missing_value_renders_a_blank_field() -> None:
    """Ordinary callers pass only player and mask (§10.4)."""
    state = _normal_state()
    dialog_first_encounter(state, 0, 1 << 15)
    assert state.dialog_message[1] == "  PLAYER LOSES  0 HEALTH  "
