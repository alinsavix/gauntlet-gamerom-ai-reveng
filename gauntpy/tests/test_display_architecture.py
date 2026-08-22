"""Architecture guards for the alpha VRAM/color-RAM rendering path."""

from __future__ import annotations

import inspect

from gauntpy.render import hud
from gauntpy.state import GameState
from gauntpy.subsystems import score
from gauntpy.subsystems.display import (
    _irgb_rgba,
    alpha_color_rgba,
    init_alpha_color_ram,
)
from gauntpy.subsystems.players import setup_infopanel


def test_hud_has_no_player_color_shortcut():
    source = inspect.getsource(hud)
    assert "_PLAYER_BLOCK_BG" not in source
    assert "PLAYER_COLOR_RGBA" not in source


def test_setup_infopanel_writes_opaque_palette_attributes_to_alpha_ram():
    state = GameState()
    init_alpha_color_ram(state)

    setup_infopanel(state, -1)

    for player_index, attribute in enumerate(score.PLAYER_TEXT_PALETTE_WORDS):
        row = player_index * score.PLAYER_BLOCK_STRIDE + score.PLAYER_LABEL_ROW
        start = row * score.ALPHA_ROW_STRIDE + score.PANEL_COLUMN
        words = state.alpha_ram[start:start + score.PANEL_WIDTH]
        assert all(word & 0xFC00 == attribute for word in words)
        assert all(word & 0x3FF == score.ALPHA_SPACE_GLYPH for word in words)


def test_player_background_words_convert_like_mame_color_ram():
    state = GameState()
    init_alpha_color_ram(state)
    assert _irgb_rgba(0x3F00) == (50, 0, 0, 255)
    assert tuple(
        alpha_color_rgba(state, attribute, 0)
        for attribute in score.PLAYER_TEXT_PALETTE_WORDS
    ) == (
        (50, 0, 0, 255),
        (0, 0, 50, 255),
        (33, 33, 0, 255),
        (0, 50, 0, 255),
    )
