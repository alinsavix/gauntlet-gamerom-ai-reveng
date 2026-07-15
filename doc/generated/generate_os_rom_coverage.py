#!/usr/bin/env python3
"""Produce a byte-exact code/data/fill account of the 64 KiB OS ROM."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


EXPECTED_SHA1 = "6e0d2026317e4a050fd79aac24ee0a644bf5a836"
ROM_SIZE = 0x10000

# Disjoint architectural regions.  These rows account for every byte exactly
# once; the coverage report below further splits the two mixed code/data
# regions according to targeted radare2 instruction analysis.
REGIONS = (
    (0x0000, 0x0100, "m68010_vector_table", "64 big-endian longword vector slots", "data", "Verified"),
    (0x0100, 0x01D8, "os_api_jump_table_1", "36 six-byte JMP absolute veneers", "code", "Verified"),
    (0x01D8, 0x01F8, "os_api_data_address_table", "eight big-endian hardware/RAM pointers", "data", "Verified"),
    (0x01F8, 0x0200, "api_alignment_zero_fill_1f8", "eight zero bytes", "fill", "Verified"),
    (0x0200, 0x022A, "os_api_jump_table_2a", "seven six-byte JMP absolute veneers", "code", "Verified"),
    (0x022A, 0x0230, "unused_api_slot_ff_fill", "one six-byte 0xFF-filled API slot", "fill", "Verified"),
    (0x0230, 0x027E, "os_api_jump_table_2b", "thirteen six-byte JMP absolute veneers", "code", "Verified"),
    (0x027E, 0x0300, "preimplementation_zero_fill", "130 zero bytes before the implementation image", "fill", "Verified"),
    (0x0300, 0x599A, "active_os_implementation", "active OS 68010 code with embedded constants/tables", "mixed", "Verified"),
    (0x599A, 0x6DA8, "active_os_data_image", "diagnostic/operator tables, descriptor chains, strings, and palette source data", "data", "Verified"),
    (0x6DA8, 0x8000, "intermodule_zero_fill", "zero fill between active OS and retained module", "fill", "Verified"),
    (0x8000, 0x9A10, "retained_game_support_code", "runtime-dead 68010 game-support code with five embedded data islands", "mixed", "Strong inference"),
    (0x9A10, 0xF9FA, "retained_game_support_data", "runtime-dead older-game tables, text, palettes, and graphics data", "data", "Strong inference"),
    (0xF9FA, 0x10000, "trailing_zero_fill", "zero fill to end of ROM", "fill", "Verified"),
)

# Exact embedded-data islands interrupting the retained module's code.  Their
# formats are derived from the instructions that index them; original symbol
# names are absent from the shipped artifact.
LEGACY_DATA_ISLANDS = (
    (0x860C, 0x8702, "legacy_object_motion_tables", "word offsets, longword picture values, packed MOB attributes, and byte direction records"),
    (0x8A64, 0x8AE8, "legacy_direction_route_tables", "eight-direction word/byte lookup records and movement masks"),
    (0x8B9E, 0x8C36, "legacy_mob_bucket_tables", "MOB bucket/link constants and insertion-order records"),
    (0x8D86, 0x8F38, "legacy_path_probe_tables", "signed neighbor offsets, direction maps, and path-probe constants"),
    (0x9252, 0x9284, "legacy_recursive_move_tables", "neighbor-order and recursive path-selection constants"),
)

ACTIVE_INLINE_DATA = (
    (0x0C86, 0x0C98, "working_ram_error_text", "NUL-terminated early-boot diagnostic string"),
    (0x0F1C, 0x0F7E, "rom_error_descriptor_pointer_tables", "three indexed tables of 16-bit display-descriptor addresses used for ROM lane/socket errors"),
    (0x2A48, 0x2A5E, "number_format_bit_masks", "eleven words selected by the generic numeric formatter's mode index"),
    (0x2C16, 0x2C22, "text_effect_dispatch_offsets", "six signed word offsets relative to 0x2C16"),
    (0x33D2, 0x34A2, "large_character_tile_quads", "52 four-byte large-character tile-number records"),
    (0x34A2, 0x3522, "large_character_clear_maps", "large-character clearing/width lookup records"),
    (0x44BE, 0x44CA, "eeprom_redundancy_probe_order", "word seed followed by signed byte offsets for redundant-record bit probing"),
    (0x4736, 0x4746, "eeprom_bit_index_map", "sixteen signed byte mappings from packed bit index to EEPROM record bit"),
)

ACTIVE_DATA_GROUPS = (
    (0x599A, 0x5A1A, "motion_test_lookup_tables", "palette words, position/delta words, and 8x8 multiplication bytes for the Motion Object test"),
    (0x5A1A, 0x5A4A, "diagnostic_pointer_and_endpoint_tables", "error-descriptor pointers plus MOB/alpha/input hardware endpoints"),
    (0x5A4A, 0x6114, "selftest_descriptor_and_string_stream", "control labels and chained display descriptors/strings for RAM, switch, display, MOB, and sound tests"),
    (0x6114, 0x6134, "color_name_pointer_table", "eight big-endian pointers to color-name strings, including a null terminator"),
    (0x6134, 0x6174, "display_test_selection_tables", "signed word selection/enable matrices used by self-test and Motion Object test"),
    (0x6174, 0x6184, "display_test_palette_words", "eight palette words for convergence/display tests"),
    (0x6184, 0x6624, "color_test_palette_source_prefix", "packed color-test palette words copied to MOB/shadow/playfield color RAM"),
    (0x6624, 0x6784, "palette_and_rom_error_descriptor_overlap", "tail of the 768-word palette source, simultaneously structured as ROM-error display descriptors and strings"),
    (0x6784, 0x6986, "rom_error_descriptor_stream", "remaining per-socket ROM error descriptors, one-character lane labels, and strings"),
    (0x6986, 0x698E, "coin_counter_decode_table", "eight packed 2-bit coin-counter decode bytes"),
    (0x698E, 0x69A8, "game_config_descriptor_table", "thirteen two-byte packed configuration descriptors"),
    (0x69A8, 0x69AC, "session_difficulty_factors", "four one-byte histogram weighting factors"),
    (0x69AC, 0x6A46, "statistics_prompt_strings", "NUL-terminated histogram/navigation labels and short display fragments"),
    (0x6A46, 0x6B18, "statistics_summary_table", "title, eleven longword string pointers, and NUL-terminated summary labels"),
    (0x6B18, 0x6B66, "statistics_error_and_navigation_descriptors", "EEPROM-error descriptor plus clear/histogram navigation strings"),
    (0x6B66, 0x6B8A, "operator_more_marker_variants", "three glyph-decorated MORE strings used by option navigation"),
    (0x6B8A, 0x6B9A, "operator_ui_palette", "eight palette words for operator Motion Objects"),
    (0x6B9A, 0x6D3A, "operator_option_descriptor_stream", "display descriptors and strings for save/cancel, raw-bit, game, and coin editors"),
    (0x6D3A, 0x6DA8, "built_in_coin_option_stream", "tagged multiplier/bonus-adder prompts and NUL-terminated choices including Free Play"),
)

# Coarse but exact semantic subregions of the retained data image.  This code
# is unreachable in the supplied Gauntlet II configuration; the row names
# describe encoded formats/content without claiming live ownership.
LEGACY_DATA_GROUPS = (
    (0x9A10, 0x9BD8, "legacy_game_option_stream", "tagged option prompts and NUL-terminated choice strings"),
    (0x9BD8, 0x9D1C, "legacy_level_display_tables", "level/status constants, glyph maps, and small animation lookup tables"),
    (0x9D1C, 0xA020, "legacy_status_text_descriptors", "display descriptors, treasure/coin/continue strings, pointer arrays, and status constants"),
    (0xA020, 0xBD3C, "legacy_gameplay_numeric_tables_a", "word/byte gameplay, movement, object, animation, and tile lookup data"),
    (0xBD3C, 0xBE7C, "legacy_factory_high_scores", "four 10-entry tables of {score longword, three initials bytes, pad byte}"),
    (0xBE7C, 0xBEF6, "legacy_high_score_text", "display descriptors and NUL-terminated score/name-entry strings"),
    (0xBEF6, 0xC140, "legacy_name_entry_and_gameplay_tables", "name-entry glyph/control stream followed by word/byte gameplay lookup tables"),
    (0xC140, 0xC3D0, "legacy_tutorial_descriptor_stream", "blank/text display descriptors, tutorial strings, and descriptor pointer table"),
    (0xC3D0, 0xD46A, "legacy_gameplay_numeric_tables_b", "object, animation, maze-display, and tile lookup data"),
    (0xD46A, 0xE086, "legacy_hint_and_legend_stream", "NUL-terminated hint/legend text, display descriptors, and pointer tables"),
    (0xE086, 0xE450, "legacy_legend_and_credit_text", "legend labels, item-name pointer tables, credit descriptors, and credit strings"),
    (0xE450, 0xF140, "legacy_descriptor_and_tile_tables", "display descriptor chains plus gameplay, animation, and tile-number lookup data"),
    (0xF140, 0xF9FA, "legacy_palette_and_graphics_tables", "palette words and packed graphics/tile pattern data"),
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def analyze(root: Path, address: int, name: str) -> dict[str, object]:
    command = [
        "r2", "-q", "-n", "-e", "scr.color=0", "-e", "asm.flags=false",
        "-e", "asm.sub.names=false", "-i", "doc/gauntlet_loader.r2",
        "-c", f"af- 0x{address:x}; af @ 0x{address:x}; s 0x{address:x}; pdfj",
        "-c", "q", "malloc://1",
    ]
    completed = subprocess.run(command, cwd=root, text=True, capture_output=True)
    errors = [line for line in completed.stderr.splitlines() if line.startswith(("ERROR", "FATAL"))]
    if completed.returncode or errors:
        return {"address": address, "name": name, "error": "; ".join(errors) or f"r2 exit {completed.returncode}"}
    try:
        return {"address": address, "name": name, "body": json.loads(completed.stdout)}
    except json.JSONDecodeError as exc:
        return {"address": address, "name": name, "error": f"invalid analysis JSON: {exc}"}


def checked_partition(rows: tuple[tuple[object, ...], ...], start: int, end: int, label: str) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    cursor = start
    for row in rows:
        row_start, row_end = int(row[0]), int(row[1])
        if row_start != cursor or row_end <= row_start:
            failures.append({"address": f"0x{cursor:04X}", "issue": f"{label} has gap/overlap at 0x{row_start:04X}"})
        cursor = row_end
    if cursor != end:
        failures.append({"address": f"0x{cursor:04X}", "issue": f"{label} ends at 0x{cursor:04X}, expected 0x{end:04X}"})
    return failures


def generated(root: Path) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    doc = root / "doc"
    rom = (root / "row9.bin").read_bytes()
    failures: list[dict[str, str]] = []
    if len(rom) != ROM_SIZE:
        failures.append({"address": "ROM", "issue": f"size {len(rom)} != {ROM_SIZE}"})
    if hashlib.sha1(rom).hexdigest() != EXPECTED_SHA1:
        failures.append({"address": "ROM", "issue": "SHA-1 mismatch"})
    failures += checked_partition(REGIONS, 0, ROM_SIZE, "top-level regions")
    failures += checked_partition(ACTIVE_DATA_GROUPS, 0x599A, 0x6DA8, "active data groups")
    failures += checked_partition(LEGACY_DATA_GROUPS, 0x9A10, 0xF9FA, "legacy data groups")

    # The two independently generated control-transfer inventories are the
    # reachability proof for the retained module in this supplied game image.
    for filename in ("os_control_targets.csv", "control_targets.csv"):
        for row in read_csv(doc / "generated" / filename):
            for text in re.findall(r"0x([0-9A-Fa-f]+)", row.get("target", "")):
                target = int(text, 16)
                if 0x8000 <= target < 0x9A10:
                    failures.append({"address": f"0x{target:04X}", "issue": f"incoming control transfer reported by {filename}"})

    for start, end, _, _, kind, _ in REGIONS:
        block = rom[start:end]
        if kind == "fill" and start == 0x022A and block != b"\xFF" * len(block):
            failures.append({"address": f"0x{start:04X}", "issue": "expected solid 0xFF fill"})
        elif kind == "fill" and start != 0x022A and any(block):
            failures.append({"address": f"0x{start:04X}", "issue": "expected solid zero fill"})

    callable_rows = read_csv(doc / "generated" / "os_callable_contracts.csv")
    active_entries = [
        (int(row["address"], 16), row["name"])
        for row in callable_rows
        if row["entry_kind"] in {"implementation", "computed_dispatch"}
    ]
    legacy_entries = [
        (int(row["address"], 16), row["name"])
        for row in read_csv(doc / "generated" / "os_legacy_module_contracts.csv")
    ]
    residue_entries = [
        (int(row["address"], 16), row["name"])
        for row in read_csv(doc / "generated" / "os_residue_contracts.csv")
    ]
    with ThreadPoolExecutor(max_workers=8) as executor:
        analyses = list(executor.map(lambda item: analyze(root, *item), active_entries + legacy_entries + residue_entries))

    code: set[int] = set()
    for result in analyses:
        if "error" in result:
            failures.append({"address": f"0x{int(result['address']):04X}", "issue": str(result["error"])})
            continue
        body = result["body"]
        assert isinstance(body, dict)
        for op in body.get("ops", []):
            address = int(op.get("addr", -1)); size = int(op.get("size", 0))
            if size <= 0:
                failures.append({"address": f"0x{address:04X}", "issue": "zero-sized analyzed instruction"})
                continue
            # radare2's bounded computed-dispatch case analysis inherits a
            # spurious block at address zero from the parent indirect JMP.
            # The case contracts independently bound their real blocks; only
            # bytes in the two declared implementation regions belong here.
            if 0x0300 <= address < 0x599A or 0x8000 <= address < 0x9A10:
                code.update(range(address, min(address + size, ROM_SIZE)))

    # Fixed JMP veneers are executable even though they are not analyzed as
    # ordinary function bodies in the implementation closure.
    for row in callable_rows:
        if row["entry_kind"] == "api_veneer":
            start = int(row["address"], 16)
            code.update(range(start, start + 6))

    island_bytes = {address for start, end, *_ in LEGACY_DATA_ISLANDS for address in range(start, end)}
    if code & island_bytes:
        address = min(code & island_bytes)
        failures.append({"address": f"0x{address:04X}", "issue": "legacy code analysis overlaps declared data island"})
    for address in code:
        if not (0x0100 <= address < 0x01D8 or 0x0200 <= address < 0x022A or 0x0230 <= address < 0x027E or 0x0300 <= address < 0x599A or 0x8000 <= address < 0x9A10):
            failures.append({"address": f"0x{address:04X}", "issue": "instruction byte outside executable regions"})
            break

    declared_mixed_data: dict[int, str] = {}
    for start, end, name, _ in (*ACTIVE_INLINE_DATA, *LEGACY_DATA_ISLANDS):
        for address in range(start, end):
            if address in declared_mixed_data:
                failures.append({"address": f"0x{address:04X}", "issue": "overlapping mixed-region data declarations"})
            declared_mixed_data[address] = name
    for start, end in ((0x0300, 0x599A), (0x8000, 0x9A10)):
        for address in range(start, end):
            if address not in code and address not in declared_mixed_data:
                failures.append({"address": f"0x{address:04X}", "issue": "mixed-region byte is neither analyzed code nor named data"})
                break
            if address in code and address in declared_mixed_data:
                failures.append({"address": f"0x{address:04X}", "issue": "mixed-region byte is both analyzed code and named data"})
                break

    region_rows = [{
        "start": f"0x{start:04X}", "end_exclusive": f"0x{end:04X}",
        "size_bytes": str(end - start), "name": name, "format_and_purpose": purpose,
        "classification": kind, "confidence": confidence,
    } for start, end, name, purpose, kind, confidence in REGIONS]
    data_rows = [{
        "start": f"0x{start:04X}", "end_exclusive": f"0x{end:04X}",
        "size_bytes": str(end - start), "name": name, "format_and_purpose": purpose,
        "reachability": "active OS", "confidence": "Verified",
    } for start, end, name, purpose in ACTIVE_INLINE_DATA] + [{
        "start": f"0x{start:04X}", "end_exclusive": f"0x{end:04X}",
        "size_bytes": str(end - start), "name": name, "format_and_purpose": purpose,
        "reachability": "active OS", "confidence": "Verified",
    } for start, end, name, purpose in ACTIVE_DATA_GROUPS] + [{
        "start": f"0x{start:04X}", "end_exclusive": f"0x{end:04X}",
        "size_bytes": str(end - start), "name": name, "format_and_purpose": purpose,
        "reachability": "retained module; unreachable in supplied Gauntlet II", "confidence": "Strong inference",
    } for start, end, name, purpose in (*LEGACY_DATA_ISLANDS, *LEGACY_DATA_GROUPS)]

    coverage_rows: list[dict[str, str]] = []
    segment_start = 0
    previous: tuple[str, str] | None = None
    for address in range(ROM_SIZE + 1):
        if address == ROM_SIZE:
            state = None
        else:
            region = next(row for row in REGIONS if int(row[0]) <= address < int(row[1]))
            region_name, region_kind = str(region[2]), str(region[4])
            if address in code:
                classification = "analyzed_instruction"
            elif region_kind == "mixed":
                classification = declared_mixed_data.get(address, "unknown_mixed_byte")
            else:
                classification = region_kind
            state = (region_name, classification)
        if previous is None:
            previous = state; segment_start = address; continue
        if state == previous:
            continue
        assert previous is not None
        region_name, classification = previous
        coverage_rows.append({
            "start": f"0x{segment_start:04X}", "end_inclusive": f"0x{address - 1:04X}",
            "size_bytes": str(address - segment_start), "region": region_name,
            "classification": classification, "confidence": "Verified",
        })
        segment_start = address; previous = state

    unknown = [row for row in coverage_rows if row["classification"].startswith("unknown")]
    if unknown:
        failures.append({"address": unknown[0]["start"], "issue": "unknown byte classification"})
    return region_rows, data_rows, coverage_rows, failures


def write_csv(path: Path, rows: list[dict[str, str]], fields: tuple[str, ...]) -> None:
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--check", action="store_true"); args = parser.parse_args()
    here = Path(__file__).resolve().parent
    reports = generated(here.parent.parent)
    outputs = (
        (here / "os_rom_regions.csv", reports[0], ("start", "end_exclusive", "size_bytes", "name", "format_and_purpose", "classification", "confidence")),
        (here / "os_rom_data_catalog.csv", reports[1], ("start", "end_exclusive", "size_bytes", "name", "format_and_purpose", "reachability", "confidence")),
        (here / "os_rom_byte_coverage.csv", reports[2], ("start", "end_inclusive", "size_bytes", "region", "classification", "confidence")),
        (here / "os_rom_byte_coverage_failures.csv", reports[3], ("address", "issue")),
    )
    if args.check:
        for path, rows, _ in outputs:
            if read_csv(path) != rows:
                raise SystemExit(f"{path.name} is stale")
    else:
        for path, rows, fields in outputs:
            write_csv(path, rows, fields)
    print(f"OS ROM coverage: {len(reports[0])} regions, {len(reports[1])} data subregions, {len(reports[2])} byte segments, {len(reports[3])} failures")
    if reports[3]:
        raise SystemExit("OS ROM coverage reconciliation failed")


if __name__ == "__main__":
    main()
