"""Independent address examples for the hidden-alpha/route-grid byte alias."""

from gauntpy.game.alpha_memory import write_alpha_word, write_path_grid_byte
from gauntpy.game.state import GameState
from gauntpy.game.subsystems.display import (
    fill_alpha_rect, write_alpha_glyphs, write_alpha_name_entry_large_char,
)


def test_first_and_last_hidden_words_publish_big_endian_route_bytes():
    state = GameState()
    write_alpha_word(state, 42, 0x1234)
    write_alpha_word(state, 23 * 64 + 63, 0xABCD)
    assert state.path_direction_grid[0:2] == b"\x12\x34"
    assert state.path_direction_grid[23 * 128 + 42:23 * 128 + 44] == b"\xAB\xCD"
    assert state.path_direction_grid[44:128] == bytes(84)


def test_route_writes_preserve_the_other_byte_of_the_same_alpha_word():
    state = GameState()
    write_alpha_word(state, 42, 0xABCD)
    write_path_grid_byte(state, 0, 0x123)
    assert state.alpha_ram[42] == 0x23CD
    write_path_grid_byte(state, 1, 0x456)
    assert state.alpha_ram[42] == 0x2356
    assert state.path_direction_grid[:2] == b"\x23\x56"


def test_visible_and_below_route_rows_do_not_create_live_route_cells():
    state = GameState()
    state.path_direction_grid[:] = b"\xA5" * len(state.path_direction_grid)
    write_alpha_word(state, 41, 0x1234)
    write_alpha_word(state, 24 * 64 + 42, 0x5678)
    assert state.path_direction_grid == b"\xA5" * len(state.path_direction_grid)


def test_clipped_rectangle_updates_only_covered_hidden_words():
    state = GameState()
    state.path_direction_grid[:] = b"\xA5" * len(state.path_direction_grid)
    fill_alpha_rect(state, 41, 0, 3, 1, 0x12345)
    assert state.alpha_ram[40:45] == [0, 0x2345, 0x2345, 0x2345, 0]
    assert state.path_direction_grid[:6] == b"\x23\x45\x23\x45\xA5\xA5"
    assert state.path_direction_grid[128:130] == b"\xA5\xA5"


def test_glyph_writers_use_the_same_alias_boundary_as_rectangle_writers():
    state = GameState()
    write_alpha_glyphs(state, 42, 0, [ord("A")], 0x8000)
    assert state.alpha_ram[42] == 0x8041
    assert state.path_direction_grid[:2] == b"\x80\x41"
    write_alpha_name_entry_large_char(state, 42, 0, "-", 0x8000)
    assert state.path_direction_grid[:4] == b"\x80\x7C\x80\xFC"
    assert state.path_direction_grid[128:132] == b"\x80\xFE\x80\x7E"
