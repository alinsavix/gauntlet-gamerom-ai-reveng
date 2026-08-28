"""Alpha VRAM/color-RAM primitives shared by the game-side display routines."""

from __future__ import annotations

from ..mob import MobTable
from ..state import GameState

ALPHA_COLUMNS = 64
ALPHA_VISIBLE_COLUMNS = 42
ALPHA_ROWS = 30
ALPHA_GLYPH_MASK = 0x03FF
ALPHA_ATTRIBUTE_MASK = 0xFC00

# OS large_character_tile_quads, OS ROM 0x33D2. Bytes are
# top-left, bottom-left, top-right, bottom-right alpha glyphs.
_LARGE_GLYPH_QUADS = (
    (0x00, 0x02, 0x01, 0x03), (0x04, 0x06, 0x05, 0x07),
    (0x08, 0x0A, 0x09, 0x0B), (0x0C, 0x0E, 0x0D, 0x0F),
    (0x10, 0x12, 0x11, 0x13), (0x14, 0x16, 0x15, 0x17),
    (0x18, 0x1A, 0x19, 0x1B), (0x1C, 0x1E, 0x1D, 0x1F),
    (0x20, 0x22, 0x21, 0x23), (0x24, 0x26, 0x25, 0x27),
    (0x28, 0x2A, 0x29, 0x2B), (0x2C, 0x2D, 0x21, 0x2E),
    (0x00, 0x02, 0x2F, 0x30), (0x31, 0x32, 0x01, 0x03),
    (0x2C, 0x2D, 0x33, 0x34), (0x2C, 0x2D, 0x33, 0x35),
    (0x00, 0x02, 0x2F, 0x36), (0x2C, 0x2D, 0x37, 0x38),
    (0x39, 0x06, 0x3A, 0x3B), (0x3C, 0x3E, 0x3D, 0x3F),
    (0x2C, 0x2D, 0x40, 0x41), (0x31, 0x32, 0x42, 0x43),
    (0x44, 0x46, 0x45, 0x47), (0x48, 0x4A, 0x49, 0x4B),
    (0x00, 0x02, 0x01, 0x03), (0x2C, 0x2D, 0x21, 0x4C),
    (0x00, 0x02, 0x01, 0x4D), (0x2C, 0x2D, 0x21, 0x41),
    (0x4E, 0x50, 0x4F, 0x51), (0x52, 0x06, 0x53, 0x07),
    (0x31, 0x55, 0x54, 0x56), (0x57, 0x59, 0x58, 0x5A),
    (0x5B, 0x5D, 0x5C, 0x5E), (0x5F, 0x61, 0x60, 0x62),
    (0x5F, 0x64, 0x63, 0x65), (0x1C, 0x67, 0x66, 0x68),
    (0x69, 0x6B, 0x6A, 0x6C), (0x3C, 0x3C, 0x3C, 0x3C),
    (0x6E, 0x3C, 0x6E, 0x3C), (0x6D, 0x6E, 0x00, 0x00),
    (0x6F, 0x70, 0x00, 0x00), (0x71, 0x72, 0x00, 0x00),
    (0x6D, 0x6D, 0x00, 0x00), (0x3C, 0x6D, 0x00, 0x00),
    (0x3C, 0x6E, 0x00, 0x00), (0x3C, 0x3C, 0x00, 0x00),
    (0x6E, 0x3C, 0x00, 0x00), (0x00, 0x00, 0x00, 0x00),
    (0x00, 0x00, 0x00, 0x00), (0x00, 0x00, 0x00, 0x00),
    (0x1C, 0x1E, 0xDB, 0xDD),
)


def _rom_words(words: str) -> tuple[int, ...]:
    return tuple(int(word, 16) for word in words.split())

# teleff_palette, ROM 0x5ACFE. init_display (0x4356C-0x4357C) copies all
# sixteen words to playfield palette 4 at 0x910580.
PLAYFIELD_PALETTE4_INIT = (
    0x0000, 0x0000, 0x4FEC, 0x5F00, 0x8F00, 0xCF20, 0xFF20, 0xEFFF,
    0x8F00, 0xCF21, 0xFF76, 0xFF98, 0xFFDD, 0xFFFF, 0x0000, 0x0000,
)

# alpha_palette_init, ROM 0x5AD1E. init_display (0x434C2-0x434EC) copies the
# first 0x20 longwords to 0x910000 and the second 0x20 to 0x910100.
ALPHA_PALETTE_INIT = (
    0x0000, 0xFFFF, 0xDFFF, 0xAFFF, 0x0000, 0x2F00, 0x7F00, 0xFF00,
    0x0000, 0x208F, 0x708F, 0xF08F, 0x0000, 0x2FF0, 0x7FF0, 0xFFF0,
    0x0000, 0x20F0, 0x70F0, 0xF0F0, 0x0000, 0x0000, 0xF888, 0xF00F,
    0x0000, 0x0000, 0x0000, 0xFF00, 0x0000, 0xFC80, 0xFCA4, 0x0000,
    0x0000, 0xF532, 0xFB63, 0xFFFF, 0x0000, 0x0000, 0x0000, 0xFFFF,
    0x0000, 0x0000, 0xFFF0, 0xFF60, 0x0000, 0xF050, 0xF080, 0xF0F0,
    0x3F00, 0x5FFF, 0xFFFF, 0xFFFF, 0x300F, 0x5FFF, 0xFFFF, 0xFFFF,
    0x2FF0, 0x5FFF, 0xFFFF, 0xFFFF, 0x30F0, 0x5FFF, 0xFFFF, 0xFFFF,
    0x3F00, 0xFFFF, 0xDFFF, 0xAFFF, 0x300F, 0xFFFF, 0xDFFF, 0xAFFF,
    0x2FF0, 0xFFFF, 0xDFFF, 0xAFFF, 0x30F0, 0xFFFF, 0xDFFF, 0xAFFF,
    0x3F00, 0x2F00, 0x7F00, 0xFF00, 0x300F, 0x208F, 0x708F, 0xF08F,
    0x2FF0, 0x2FF0, 0x7FF0, 0xFFF0, 0x30F0, 0x20F0, 0x70F0, 0xF0F0,
    0x3F00, 0xFFA0, 0xF08E, 0xF00C, 0x300F, 0xFFA0, 0xF08E, 0xF00C,
    0x2FF0, 0xFFA0, 0xF08E, 0xF00C, 0x30F0, 0xFFA0, 0xF08E, 0xF00C,
    0x3F00, 0xF226, 0xF33D, 0xF66F, 0x300F, 0xF226, 0xF33D, 0xF66F,
    0x2FF0, 0xF226, 0xF33D, 0xF66F, 0x30F0, 0xF226, 0xF33D, 0xF66F,
)

# init_display 0x435F2: 0x60 longwords from ROM 0x5AE1E to 0x910200.
MOB_PALETTE_EXTENDED = _rom_words("""
0000 0000 988F A99F C99F FBBF A888 0000 9999 7F8F 711F 5F93 6F84 EF86 F0F0 FFBB
0000 0000 7F84 8F85 AF83 40F7 FF20 FF82 FFC0 FFFF 5F50 81F8 EF88 D79F A17F A00F
0000 0000 0000 7165 7387 7598 76BA 78DC 7AFE 0000 0000 7E7A 7FDF 7FC0 3FF0 7F72
0000 0000 FFFF A165 A387 A598 A6BA A8DC AAFE 0000 FFFF CE7A AFDF 8FC0 5FF0 BF72
0000 0000 FF00 F165 F387 F598 F6BA F8DC FAFE 0000 FF00 FE7A FFDF CFC0 8FF0 FF72
0000 0000 6ABF 8BBF BAAF DCBF FDDF FFFF 5F77 6F99 8FAA 9FBB AFCC CFDD 5BBF FF00
0000 0000 3FC5 5F84 5F96 6F86 AFC0 6FB1 6F9A 6F30 8F00 6F55 2F19 4F00 6F11 AFFF
0000 0000 4FC5 7F84 7F96 8F86 CFC0 9FB1 9F9A 9F30 CF00 9F55 3F19 6F00 8F11 CFFF
0000 0000 5FC5 9F84 BF96 DF86 FFC0 FFB1 FF9A FF30 FF00 FF55 4F19 9F00 DF11 FFFF
0000 0000 0000 0000 9F9A AF9A 2909 6A08 9806 8888 9CCF 4F33 5F89 7F83 BF94 9F11
0000 0000 FFFF 0000 9F9A CF9A 4909 9A08 C806 8888 ACCF 5F33 6F89 7F83 BF94 BF11
0000 0000 FF00 0000 9F9A EF9A 6909 CA08 F806 8888 BCCF 6F33 7F89 7F83 BF94 DF11
""")

# Four 128-byte character palettes at ROM 0x5B00E/0x5B08E/0x5B10E/0x5B18E.
# Each contains the four player-position variants copied by player_start_inner.
CHARACTER_MOB_PALETTES = (
    _rom_words("""
0000 0000 6944 9B74 BF96 DFA8 BFB6 6F99 FF9A 8F00 FF00 FFB3 4D74 7DB0 F6FF FFFF
0000 0000 6944 9B74 BF96 DFA8 BFB6 7F99 FF9A A00F F24F D3BF 4D74 7DB0 F6FF FFFF
0000 0000 6944 9B74 BF96 DFA8 9FC5 4FA8 FF9A BE90 FFF0 CFFB 4D74 7DB0 F6FF FFFF
0000 0000 6944 9B74 BD96 DFA8 BFB6 44F9 FF9A 90F0 D3F0 FBFB 4D74 7DB0 F6FF FFFF
"""),
    _rom_words("""
0000 0000 6F93 9F84 CF83 FF66 9FB0 8FBC FF9A 8F22 AF22 FF22 7F00 EFB0 D111 FFFF
0000 0000 6F93 9F84 CF83 FF66 9FB0 8FBC FF9A F25F F48F F8BF 700F EFB0 D111 FFFF
0000 0000 6F93 9F84 CF83 FF66 9F90 8FBC FF9A 7FF2 AFF2 EFF2 7FF0 EF90 D111 FFFF
0000 0000 6F93 9F84 CF83 FF66 9FB0 8FBC FF9A 60F0 90F0 F0F0 70F0 EFB0 D111 FFFF
"""),
    _rom_words("""
0000 0000 6F93 4F00 DF86 FF9A 6F00 9F00 FF00 8FFF DFFF 0000 0000 0000 7F43 0000
0000 0000 6F93 222F DF86 FF9A 622F A22F F22F 8FFF DFFF 0000 0000 0000 7F43 0000
0000 0000 6F93 7F84 DF86 FF9A 9FD0 CFC0 FFD0 8FFF DFFF 0000 0000 0000 7F43 0000
0000 0000 6F93 21F1 DF86 FF9A 42F2 82F2 A2F2 8FFF DFFF 0000 0000 0000 7F43 0000
"""),
    _rom_words("""
0000 0000 4F93 9F84 DF86 FF8A 9FD9 CFC8 FFF6 DFFF FFFF 5F01 9F00 DF32 6F10 4A8F
0000 0000 4F93 9F84 DF86 FF8A 9FD9 CFC8 FFF6 DFFF FFFF 801F F11D C06F 6F10 4A8F
0000 0000 4F93 9F84 DF86 FF8A 9FD9 CFC8 FFF6 DFFF FFFF 9FC0 CFD0 FFF0 6F10 4A8F
0000 0000 4F93 9F84 DF86 FF8A 9FD9 CFC8 FFF6 DFFF FFFF 60F1 90F0 C0F6 6F10 4A8F
"""),
)

# init_display 0x43604 dereferences character_palette_ptrs[2] (ROM 0x5AFA6)
# and copies the Wizard's complete 64-word table to MOB palettes 12-15.
MOB_PALETTE_INIT = MOB_PALETTE_EXTENDED + CHARACTER_MOB_PALETTES[2]

# game_vblank 0x401DE-0x40304 sources. Rows correspond to player positions;
# player_hurt_palette_offset adds character * 0x12 bytes.
PLAYER_HURT_PALETTE_CYCLES = (
    _rom_words("""
DFA8 4D74 0000 FFFF FFFF 0000 FFFF FFFF 0000 9FB0 FF9A 8F22 FFFF FFFF FFFF FFFF
FFFF FFFF 6F00 FF00 DFFF FFFF FFFF FFFF FFFF FFFF FFFF 5F01 9F00 0000 FFFF FFFF
0000 FFFF FFFF 0000
"""),
    _rom_words("""
DFA8 4D74 0000 FFFF FFFF 0000 FFFF FFFF 0000 9FB0 FF9A F25F FFFF FFFF FFFF FFFF
FFFF FFFF 622F F22F DFFF FFFF FFFF FFFF FFFF FFFF FFFF 801F F11D 0000 FFFF FFFF
0000 FFFF FFFF 0000
"""),
    _rom_words("""
DFA8 4D74 0000 FFFF FFFF 0000 FFFF FFFF 0000 9F90 FF9A 7FF2 F00F F00F F00F F00F
F00F F00F 9FD0 FFD0 DFFF F00F F00F F00F F00F F00F F00F 9FC0 CFD0 0000 FFFF FFFF
0000 FFFF FFFF 0000
"""),
    _rom_words("""
DFA8 4D74 0000 FFFF FFFF 0000 FFFF FFFF 0000 9FB0 FF9A 60F0 FFFF FFFF FFFF FFFF
FFFF FFFF 42F2 A2F2 DFFF FFFF FFFF FFFF FFFF FFFF FFFF 60F1 90F0 0000 FFFF FFFF
0000 FFFF FFFF 0000
"""),
)

# game_vblank's four 192-byte power-cycle sources at ROM
# 0x5B32E/0x5B3EE/0x5B4AE/0x5B56E.
PLAYER_POWER_PALETTE_CYCLES = (
    _rom_words("""
DFA8 BFA8 9FA8 7FA8 5FA8 7FA8 9FA8 BFA8 4D74 3D74 2D74 1D74 0D74 1D74 2D74 3D74
0000 0000 0000 0000 0000 0000 0000 0000 9FB0 7FB0 5FB0 3FB0 1FB0 3FB0 5FB0 7FB0
FF9A CF9A 9F9A 6F9A 3F9A 6F9A 9F9A CF9A 8F22 6F22 4F22 2F22 1F22 2F22 4F22 6F22
6F00 5F00 4F00 3F00 2F00 3F00 4F00 5F00 FF00 CF00 9F00 6F00 3F00 6F00 9F00 CF00
DFFF BFFF 9FFF 7FFF 5FFF 7FFF 9FFF BFFF 5F01 4F01 3F01 2F01 1F01 2F01 3F01 4F01
9F00 7F00 5F00 3F00 1F00 3F00 5F00 7F00 0000 0000 0000 0000 0000 0000 0000 0000
"""),
    _rom_words("""
DFA8 BFA8 9FA8 7FA8 5FA8 7FA8 9FA8 BFA8 4D74 3D74 2D74 1D74 0D74 1D74 2D74 3D74
0000 0000 0000 0000 0000 0000 0000 0000 9FB0 7FB0 5FB0 3FB0 1FB0 3FB0 5FB0 7FB0
FF9A CF9A 9F9A 6F9A 3F9A 6F9A 9F9A CF9A F25F C25F 925F 625F 325F 625F 925F C25F
622F 522F 422F 322F 222F 322F 422F 522F F22F C22F 922F 622F 322F 622F 922F C22F
DFFF BFFF 9FFF 7FFF 5FFF 7FFF 9FFF BFFF 801F 601F 401F 201F 101F 201F 401F 601F
F11D C11D 911D 611D 311D 611D 911D C11D 0000 0000 0000 0000 0000 0000 0000 0000
"""),
    _rom_words("""
DFA8 BFA8 9FA8 7FA8 5FA8 7FA8 9FA8 BFA8 4D74 3D74 2D74 1D74 0D74 1D74 2D74 3D74
0000 0000 0000 0000 0000 0000 0000 0000 9F90 7F90 5F90 3F90 1F90 3F90 5F90 7F90
FF9A CF9A 9F9A 6F9A 3F9A 6F9A 9F9A CF9A 7FF2 5FF2 3FF2 1FF2 0FF2 1FF2 3FF2 5FF2
9FD0 7FD0 5FD0 3FD0 1FD0 3FD0 5FD0 7FD0 FFD0 CFD0 9FD0 6FD0 3FD0 6FD0 9FD0 CFD0
DFFF BFFF 9FFF 7FFF 5FFF 7FFF 9FFF BFFF 9FC0 7FC0 5FC0 3FC0 1FC0 3FC0 5FC0 7FC0
CFD0 AFD0 8FD0 6FD0 4FD0 6FD0 8FD0 AFD0 0000 0000 0000 0000 0000 0000 0000 0000
"""),
    _rom_words("""
DFA8 BFA8 9FA8 7FA8 5FA8 7FA8 9FA8 BFA8 4D74 3D74 2D74 1D74 0D74 1D74 2D74 3D74
0000 0000 0000 0000 0000 0000 0000 0000 9FB0 7FB0 5FB0 3FB0 1FB0 3FB0 5FB0 7FB0
FF9A CF9A 9F9A 6F9A 3F9A 6F9A 9F9A CF9A 60F0 50F0 40F0 30F0 20F0 30F0 40F0 50F0
42F2 32F2 22F2 12F2 02F2 12F2 22F2 32F2 A2F2 82F2 62F2 42F2 22F2 42F2 62F2 82F2
DFFF BFFF 9FFF 7FFF 5FFF 7FFF 9FFF BFFF 60F1 50F1 40F1 30F1 20F1 30F1 40F1 50F1
90F0 70F0 50F0 30F0 10F0 30F0 50F0 70F0 0000 0000 0000 0000 0000 0000 0000 0000
"""),
)

LOGO_BRIGHTNESS_SEQUENCE = _rom_words("000F 0077 00F0 0770 0F00 0707 0000")
LOGO_OUTER_TIMER_INIT = 0x0000  # ROM 0x5BA68
LOGO_INNER_TIMER_INIT = 0x0002  # ROM 0x5BA6A
LOGO_BRIGHT_MIN = 0x0002        # ROM 0x5BA6C
LOGO_BRIGHT_MAX = 0x000F        # ROM 0x5BA6E

# vscroll_alpha_gradient, ROM 0x405E8. game_vblank 0x40304-0x40324 folds
# frame_counter & 0xFC around 0x80 and writes the selected word to alpha color
# RAM 0x91002E (palette 5, color 3), animating the dungeon logo in the HUD.
VSCROLL_ALPHA_GRADIENT = _rom_words("""
F00F F00E F00D F00C F00B F00A F009 F008
F007 F006 F005 F004 F003 F002 F001 F000
F000 F100 F200 F300 F400 F500 F600 F700
F800 F900 FA00 FB00 FC00 FD00 FE00 FF00
""")


def restore_alpha_color_ram(state: GameState) -> None:
    """Copy init_display's two alpha palette banks without touching alpha RAM."""
    state.alpha_color_ram[:] = [0] * 256
    state.alpha_color_ram[0:64] = ALPHA_PALETTE_INIT[0:64]
    state.alpha_color_ram[128:192] = ALPHA_PALETTE_INIT[64:128]


def init_alpha_color_ram(
    state: GameState, *, initialize_mobs: bool = True,
) -> None:
    """Perform init_display's alpha copies and, normally, its MOB copies.

    ``init_display(0x10, 0x10)`` on TITLE returns after the alpha copies at
    0x434EE, so that caller leaves the cleared MOB color RAM for
    ``title_logo_init`` to populate.
    """
    state.alpha_ram[:] = [0] * (ALPHA_COLUMNS * ALPHA_ROWS)
    restore_alpha_color_ram(state)
    if initialize_mobs:
        init_mob_color_ram(state)


def init_mob_color_ram(state: GameState) -> None:
    """Port init_display 0x435F2-0x43614 in its exact copy order."""
    state.mob_color_ram[:] = MOB_PALETTE_EXTENDED
    state.mob_color_ram[192:256] = CHARACTER_MOB_PALETTES[2]


def clear_mob_color_ram(state: GameState) -> None:
    """pf_palette_clear 0x5FCEA-0x5FCF4: clear all 0x80 longwords."""
    state.mob_color_ram[:] = [0] * 256


def clear_attract_display_memory(state: GameState) -> None:
    """Port pf_palette_clear/display_state_clear at 0x5FCCE/0x5FD14."""
    state.playfield_color_latch = 0
    state.playfield_color_base = 0
    state.alpha_color_ram[:] = [0] * 256
    state.mob_color_ram[:] = [0] * 256
    state.playfield_color_ram[:] = [0] * 128
    state.playfield_shadow_color_ram[:] = [0] * 128
    state.playfield_color_generation += 1
    state.alpha_ram[:] = [0] * (ALPHA_COLUMNS * ALPHA_ROWS)
    state.playfield_ram[:] = [0] * len(state.playfield_ram)
    state.playfield_generation += 1
    state.mobs = MobTable()
    state.scroll_x = 0
    state.scroll_y = 0


def init_player_mob_palette(
    state: GameState, player_index: int, character: int,
) -> None:
    """player_start_inner 0x48CCC-0x48D80: install one live player palette."""
    character &= 3
    state.player_hurt_palette_offset[player_index] = character * 0x12
    state.player_power_palette_offset[player_index] = character * 0x30
    source = CHARACTER_MOB_PALETTES[character]
    source_start = player_index * 16
    destination = 192 + player_index * 16
    state.mob_color_ram[destination:destination + 16] = source[
        source_start:source_start + 16
    ]


_PLAYER_HURT_DESTINATIONS = (
    ((5, 0), (12, 1)),
    ((6, 0), (8, 1), (9, 2)),
    ((6, 0), (8, 1), (10, 2)),
    ((11, 0), (12, 1)),
)
_PLAYER_POWER_DESTINATIONS = (
    ((5, 0x00), (12, 0x10)),
    ((6, 0x00), (8, 0x10), (9, 0x20)),
    ((6, 0x00), (8, 0x10), (10, 0x20)),
    ((11, 0x00), (12, 0x10)),
)


def player_palette_vblank(state: GameState) -> None:
    """game_vblank 0x401DE-0x40304 live player hurt/power color writes."""
    for player_index, player in enumerate(state.players):
        destination = 192 + player_index * 16
        character = int(player.character) & 3
        if player.hurt_cooldown:
            player.hurt_cooldown = max(0, player.hurt_cooldown - 6)
            byte_offset = (
                state.player_hurt_palette_offset[player_index]
                + player.hurt_cooldown
            )
            source_index = byte_offset // 2
            source = PLAYER_HURT_PALETTE_CYCLES[player_index]
            for color_index, relative_word in _PLAYER_HURT_DESTINATIONS[character]:
                state.mob_color_ram[destination + color_index] = source[
                    source_index + relative_word
                ]
            continue

        power_timer = state.player_repulse_timer[player_index]
        if power_timer == 0:
            continue
        byte_offset = (
            state.player_power_palette_offset[player_index]
            + ((power_timer & 0x38) >> 2)
        )
        source_index = byte_offset // 2
        source = PLAYER_POWER_PALETTE_CYCLES[player_index]
        for color_index, relative_bytes in _PLAYER_POWER_DESTINATIONS[character]:
            state.mob_color_ram[destination + color_index] = source[
                source_index + relative_bytes // 2
            ]


def potion_flash_vblank(state: GameState) -> None:
    """game_vblank 0x401D4: publish the live potion/floor color latch."""
    from ..playfield_vram import write_playfield_color

    write_playfield_color(state, 8, state.playfield_color_latch)


def alpha_palette_vblank(state: GameState) -> None:
    """Port game_vblank's live alpha-color writes at 0x40304-0x4037A."""
    phase = state.frame_counter & 0xFC
    if phase >= 0x80:
        phase ^= 0xFC
    state.alpha_color_ram[23] = VSCROLL_ALPHA_GRADIENT[phase >> 2]

    if state.frame_counter & 0x0F:
        return

    # 0x40328-0x4037A flashes the four player-specific IT palettes (12-15).
    # The dim half copies each palette's color 0 over colors 1-3; the bright
    # half restores those colors from alpha_palette_init.
    bright = bool(state.frame_counter & 0x10)
    for palette in range(12, 16):
        base = palette * 4
        for color in range(1, 4):
            source = base + color if bright else base
            state.alpha_color_ram[base + color] = ALPHA_PALETTE_INIT[source]


def init_title_logo_colors(state: GameState) -> None:
    """title_logo_init 0x4DA46-0x4DA98 and 0x4DC72 color state."""
    state.logo_color_index = 0
    state.logo_bright_accum = 0
    state.logo_color_cur = LOGO_BRIGHTNESS_SEQUENCE[0]
    state.logo_color_index = 1
    state.logo_bright_timer = LOGO_INNER_TIMER_INIT
    state.logo_color_dir = 1
    for palette in range(10):
        state.mob_color_ram[palette * 16 + 14] = 0xBFFF
    state.logo_cycle_timer = LOGO_OUTER_TIMER_INIT


def update_title_logo_colors(state: GameState) -> None:
    """main_logo_updcolors 0x4DCEE-0x4DDE8 live MOB-color writes."""
    if state.logo_cycle_timer & 0x8000:
        return
    state.logo_cycle_timer = (state.logo_cycle_timer - 1) & 0xFFFF
    if not state.logo_cycle_timer & 0x8000:
        return
    state.logo_cycle_timer = LOGO_OUTER_TIMER_INIT

    for palette in range(10):
        base = palette * 16
        state.mob_color_ram[base + 2:base + 9] = state.mob_color_ram[
            base + 3:base + 10
        ]
        state.mob_color_ram[base + 9] = state.mob_color_ram[base + 18]

    state.logo_bright_timer = (state.logo_bright_timer - 1) & 0xFFFF
    if state.logo_bright_timer & 0x8000:
        state.logo_bright_timer = LOGO_INNER_TIMER_INIT
        state.logo_bright_accum += state.logo_color_dir
        if state.logo_bright_accum > LOGO_BRIGHT_MAX:
            state.logo_bright_accum = LOGO_BRIGHT_MAX
            state.logo_color_dir = -state.logo_color_dir
        elif state.logo_bright_accum < LOGO_BRIGHT_MIN:
            state.logo_bright_accum = LOGO_BRIGHT_MIN
            state.logo_color_dir = -state.logo_color_dir
            state.logo_bright_accum += state.logo_color_dir
            state.logo_color_cur = LOGO_BRIGHTNESS_SEQUENCE[
                state.logo_color_index
            ]
            state.logo_color_index += 1
            if state.logo_color_cur == 0:
                state.logo_color_index = 0
                state.logo_color_cur = LOGO_BRIGHTNESS_SEQUENCE[0]
                state.logo_color_index = 1

    state.mob_color_ram[153] = (
        (state.logo_bright_accum << 12) + state.logo_color_cur
    ) & 0xFFFF


def mob_palette_words(state: GameState, palette: int) -> tuple[int, ...]:
    """Resolve a MOB hpos palette nibble to sixteen live color-RAM entries."""
    base = (palette & 0x0F) * 16
    return tuple(state.mob_color_ram[base:base + 16])


def mob_palette_rgba(
    state: GameState, palette: int,
) -> tuple[tuple[int, int, int, int], ...]:
    return tuple(_irgb_rgba(word) for word in mob_palette_words(state, palette))


def palette_fade_word(word: int, delta: int) -> int:
    """palette_fade_copy (0x5FD80), including its 12-bit underflow encoding."""
    value = (int(word) & 0xFFFF) - int(delta)
    if value >= 0:
        return value & 0xFFFF
    return ((value & 0x0FFF) | 0x1000) & 0xFFFF


def init_playfield_color_ram(
    state: GameState,
    main_palette: list[int] | tuple[int, ...],
    special_palette: list[int] | tuple[int, ...],
    *,
    palette7_substitutions: tuple[tuple[int, int], ...] = (),
) -> None:
    """Port init_display's level playfield setup (0x434FA-0x436B8).

    ``main_palette`` is the selected 0x5D5C8 record and ``special_palette`` is
    the raw selected 0x5D7C8/0x5D7E8 record.  On shrub levels the ROM derives
    palettes 6 and 5 first, then applies three floor-color substitutions only
    to palette 7; callers provide those writes in ``palette7_substitutions``.
    """
    if len(main_palette) != 16 or len(special_palette) != 16:
        raise ValueError("playfield palettes must contain sixteen IRGB words")

    restore_alpha_color_ram(state)
    # Every level-facing init_display call performs these MOB copies before the
    # playfield branches at 0x43616.
    init_mob_color_ram(state)

    main = [int(word) & 0xFFFF for word in main_palette]
    raw_palette7 = [int(word) & 0xFFFF for word in special_palette]
    palette6 = [palette_fade_word(word, 0x4000) for word in raw_palette7]
    palette5 = [palette_fade_word(word, 0x3000) for word in palette6]
    palette7 = list(raw_palette7)
    for index, word in palette7_substitutions:
        if not 0 <= index < 16:
            raise IndexError("palette 7 substitution index must be in 0..15")
        palette7[index] = int(word) & 0xFFFF

    normal = [0] * 128
    for bank in range(4):
        normal[bank * 16:(bank + 1) * 16] = main
    normal[64:80] = PLAYFIELD_PALETTE4_INIT
    normal[80:96] = palette5
    normal[96:112] = palette6
    normal[112:128] = palette7
    state.playfield_color_base = main[8]
    state.playfield_color_latch = main[8]

    # The shadow-bank derivation is last, after palette-7 substitutions.
    shadow = [palette_fade_word(word, 0x7000) for word in normal]
    if (
        state.playfield_color_ram != normal
        or state.playfield_shadow_color_ram != shadow
    ):
        state.playfield_color_ram[:] = normal
        state.playfield_shadow_color_ram[:] = shadow
        state.playfield_color_generation += 1


def init_fixed_playfield_color_ram(
    state: GameState, palette_words: tuple[int, ...],
) -> None:
    """Port init_display(0x10, 0x10), ROM 0x4367C-0x436B8."""
    if len(palette_words) != 128:
        raise ValueError("fixed playfield palette must contain 128 IRGB words")
    normal = [int(word) & 0xFFFF for word in palette_words]
    shadow = [palette_fade_word(word, 0x7000) for word in normal]
    state.playfield_color_base = normal[8]
    state.playfield_color_latch = normal[8]
    state.playfield_color_ram[:] = normal
    state.playfield_shadow_color_ram[:] = shadow
    state.playfield_color_generation += 1


def alpha_palette_words(state: GameState, attribute: int) -> tuple[int, ...]:
    """Resolve an alpha attribute word to its four live color-RAM entries."""
    bank = (attribute >> 14) & 1
    palette = (attribute >> 10) & 0x0F
    base = bank * 128 + palette * 4
    return tuple(state.alpha_color_ram[base:base + 4])


def alpha_palette_rgba(state: GameState, attribute: int) -> tuple[tuple[int, int, int, int], ...]:
    return tuple(_irgb_rgba(word) for word in alpha_palette_words(state, attribute))


def alpha_color_rgba(
    state: GameState, attribute: int, pixel: int,
) -> tuple[int, int, int, int]:
    return alpha_palette_rgba(state, attribute)[pixel & 3]


def alpha_word(attribute: int, glyph: int = 0) -> int:
    """Compose the hardware's attribute and ten-bit alpha glyph fields."""
    return (attribute & ALPHA_ATTRIBUTE_MASK) | (glyph & ALPHA_GLYPH_MASK)


def alpha_index(column: int, row: int) -> int:
    return row * ALPHA_COLUMNS + column


def write_alpha_glyphs(
    state: GameState, column: int, row: int, glyphs, attribute: int,
) -> None:
    """Write one clipped horizontal run of ROM glyph codes."""
    if not 0 <= row < ALPHA_ROWS:
        return
    for offset, glyph in enumerate(glyphs):
        x = column + offset
        if 0 <= x < ALPHA_COLUMNS:
            state.alpha_ram[alpha_index(x, row)] = alpha_word(
                attribute, 0 if glyph == 0x20 else glyph,
            )


# OS large_character_glyph_index_map, OS ROM 0x34A2. display_large_text uses
# the ASCII byte directly as an index; notably digits begin at quad 4 and space
# maps to quad 0. Reconstructing this as ASCII ranges corrupts level numbers.
_LARGE_GLYPH_INDEX_MAP = bytes.fromhex("""
00 00 00 00 00 00 00 00 32 00 00 00 00 00 00 00
00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
25 28 26 29 00 00 00 2E 00 00 00 00 2C 00 2B 00
00 01 02 03 04 05 06 07 08 09 2A 27 00 00 00 24
00 0A 0B 0C 0D 0E 0F 10 11 12 13 14 15 16 17 18
19 1A 1B 1C 1D 1E 1F 20 21 22 23 00 00 00 00 2D
00 0A 0B 0C 0D 0E 0F 10 11 12 13 14 15 16 17 18
19 1A 1B 1C 1D 1E 1F 20 21 22 23 00 00 00 00 00
""")


def _large_glyph_index(character: str) -> int:
    code = ord(character)
    return _LARGE_GLYPH_INDEX_MAP[code] if code < len(_LARGE_GLYPH_INDEX_MAP) else 0


def write_alpha_large_text(
    state: GameState, column: int, row: int, text: str, attribute: int,
) -> int:
    """Port OS display_large_text 0x31D2 for one descriptor."""
    cursor = column
    for character in text.upper():
        cursor += write_alpha_large_char(
            state, cursor, row, character, attribute,
        )
    return cursor - column


def write_alpha_large_char(
    state: GameState, column: int, row: int, character: str, attribute: int,
) -> int:
    """Write one OS large character and return its one- or two-cell advance."""
    cell_attribute = (attribute & ALPHA_ATTRIBUTE_MASK) | 0x0100
    glyphs = (
        (0x1C, 0x1E, 0xFC, 0x7E)
        if character == "\b"
        else _LARGE_GLYPH_QUADS[_large_glyph_index(character.upper())]
    )
    cells = [(0, 0, glyphs[0]), (0, 1, glyphs[1])]
    width = 1
    if glyphs[2] or glyphs[3]:              # 0x3280 tst.w (a2)
        cells.extend(((1, 0, glyphs[2]), (1, 1, glyphs[3])))
        width = 2
    for dx, dy, glyph in cells:
        if 0 <= column + dx < ALPHA_COLUMNS and 0 <= row + dy < ALPHA_ROWS:
            state.alpha_ram[alpha_index(column + dx, row + dy)] = alpha_word(
                cell_attribute, glyph | 0x0100,
            )
    return width


def write_alpha_text(
    state: GameState, column: int, row: int, text: str, attribute: int,
) -> None:
    write_alpha_glyphs(state, column, row, (ord(ch) for ch in text), attribute)


def write_alpha_decimal(
    state: GameState, column: int, row: int, value: int, width: int,
    attribute: int,
) -> None:
    text = str(max(0, int(value)))[-width:].rjust(width)
    write_alpha_text(state, column, row, text, attribute)


def fill_alpha_rect(
    state: GameState, column: int, row: int, width: int, height: int,
    word: int,
) -> None:
    """Fill a clipped alpha rectangle with one complete VRAM word."""
    left = max(0, column)
    right = min(ALPHA_COLUMNS, column + width)
    top = max(0, row)
    bottom = min(ALPHA_ROWS, row + height)
    if left >= right or top >= bottom:
        return
    values = [word & 0xFFFF] * (right - left)
    for y in range(top, bottom):
        start = alpha_index(left, y)
        state.alpha_ram[start:start + len(values)] = values


def clear_alpha_visible(state: GameState) -> None:
    fill_alpha_rect(state, 0, 0, ALPHA_VISIBLE_COLUMNS, ALPHA_ROWS, 0)


def maze_show(state: GameState) -> None:
    """Port maze_show 0x4526A: reveal the maze while preserving its info panel."""
    fill_alpha_rect(state, 0, 0, 29, ALPHA_ROWS, 0)
    fill_alpha_rect(state, 42, 0, ALPHA_COLUMNS - 42, ALPHA_ROWS, 0)


def _irgb_rgba(word: int) -> tuple[int, int, int, int]:
    """MAME's 4-bit intensity × channel conversion, with 8-bit truncation."""
    intensity = ((word >> 12) & 0x0F) * 17
    channels = (
        ((word >> 8) & 0x0F) * 17,
        ((word >> 4) & 0x0F) * 17,
        (word & 0x0F) * 17,
    )
    return tuple((channel * intensity) >> 8 for channel in channels) + (255,)
