"""Architecture guards for the game-owned alpha VRAM rendering path."""

from __future__ import annotations

import ast
import inspect

from gauntpy.constants import PlayerStatus
from gauntpy.render import hud
from gauntpy.render import mobs as mob_renderer
from gauntpy.render import text as text_renderer
from gauntpy import assets
from gauntpy.render.alpha import draw_alpha_layer
from gauntpy.render.framebuffer import Framebuffer
from gauntpy.state import GameState
from gauntpy.subsystems import score
from gauntpy.subsystems.display import (
    CHARACTER_MOB_PALETTES,
    MOB_PALETTE_INIT,
    PLAYER_HURT_PALETTE_CYCLES,
    PLAYFIELD_PALETTE4_INIT,
    _irgb_rgba,
    alpha_color_rgba,
    alpha_palette_rgba,
    init_alpha_color_ram,
    init_player_mob_palette,
    init_playfield_color_ram,
    init_title_logo_colors,
    maze_show_alpha,
    palette_fade_word,
    player_palette_vblank,
    update_title_logo_colors,
)
from gauntpy.subsystems.players import setup_infopanel


def _calls(function) -> set[str]:
    tree = ast.parse(inspect.getsource(function))
    return {
        node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, (ast.Attribute, ast.Name))
    }


def test_game_content_render_entry_points_only_delegate_to_generic_alpha():
    assert _calls(hud.draw_hud) == {"draw_alpha_layer"}
    assert _calls(hud.draw_message_box) == {"draw_alpha_layer"}
    assert not {
        "draw_text", "draw_text_centered", "draw_glyph_run", "rectangle",
    } & _calls(hud.draw_hud)


def test_subsystem_display_has_no_gex_dependency():
    import gauntpy.subsystems.display as display

    assert "gex" not in inspect.getsource(display)


def test_rom_free_large_font_uses_the_os_character_index_map():
    source = inspect.getsource(text_renderer._large_fallback_tiles)
    assert "_LARGE_GLYPH_INDEX_MAP[ord(character)]" in source
    assert "_LARGE_GLYPH_INDEX_MAP[ord(\" \")]" in source


def test_maze_show_clears_everything_except_the_status_panel():
    state = GameState()
    state.alpha_ram[:] = [0xFFFF] * len(state.alpha_ram)

    maze_show_alpha(state)

    for row in range(30):
        assert state.alpha_ram[row * 64:row * 64 + 29] == [0] * 29
        assert state.alpha_ram[row * 64 + 29:row * 64 + 42] == [0xFFFF] * 13
        assert state.alpha_ram[row * 64 + 42:(row + 1) * 64] == [0] * 22


def test_large_text_uses_rom_variable_width_glyphs():
    from gauntpy.subsystems.display import write_alpha_large_text

    state = GameState()
    width = write_alpha_large_text(state, 4, 9, "L:", 0x8000)

    assert width == 3
    assert state.alpha_ram[9 * 64 + 6] & 0x3FF == 0x16D
    assert state.alpha_ram[9 * 64 + 7] == 0


def test_mob_renderer_and_asset_bridge_have_no_palette_overrides():
    mob_source = inspect.getsource(mob_renderer)
    asset_source = inspect.getsource(assets)
    assert "_player_hurt_palette" not in mob_source
    assert "_HURT_WHITE_RGBA" not in mob_source
    assert "assets.palette" not in mob_source
    assert "title_logo" not in asset_source
    assert "_title_logo_palette_words" not in asset_source


def test_setup_infopanel_writes_complete_rom_words_to_alpha_ram():
    state = GameState()
    init_alpha_color_ram(state)
    setup_infopanel(state, -1)

    for player_index, attribute in enumerate(score.PLAYER_TEXT_PALETTE_WORDS):
        base = player_index * score.PLAYER_BLOCK_STRIDE
        row = base + score.PLAYER_LABEL_ROW
        start = row * score.ALPHA_ROW_STRIDE + score.PANEL_COLUMN
        words = state.alpha_ram[start:start + score.PANEL_WIDTH]
        assert all(word & 0xFC00 == attribute for word in words)
        assert [word & 0x3FF for word in words[7:9]] == [0, 0]
        score_start = (
            (base + score.PLAYER_VALUE_ROW) * score.ALPHA_ROW_STRIDE
            + score.SCORE_COLUMN
        )
        assert "".join(
            chr(word & 0x3FF) if word & 0x3FF else " "
            for word in state.alpha_ram[
                score_start:score_start + score.SCORE_DIGITS
            ]
        ).strip() == ""


def test_setup_infopanel_makes_the_entire_status_column_opaque():
    state = GameState()
    setup_infopanel(state, -1)

    assert all(
        state.alpha_ram[row * score.ALPHA_ROW_STRIDE + column] & 0x8000
        for row in range(30)
        for column in range(score.PANEL_COLUMN, score.PANEL_LAST_COLUMN + 1)
    )


def test_vblank_cycles_the_dungeon_header_color_from_the_rom_gradient():
    from gauntpy.subsystems.display import (
        VSCROLL_ALPHA_GRADIENT,
        alpha_palette_vblank,
    )

    state = GameState()
    for frame in (0, 4, 124, 128, 252):
        state.frame_counter = frame
        alpha_palette_vblank(state)
        folded = (frame & 0xFC) ^ (0xFC if (frame & 0xFC) >= 0x80 else 0)
        assert state.alpha_color_ram[23] == VSCROLL_ALPHA_GRADIENT[folded >> 2]


def test_vblank_flashes_the_four_it_label_palettes_from_rom_color_ram():
    from gauntpy.subsystems.display import (
        ALPHA_PALETTE_INIT,
        alpha_palette_vblank,
        restore_alpha_color_ram,
    )

    state = GameState()
    restore_alpha_color_ram(state)

    state.frame_counter = 0
    alpha_palette_vblank(state)
    for palette in range(12, 16):
        base = palette * 4
        assert state.alpha_color_ram[base:base + 4] == [
            ALPHA_PALETTE_INIT[base],
        ] * 4

    state.frame_counter = 0x10
    alpha_palette_vblank(state)
    assert state.alpha_color_ram[48:64] == list(ALPHA_PALETTE_INIT[48:64])


def test_inventory_writer_stamps_complete_rom_power_icon_words():
    state = GameState()
    state.players[2].status = 1
    state.players[2].powers = 0b10_0101
    setup_infopanel(state, 2)
    row = 2 * score.PLAYER_BLOCK_STRIDE + score.PLAYER_NAME_ROW

    assert [
        state.alpha_ram[row * score.ALPHA_ROW_STRIDE + column]
        for column in score.POWER_ICON_COLUMNS
    ] == [
        word if state.players[2].powers & (1 << bit) else 0x8000
        for bit, word in enumerate(score.POWER_ICON_WORDS)
    ]
    assert score.POWER_ICON_COLUMNS == (40, 39, 32, 31, 30, 29)


def test_removed_player_rebuild_clears_every_stale_panel_content_cell():
    state = GameState()
    player_index = 1
    base_row = player_index * score.PLAYER_BLOCK_STRIDE + score.PLAYER_NAME_ROW
    for row in range(base_row, base_row + score.PLAYER_BLOCK_ROWS):
        start = row * score.ALPHA_ROW_STRIDE + score.PANEL_COLUMN
        state.alpha_ram[start:start + score.PANEL_WIDTH] = [0x9BAD] * score.PANEL_WIDTH
    state.players[player_index].status = int(PlayerStatus.REMOVED)

    setup_infopanel(state, player_index)

    block = [
        state.alpha_ram[row * score.ALPHA_ROW_STRIDE + column]
        for row in range(base_row, base_row + score.PLAYER_BLOCK_ROWS)
        for column in range(score.PANEL_COLUMN, score.PANEL_LAST_COLUMN + 1)
    ]
    assert 0x9BAD not in block
    assert not set(score.POWER_ICON_WORDS) & set(block)
    assert all(
        state.alpha_ram[
            base_row * score.ALPHA_ROW_STRIDE + column
        ] & 0x3FF == score.ALPHA_SPACE_GLYPH
        for column in range(score.PANEL_COLUMN, score.PANEL_LAST_COLUMN + 1)
    )


def test_generic_renderer_observes_opaque_bank_palette_and_glyph(monkeypatch):
    state = GameState()
    init_alpha_color_ram(state)
    state.alpha_ram[0] = 0xD000 | ord("A")
    seen = []
    monkeypatch.setattr(
        "gauntpy.render.alpha.draw_alpha_glyph",
        lambda image, x, y, code, palette, *, opaque:
            seen.append((x, y, code, palette, opaque)),
    )

    draw_alpha_layer(Framebuffer(336, 240), state)

    assert seen == [(
        0, 0, ord("A"), alpha_palette_rgba(state, 0xD000), True,
    )]


def test_generic_alpha_has_a_rom_free_pil_fallback(monkeypatch):
    import gauntpy.render.text as text

    state = GameState()
    init_alpha_color_ram(state)
    state.alpha_ram[0] = 0xD000 | ord("A")
    monkeypatch.setattr(text, "_glyph_checked", True)
    monkeypatch.setattr(text, "_glyph_fn", None)
    monkeypatch.setattr(text, "_raw_glyph_fn", None)
    fb = Framebuffer(336, 240)

    draw_alpha_layer(fb, state)

    background = alpha_color_rgba(state, 0xD000, 0)
    assert any(
        fb.get_pixel(x, y) != background
        for y in range(8) for x in range(8)
    )


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


def test_init_display_copies_all_256_mob_color_words_in_rom_order():
    state = GameState()
    init_alpha_color_ram(state)
    assert state.mob_color_ram == list(MOB_PALETTE_INIT)


def test_player_start_and_hurt_vblank_write_the_live_player_palette():
    state = GameState()
    init_alpha_color_ram(state)
    init_player_mob_palette(state, 2, 3)
    assert state.mob_color_ram[224:240] == list(CHARACTER_MOB_PALETTES[3][32:48])
    assert state.player_hurt_palette_offset[2] == 3 * 0x12
    assert state.player_power_palette_offset[2] == 3 * 0x30

    state.players[2].character = 3
    state.players[2].hurt_cooldown = 0x12
    player_palette_vblank(state)
    source = PLAYER_HURT_PALETTE_CYCLES[2]
    source_index = (3 * 0x12 + 0x0C) // 2
    assert state.mob_color_ram[224 + 11] == source[source_index]
    assert state.mob_color_ram[224 + 12] == source[source_index + 1]


def test_title_initializer_and_nested_cycle_mutate_mob_color_ram():
    state = GameState()
    init_alpha_color_ram(state)
    init_title_logo_colors(state)
    assert [state.mob_color_ram[p * 16 + 14] for p in range(10)] == [0xBFFF] * 10
    before = list(state.mob_color_ram)

    update_title_logo_colors(state)
    for palette in range(9):
        base = palette * 16
        assert state.mob_color_ram[base + 2:base + 9] == before[base + 3:base + 10]
        assert state.mob_color_ram[base + 9] == before[base + 18]
    assert state.mob_color_ram[153] == 0x000F
    update_title_logo_colors(state)
    update_title_logo_colors(state)
    assert state.mob_color_ram[153] == 0x1077


def test_level_playfield_palette_setup_clones_and_derives_exact_banks():
    state = GameState()
    main = [0xF000 | index for index in range(16)]
    special = [0xF100 | index for index in range(16)]

    init_playfield_color_ram(state, main, special)

    assert state.playfield_color_ram[0:64] == main * 4
    assert state.playfield_color_ram[64:80] == list(PLAYFIELD_PALETTE4_INIT)
    assert state.playfield_color_ram[112:128] == special
    assert state.playfield_color_ram[96:112] == [
        palette_fade_word(word, 0x4000) for word in special
    ]
    assert state.playfield_color_ram[80:96] == [
        palette_fade_word(word, 0x3000)
        for word in state.playfield_color_ram[96:112]
    ]
    assert state.playfield_shadow_color_ram == [
        palette_fade_word(word, 0x7000)
        for word in state.playfield_color_ram
    ]


def test_shrub_substitutions_happen_after_palette_fades_before_shadow():
    state = GameState()
    main = [0xF000 | index for index in range(16)]
    raw = [0xE100 | index for index in range(16)]
    substitutions = ((13, 0xFABC), (14, 0xFDEF), (15, 0xF123))

    init_playfield_color_ram(
        state, main, raw, palette7_substitutions=substitutions,
    )

    assert state.playfield_color_ram[112:128] == raw[:13] + [
        0xFABC, 0xFDEF, 0xF123,
    ]
    assert state.playfield_color_ram[96:112] == [
        palette_fade_word(word, 0x4000) for word in raw
    ]
    assert state.playfield_color_ram[80:96] == [
        palette_fade_word(
            palette_fade_word(word, 0x4000), 0x3000,
        )
        for word in raw
    ]
    assert state.playfield_shadow_color_ram[112:128] == [
        palette_fade_word(word, 0x7000)
        for word in state.playfield_color_ram[112:128]
    ]
