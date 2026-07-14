#!/usr/bin/env python3
"""Generate a small radare2 loader from the symbols in gauntlet.r2."""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path


SETTINGS = (
    "e io.va=true",
    "e anal.arch=m68k",
    "e asm.arch=m68k",
    "e asm.cpu=68010",
    "e asm.bits=32",
    "e cfg.bigendian=true",
)
MAPS = (
    "o row9.bin 0x000000 r-x",
    "o row10.bin 0x038000 r-x",
    "o row76.bin 0x040000 r-x",
)
CANONICAL_OS_NAMES = {
    0x0FCA: "run_color_test",
    0x129A: "os_selftest_loop",
    0x17D4: "run_alpha_test",
    0x1B20: "run_motion_object_test",
    0x21A0: "validate_game_rom",
    0x0A2C: "mem_test_short",
    0x0A6A: "mem_test_full",
    0x0C52: "display_working_ram_error",
    0x3122: "start_text_line_rotation",
    0x3130: "init_fullscreen_text_scroll",
    0x3156: "start_progressive_text_clear",
    0x3162: "start_blink_text",
    0x3168: "start_timed_text",
    0x316C: "start_progressive_text",
    0x32DA: "display_large_decimal_value",
    0x3310: "display_large_hex_value",
    0x332A: "display_large_text_at",
    0x3346: "clear_large_text",
    0x3804: "check_and_deduct_credits",
    0x3BE8: "update_active_player_time_stats",
    0x3F68: "rank_high_score",
    0x401A: "activate_player_time_tracking",
    0x4038: "record_player_session_histogram",
    0x41C8: "send_sound_command_wait",
    0x41CC: "try_send_sound_command",
    0x427A: "sound_receive_irq_body",
    0x5454: "run_statistics_screens",
    0x58C6: "run_game_options",
}
ADDITIONAL_OS_FUNCTIONS = {
    0x03B6: "normal_boot_spare_test_done",
    0x03C4: "normal_boot_spare_error_ack",
    0x0424: "normal_boot_color_test_done",
    0x04A4: "normal_boot_playfield_test_done",
    0x0512: "normal_boot_alpha_test_done",
    0x0582: "normal_boot_mob_test_done",
    0x0652: "selftest_spare_test_done",
    0x0660: "selftest_spare_error_ack",
    0x067C: "selftest_color_test_done",
    0x06A6: "selftest_playfield_test_done",
    0x06D0: "selftest_alpha_test_done",
    0x06FC: "selftest_mob_test_done",
    0x08EC: "boot_postcheck_dispatch",
    0x0A42: "mem_test_short_walk_ones",
    0x0A52: "mem_test_short_walk_zeroes",
    0x0A62: "mem_test_short_done",
    0x0A7A: "mem_test_full_walk_ones_highbit",
    0x0A84: "mem_test_full_walk_zeroes_highbit",
    0x0A8E: "mem_test_full_walk_ones_lowbit",
    0x0A98: "mem_test_full_walk_zeroes_lowbit",
    0x0AA2: "mem_test_full_restore_ones_highbit",
    0x0AAC: "mem_test_full_restore_ones_lowbit",
    0x0AB6: "mem_test_full_fill_ones",
    0x0AC2: "mem_test_full_restore_zeroes_highbit",
    0x0ACC: "mem_test_full_restore_zeroes_lowbit",
    0x0AD6: "mem_test_full_toggle_words",
    0x0AE0: "mem_test_full_done",
    0x0D26: "game_descriptor_ram_test",
    0x0D3A: "game_descriptor_ram_test_done",
    0x0D7A: "game_rom_checksum_error",
    0x0EEE: "selftest_watchdog_reset_trap",
    0x0F04: "playfield_add_word_test_range",
    0x0F7E: "copy_test_tile_rows_to_alpha",
    0x113E: "read_debounced_input",
    0x11FC: "color_test_palette_init",
    0x1228: "selftest_load_control_labels",
    0x169C: "load_color_test_palettes",
    0x16F6: "copy_cstring",
    0x1704: "reset_sound_test_interface",
    0x1732: "fill_incrementing_words",
    0x1758: "display_standard_large_glyph_range",
    0x179E: "display_rotated_large_glyph_range",
    0x1A34: "run_switch_test",
    0x2190: "wait_os_vblank",
    0x226A: "display_next_test_prompt",
    0x229C: "run_sound_test",
    0x4198: "send_sound_command_register",
    0x27AC: "send_sound_test_command_wait",
    0x27F4: "wait_sound_test_delay_or_abort",
    0x2828: "display_ram_error_detail",
    0x28CA: "display_two_byte_hex_pair",
    0x2D14: "rotate_text_line_forward",
    0x2D18: "rotate_text_line_forward_register",
    0x2D74: "rotate_text_line_reverse",
    0x2D78: "rotate_text_line_reverse_register",
    0x2DDE: "scroll_alpha_surface_one_step",
    0x2E3E: "display_text_register",
    0x2F3C: "draw_string_register",
    0x2FB2: "draw_text_effect_next_char_stack_veneer",
    0x2FBE: "draw_text_effect_next_char",
    0x3018: "clear_text_effect_next_char_stack_veneer",
    0x3020: "clear_text_effect_next_char",
    0x304E: "write_alpha_char_register",
    0x3088: "clear_text_descriptor_chain_stack_veneer",
    0x308C: "clear_text_descriptor_chain",
    0x3166: "unused_text_effect_noop",
    0x3172: "allocate_text_effect",
    0x324E: "render_large_glyph_register",
    0x355C: "reset_text_effects",
    0x3D18: "write_game_config",
    0x4674: "eeprom_decode_block",
    0x467C: "eeprom_decode_block_to",
    0x4770: "eeprom_clear_statistics",
    0x4784: "eeprom_clear_configuration",
    0x47AC: "eeprom_request_write_register",
    0x47B8: "eeprom_clear_difficulty_rows",
    0x4896: "wait_vblank_counter_ticks",
    0x48B8: "display_text_set_cursor",
    0x4912: "display_text_at_cursor",
    0x493C: "display_decimal_at_cursor",
    0x4966: "display_decimal_set_cursor",
    0x49C8: "option_record_present",
    0x49E8: "find_option_record",
    0x4A44: "render_option_record",
    0x4B66: "render_option_record_page",
    0x4BE6: "display_next_screen_prompt",
    0x4C38: "init_operator_mob_display",
    0x4C66: "run_statistics_histograms",
    0x4FA0: "display_statistics_play_time",
    0x5098: "run_statistics_summary",
    0x522A: "run_game_settings_bit_editor",
    0x5392: "draw_game_settings_bits",
    0x5476: "run_option_descriptor_editor",
    0x593C: "run_coin_options",
    0x8000: "legacy_monster_object_update",
    0x8702: "legacy_monster_choose_direction",
    0x89AA: "legacy_four_cell_occupied_test",
    0x89E6: "legacy_position_in_active_bounds",
    0x8A12: "legacy_set_direction_from_delta",
    0x8AE8: "legacy_moblist_insert",
    0x8C36: "legacy_move_mob_slot",
    0x8C70: "legacy_moblist_remove_and_clear",
    0x8D00: "legacy_moblist_unlink",
    0x8F38: "legacy_probe_up",
    0x9006: "legacy_probe_down",
    0x90D2: "legacy_probe_left",
    0x9192: "legacy_probe_right",
    0x9284: "legacy_recursive_path_move",
    0x9864: "legacy_test_actor_contact_a",
    0x9880: "legacy_test_actor_contact_b",
    0x989C: "legacy_probe_vertical_triplet_up",
    0x98D8: "legacy_probe_vertical_triplet_down",
    0x9914: "legacy_test_cell_proximity",
    0x99A0: "legacy_probe_horizontal_triplet_left",
    0x99D8: "legacy_probe_horizontal_triplet_right",
}
CANONICAL_FLAG_NAMES = {
    0x579E2: "death_potion_popup_type_table",
    0x904B3A: "ram.player_death_damage_counter",
    0x905F80: "ram.priority_bucket_heads",
    0x905F82: "ram.priority_bucket_heads_tail",
    0x905F6D: "ram.secret_saved_supershot",
    0x904F02: "ram.fullscreen_scroll_active",
    0x904F06: "ram.fullscreen_scroll_offset",
    0x904F7A: "ram.input_previous_raw",
    0x904F82: "ram.input_debounced",
    0x904F8A: "ram.input_source_ptr",
    0x904F44: "ram.highscore_work_buffer",
    0x904F4B: "ram.active_player_time_mask",
    0x904F4C: "ram.player_time_last_vblank",
    0x904F50: "ram.player_time_counters",
    0x40070: "game.default_settings",
    0x904F78: "ram.operator_cursor0",
    0x904F79: "ram.operator_cursor1",
    0x904FC0: "ram.eeprom_error_count",
    0x904FFA: "ram.eeprom_init_timeout_counter_byte",
}

# OS-specific aliases are emitted even when the game uses the same spare-video
# address for another purpose after handoff.  Sizes describe the exact object
# or diagnostic span used by row9.bin, not the later game lifetime.
ADDITIONAL_OS_FLAGS = {
    0x0C86: ("osdata.working_ram_error_text", 0x12),
    0x0F1C: ("osdata.rom_error_descriptor_pointer_tables", 0x62),
    0x2A48: ("osdata.number_format_bit_masks", 0x16),
    0x2C16: ("osdata.text_effect_dispatch_offsets", 0x0C),
    0x33D2: ("osdata.large_character_tile_quads", 0xD0),
    0x34A2: ("osdata.large_character_clear_maps", 0x80),
    0x44BE: ("osdata.eeprom_redundancy_probe_order", 0x0C),
    0x4736: ("osdata.eeprom_bit_index_map", 0x10),
    0x599A: ("osdata.motion_test_lookup_tables", 0x80),
    0x5A1A: ("osdata.diagnostic_pointer_and_endpoint_tables", 0x30),
    0x5A4A: ("osdata.selftest_descriptor_and_string_stream", 0x6CA),
    0x6114: ("osdata.color_name_pointer_table", 0x20),
    0x6134: ("osdata.display_test_selection_tables", 0x40),
    0x6174: ("osdata.display_test_palette_words", 0x10),
    0x6184: ("osdata.color_test_palette_source_prefix", 0x4A0),
    0x6624: ("osdata.palette_and_rom_error_descriptor_overlap", 0x160),
    0x6784: ("osdata.rom_error_descriptor_stream", 0x202),
    0x6986: ("osdata.coin_counter_decode_table", 8),
    0x698E: ("osdata.game_config_descriptor_table", 0x1A),
    0x69A8: ("osdata.session_difficulty_factors", 4),
    0x69AC: ("osdata.statistics_prompt_strings", 0x9A),
    0x6A46: ("osdata.statistics_summary_table", 0xD2),
    0x6B18: ("osdata.statistics_error_and_navigation_descriptors", 0x4E),
    0x6B66: ("osdata.operator_more_marker_variants", 0x24),
    0x6B8A: ("osdata.operator_ui_palette", 0x10),
    0x6B9A: ("osdata.operator_option_descriptor_stream", 0x1A0),
    0x6D3A: ("osdata.built_in_coin_option_stream", 0x6E),
    0x860C: ("legacydata.object_motion_tables", 0xF6),
    0x8A64: ("legacydata.direction_route_tables", 0x84),
    0x8B9E: ("legacydata.mob_bucket_tables", 0x98),
    0x8D86: ("legacydata.path_probe_tables", 0x1B2),
    0x9252: ("legacydata.recursive_move_tables", 0x32),
    0x9A10: ("legacydata.game_option_stream", 0x1C8),
    0x9BD8: ("legacydata.level_display_tables", 0x144),
    0x9D1C: ("legacydata.status_text_descriptors", 0x304),
    0xA020: ("legacydata.gameplay_numeric_tables_a", 0x1D1C),
    0xBD3C: ("legacydata.factory_high_scores", 0x140),
    0xBE7C: ("legacydata.high_score_text", 0x7A),
    0xBEF6: ("legacydata.name_entry_and_gameplay_tables", 0x24A),
    0xC140: ("legacydata.tutorial_descriptor_stream", 0x290),
    0xC3D0: ("legacydata.gameplay_numeric_tables_b", 0x109A),
    0xD46A: ("legacydata.hint_and_legend_stream", 0xC1C),
    0xE086: ("legacydata.legend_and_credit_text", 0x3CA),
    0xE450: ("legacydata.descriptor_and_tile_tables", 0xCF0),
    0xF140: ("legacydata.palette_and_graphics_tables", 0x8BA),
    0x803000: ("hw.input_word_array", 8),
    0x80300E: ("hw.sound_response_word", 2),
    0x803120: ("hw.board_enable_latch", 2),
    0x80312E: ("hw.sound_reset_control", 2),
    0x803170: ("hw.sound_command_word", 2),
    0x901FFE: ("vram.playfield_last_word", 2),
    0x903FFE: ("vram.mob_last_word", 2),
    0x904004: ("ram.os_vblank_occurred", 2),
    0x904012: ("ram.sound_test_status_value", 2),
    0x90403E: ("ram.selftest_button0_label", 0x1A),
    0x904058: ("ram.selftest_button1_label", 0x1A),
    0x904072: ("ram.selftest_joystick_label", 0x1A),
    0x90408C: ("ram.motion_test_object_index", 2),
    0x90408E: ("ram.motion_test_pattern", 2),
    0x904F00: ("ram.text_repeat_bias", 2),
    0x904F04: ("ram.vblank_sync", 2),
    0x904F0A: ("ram.fullscreen_scroll_interval", 2),
    0x904F44: ("ram.highscore_work_buffer", 7),
    0x904F4B: ("ram.active_player_time_mask", 1),
    0x904F4C: ("ram.player_time_last_vblank", 4),
    0x904F78: ("ram.operator_cursor0", 1),
    0x904F79: ("ram.operator_cursor1", 1),
    0x904F7A: ("ram.input_previous_raw", 8),
    0x904F82: ("ram.input_debounced", 8),
    0x904FEB: ("ram.sound_status_poll_busy_count", 1),
    0x904FFE: ("vram.spare_last_word", 2),
    0x905E80: ("vram.alpha_color_test_bottom_row", 0x4A),
    0x905FFE: ("vram.alpha_last_word", 2),
    0x906D00: ("diag.working_ram_error_text", 0x22),
    0x910002: ("vram.color_alpha_entry1", 2),
    0x910004: ("vram.color_alpha_entry2", 2),
    0x910006: ("vram.color_alpha_entry3", 2),
    0x910008: ("vram.color_alpha_entry4", 2),
    0x91000A: ("vram.color_alpha_entry5", 2),
    0x91000C: ("vram.color_alpha_entry6", 2),
    0x91000E: ("vram.color_alpha_entry7", 2),
    0x91051E: ("vram.color_pf_entry15", 2),
    0x9107FE: ("vram.color_last_word", 2),
}


def canonicalize_function(line: str, canonical_names: dict[int, str]) -> str:
    match = re.match(r"af\+ (0x[0-9A-Fa-f]+) \S+", line)
    if not match:
        return line
    address = int(match.group(1), 16)
    name = canonical_names.get(address)
    return f"af+ 0x{address:x} {name}" if name else line


def canonicalize_flag(line: str, canonical_names: dict[int, str]) -> str:
    match = re.match(r"f \S+ (\S+) (0x[0-9A-Fa-f]+)$", line)
    if not match:
        return line
    address = int(match.group(2), 16)
    name = canonical_names.get(address)
    return f"f {name} {match.group(1)} 0x{address:08x}" if name else line


def documented_game_function_map(function_index: str) -> dict[int, str]:
    # Stop after the first backticked name, not after the whole cell: many
    # canonical rows contain slash-separated aliases in the same cell.
    row = re.compile(r"^\| 0x([0-9A-Fa-f]+) \| `([^`]+)`", re.MULTILINE)
    by_address: dict[int, str] = {}
    for address_text, name in row.findall(function_index):
        address = int(address_text, 16)
        if 0x40000 <= address <= 0x5FFFF:
            by_address.setdefault(address, name)
    return by_address


def generated_text(source: str, function_index: str) -> str:
    game_functions = documented_game_function_map(function_index)
    canonical_names = {
        **CANONICAL_OS_NAMES,
        **ADDITIONAL_OS_FUNCTIONS,
        **game_functions,
    }
    function_block = source.split("# functions\n", 1)[1].split("# registers\n", 1)[0]
    functions = [
        canonicalize_function(line, canonical_names)
        for line in function_block.splitlines()
        if line.startswith("af+")
    ]
    existing_function_addresses = {
        int(match.group(1), 16)
        for line in functions
        if (match := re.match(r"af\+ (0x[0-9A-Fa-f]+) ", line))
    }
    functions.extend(
        f"af+ 0x{address:04x} {name}"
        for address, name in sorted(ADDITIONAL_OS_FUNCTIONS.items())
        if address not in existing_function_addresses
    )
    functions.extend(
        f"af+ 0x{address:05x} {name}"
        for address, name in sorted(game_functions.items())
    )

    flag_block = source.split("# flags\n", 1)[1].split("# meta\n", 1)[0]
    # The export begins with an obsolete ARM register namespace. Start at the
    # real function namespace, then retain every named symbol in later spaces.
    flag_block = flag_block.split("fs functions\n", 1)[1]
    flags = [
        canonicalize_flag(line[1:], {**canonical_names, **CANONICAL_FLAG_NAMES})
        for line in flag_block.splitlines()
        if line.startswith("'f ")
    ]
    existing_flag_names = {
        match.group(1)
        for line in flags
        if (match := re.match(r"f (\S+) ", line))
    }
    flags.extend(
        f"f {name} {size} 0x{address:08x}"
        for address, (name, size) in sorted(ADDITIONAL_OS_FLAGS.items())
        if name not in existing_flag_names
    )

    lines = [
        "# Generated by doc/generate_r2_loader.py; do not edit by hand.",
        *MAPS,
        # Opening a raw file resets some decoding settings in r2 6.1.8.
        *SETTINGS,
        "fs functions",
        *functions,
        *flags,
        "fs *",
        "s 0x040000",
        "",
    ]
    return "\n".join(lines)


def runtime_check(root: Path, expected_function_count: int) -> None:
    command = [
        "r2", "-q", "-n", "-e", "scr.color=0",
        "-c", ". doc/gauntlet_loader.r2",
        "-c", "e asm.arch; e asm.cpu; e asm.bits; e cfg.bigendian; oj; om; f~m2mainloop; aflc",
        "-c", "q", "malloc://1",
    ]
    result = subprocess.run(command, cwd=root, text=True, capture_output=True)
    combined = result.stdout + result.stderr
    bad = re.search(r"(?im)^(?:ERROR|FATAL|Invalid|Cannot|Unknown).*", combined)
    if result.returncode or bad:
        raise SystemExit(
            "radare2 loader regression failed:\n" + (bad.group(0) if bad else combined)
        )
    required = (
        "m68k", "68010", "32", "true", "row9.bin", "row10.bin",
        "row76.bin", "m2mainloop", "r-x",
    )
    missing = [item for item in required if item not in combined]
    if missing:
        raise SystemExit(f"radare2 loader output missing: {', '.join(missing)}\n{combined}")
    if not re.search(rf"(?m)^{expected_function_count}$", combined):
        raise SystemExit(
            f"radare2 loader did not create {expected_function_count} analysis functions\n{combined}"
        )
    print(
        "gauntlet_loader.r2: zero-error load; 3 ROM maps; "
        f"m68k/68010/32-bit/big-endian; {expected_function_count} functions"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--run-check", action="store_true")
    args = parser.parse_args()

    here = Path(__file__).resolve().parent
    root = here.parent
    output = here / "gauntlet_loader.r2"
    legacy = (root / "gauntlet.r2").read_text()
    function_index = (here / "07_function_index.md").read_text()
    expected = generated_text(legacy, function_index)
    expected_function_count = len(re.findall(r"(?m)^af\+ ", expected))
    if args.check:
        if output.read_text() != expected:
            raise SystemExit("gauntlet_loader.r2 is stale; regenerate it")
        print("gauntlet_loader.r2: generated content is current")
    else:
        output.write_text(expected)
        print(f"wrote {output}")
    if args.run_check:
        runtime_check(root, expected_function_count)


if __name__ == "__main__":
    main()
