# Gauntlet II Reverse Engineering — Documentation Index

*Consolidated findings from the Gauntlet II arcade game ROM reverse engineering project.*

---

## Project Overview

This project reverse-engineered the Gauntlet II arcade game (Atari Games, 1986) at the source-code level, using radare2 disassembly, MAME tracing, and AI-assisted analysis. Three ROMs were analyzed:

| ROM | File | Address | Size | Description |
|-----|------|---------|------|-------------|
| OS ROM | `row9.bin` | `0x000000–0x00FFFF` | 64 KB | Bootstrap, OS services, diagnostics |
| Slapstic ROM | `row10.bin` | `0x038000–0x03FFFF` | 32 KB | Level data (bank-switched, 4 × 8 KB banks) |
| Game ROM image | `row76.bin` | `0x040000–0x05FFFF` | 128 KB | Populated main-game image; the OS-compatible aperture extends to `0x07FFFF` |

**CPU:** Motorola 68010 (32-bit, big-endian)  
**Display:** 336×240, 60 Hz

**Confidence: Verified** for file sizes, checksums, and populated address ranges. `row76.bin` is a 128 KB image, not 256 KB. The byte audit identifies 93,722 analyzed instruction bytes across 34 executable ranges; the rest is named ROM data and padding.

**Confidence: Contradicted** for the former unsupported claim that all functions
and tables were “fully documented.” The current audit instead checks 321/321
documented callable contracts and a byte-exact code/data/flag/catalog union.
**Confidence: Verified** that the independent main-ROM linear RAM sweep agrees
on all 318 literals and that the split-ROM graphics/maze corpus has been
regenerated after validating all 117 records. The main-game ROM audit is
closed except for the explicitly unresolvable build-intent/open-bus questions.
The OS-ROM audit is also closed: every byte is classified, all active and
retained-module entry points have contracts, and the RAM/control/data reports
have empty failure sets. Only explicitly unresolvable build provenance,
reserved-intent, and physical open-bus questions remain in
`08_known_issues.md`.

---

## ROM File Checksums

### Game ROM (`row76.bin`, 128 KB)

Assembled from 4 chips (interleave A-chips as even bytes, B-chips as odd; concatenate rows 7 then 6):

| Part Number | Location | Size | sha1sum |
|-------------|----------|------|---------|
| 136043-1121.6a | 6A | 32 kB | `3d93236aaffe6ef692e5073b1828633e8abf0ce4` |
| 136043-1122.6b | 6B | 32 kB | `378c582c360440b808820bcd3be78ec6e8800c34` |
| 136043-1109.7a | 7A | 32 kB | `7f51184840e3c96574836b8a00bfb4a7a5f508d0` |
| 136043-1110.7b | 7B | 32 kB | `dfce027ea50188659907be698aeb26f9d8bfab23` |

**Combined:** `row76.bin`, 128 kB, sha1 `decbe6438b3a2618bd7fe79d14be034efadd7ff4`

### Slapstic/Level Data ROM (`row10.bin`, 32 KB)

| Part Number | Location | Size | sha1sum |
|-------------|----------|------|---------|
| 136043-1105.10a | 10A | 16 kB | `a9a03150f5a0ad6ce62c5cfdffb4a9f54340590c` |
| 136043-1106.10b | 10B | 16 kB | `d2df4e5b036500dcc537a1e0025abb2a8c730bdd` |

**Combined:** `row10.bin`, 32 kB, sha1 `e4a36380f4a6394ad5cfb5aff5d7c8b352232d3d`

### OS ROM (`row9.bin`, 64 KB)

| Part Number | Location | Size | sha1sum |
|-------------|----------|------|---------|
| 136037-1307.9a | 9A | 32 kB | `d5fa19e028a2f43658330c67c10e0c811d332780` |
| 136037-1308.9b | 9B | 32 kB | `7467b2ec21b1b4fcc18ff9387ce891495f4b064c` |

**Combined:** `row9.bin`, 64 kB, sha1 `6e0d2026317e4a050fd79aac24ee0a644bf5a836`

---

## Document Index

| File | Contents |
|------|----------|
| [01_hardware.md](01_hardware.md) | CPU, full memory map, hardware I/O ports, and a display-composition diagram covering tiles, palettes, MOB shadowing, alpha, and layer priority |
| [02_os_rom.md](02_os_rom.md) | OS ROM: boot, interrupt/VBLANK, ROM-layout, and OS/game-boundary diagrams; complete API jump table and function reference |
| [03_game_rom_structure.md](03_game_rom_structure.md) | Game ROM: main-frame timeline, verified call sequence, calling convention, ROM-layout diagram, and coverage |
| [04_game_subsystems.md](04_game_subsystems.md) | All game subsystems, including tile-redraw, coordinate-conversion, and MOB-list structure diagrams |
| [05_data_reference.md](05_data_reference.md) | RAM variable map, enums and constants, data structures, ROM data tables catalog |
| [06_maze_catalog.md](06_maze_catalog.md) | Maze lookup/Slapstic/decode/render pipeline, the EEPROM-backed level→maze selection algorithm, and the complete 117-maze table (mazes 0–116: fixed opening levels, rotation mazes, treasure rooms, and two secret-room layouts) |
| [07_function_index.md](07_function_index.md) | Consolidated callable-entry index with addresses, names, descriptions, and checked ABI batches |
| [08_known_issues.md](08_known_issues.md) | Authoritative prioritized backlog and resolved-audit record |

### Generated and machine-readable artifacts

All CSV artifacts and their Python generators live together in
[`generated/`](generated/README.md). The commands below are also exercised by
`make check` from this `doc/` directory.

- [generated/maze_catalog.csv](generated/maze_catalog.csv) — verified pointer, bank, boundary,
  delimiter/exception, bank-table overlap, and header fields for mazes 0–116; generated by
  `generated/generate_maze_catalog.py`.
- [generated/main_loop_contracts.csv](generated/main_loop_contracts.csv) — verified inventory of
  the 29 direct calls issued by `g2mainloop`; generated by
  `generated/generate_main_loop_contracts.py`.
- [generated/maze_contracts.csv](generated/maze_contracts.csv) — checked argument, return, caller,
  and exceptional-convention inventory for 30 maze/Slapstic entries;
  generated by `generated/generate_maze_contracts.py`.
- [generated/player_collision_contracts.csv](generated/player_collision_contracts.csv) — checked
  argument, return, caller, and exceptional-convention inventory for 26
  player-movement/collision entries; generated by
  `generated/generate_player_collision_contracts.py`.
- [generated/player_runtime_contracts.csv](generated/player_runtime_contracts.csv) — checked
  argument, return, caller, and exceptional-convention inventory for 19
  player-runtime and name-entry entries; generated by
  `generated/generate_player_runtime_contracts.py`.
- [generated/mob_list_contracts.csv](generated/mob_list_contracts.csv) — checked argument, return,
  caller, and exceptional-convention inventory for 13 MOB-list and
  depth-placement entries; generated by `generated/generate_mob_list_contracts.py`.
- [generated/playfield_floor_contracts.csv](generated/playfield_floor_contracts.csv) — checked
  argument, return, caller, and exceptional-convention inventory for 15
  playfield stamp, visibility, and floor entries; generated by
  `generated/generate_playfield_floor_contracts.py`.
- [generated/wall_door_contracts.csv](generated/wall_door_contracts.csv) — checked argument,
  return, caller, and exceptional-convention inventory for 16 wall/door
  renderer entries; generated by `generated/generate_wall_door_contracts.py`.
- [generated/utility_init_contracts.csv](generated/utility_init_contracts.csv) — checked argument,
  return, caller, and exceptional-convention inventory for 13 RNG, memory,
  display-init, and Super Sorcerer entries; generated by
  `generated/generate_utility_init_contracts.py`.
- [generated/movement_path_contracts.csv](generated/movement_path_contracts.csv) — checked
  argument, return, caller, and exceptional-convention inventory for 11
  movement, path-grid, and door-endpoint entries; generated by
  `generated/generate_movement_path_contracts.py`.
- [generated/orchestration_sound_contracts.csv](generated/orchestration_sound_contracts.csv) —
  checked argument, return, caller, and exceptional-convention inventory for
  32 header veneers, reset/VBLANK, palette, options, main-loop, sound-ring, and
  alpha-render entries;
  generated by `generated/generate_orchestration_sound_contracts.py`.
- [generated/thief_secret_contracts.csv](generated/thief_secret_contracts.csv) — checked argument,
  return, caller, and exceptional-convention inventory for the final seven
  thief-state and secret-room entries; generated by
  `generated/generate_thief_secret_contracts.py`.
- [generated/callable_contract_coverage.csv](generated/callable_contract_coverage.csv) — complete
  321-entry union mapping every canonical game-ROM callable entry to one or
  more checked contract catalogs; generated by
  `generated/generate_callable_coverage.py`.
- [generated/monster_combat_contracts.csv](generated/monster_combat_contracts.csv) — checked
  argument, return, caller, and exceptional-convention inventory for 20
  monster-AI and shot-combat entries; generated by
  `generated/generate_monster_combat_contracts.py`.
- [generated/tport_forcefield_contracts.csv](generated/tport_forcefield_contracts.csv) — checked
  argument, return, caller, and exceptional-convention inventory for 20
  transporter, route-table, and forcefield entries; generated by
  `generated/generate_tport_forcefield_contracts.py`.
- [generated/dragon_thief_exit_contracts.csv](generated/dragon_thief_exit_contracts.csv) — checked
  argument, return, caller, and exceptional-convention inventory for 26
  dragon, thief/mugger, and exit entries; generated by
  `generated/generate_dragon_thief_exit_contracts.py`.
- [generated/score_coin_dialog_contracts.csv](generated/score_coin_dialog_contracts.csv) — checked
  argument, return, caller, and exceptional-convention inventory for 24
  scoring, coin, HUD, sound, and dialog entries; generated by
  `generated/generate_score_coin_dialog_contracts.py`.
- [generated/startup_attract_contracts.csv](generated/startup_attract_contracts.csv) — checked
  argument, return, caller, and exceptional-convention inventory for 19
  startup, attract, demo, title, and legend entries; generated by
  `generated/generate_startup_attract_contracts.py`.
- [generated/player_lifecycle_contracts.csv](generated/player_lifecycle_contracts.csv) — checked
  argument, return, caller, and exceptional-convention inventory for 19
  EEPROM/configuration and player-lifecycle entries; generated by
  `generated/generate_player_lifecycle_contracts.py`.
- [generated/control_targets.csv](generated/control_targets.csv) and
  [generated/control_target_failures.csv](generated/control_target_failures.csv) — independently
  analyzed direct/indirect control-transfer sites for all 321 documented game
  entries plus 80 unique computed-dispatch destinations, including
  assertion/reset exceptions;
  generated by `generated/generate_control_target_report.py`.
- [generated/rom_regions.csv](generated/rom_regions.csv) — byte-exact, gap-free top-level region
  union for the full 128 KiB game ROM; generated by
  `generated/generate_rom_regions.py`.
- [generated/rom_byte_coverage.csv](generated/rom_byte_coverage.csv),
  [generated/rom_catalog_reconciliation.csv](generated/rom_catalog_reconciliation.csv),
  [generated/rom_flag_reconciliation.csv](generated/rom_flag_reconciliation.csv),
  [generated/rom_range_overlaps.csv](generated/rom_range_overlaps.csv), and
  [generated/rom_byte_coverage_failures.csv](generated/rom_byte_coverage_failures.csv) — analyzed
  instruction-byte, named-range, and bidirectional §5/header/flag
  reconciliation for both mixed code/data regions, including an explicit
  report of the 21 intentional overlapping table views; generated by
  `generated/generate_rom_byte_coverage.py`.
- [generated/ram_operands.csv](generated/ram_operands.csv) and
  [generated/ram_operand_failures.csv](generated/ram_operand_failures.csv) — raw RAM-literal/indexed-base
  reconciliation for all 321 documented game callable entries; generated by
  `generated/generate_ram_operand_report.py`.
- [generated/ram_linear_reconciliation.csv](generated/ram_linear_reconciliation.csv) and
  [generated/ram_linear_scan_failures.csv](generated/ram_linear_scan_failures.csv) — independent
  linear decode of all 34 proven executable ranges (93,722 bytes), confirming
  the same 318 RAM literals with no extra candidates or decode gaps; generated
  by `generated/generate_ram_linear_scan.py`.
- `gauntlet_loader.r2` — minimal three-ROM radare2 map/settings/symbol loader;
  generated from `gauntlet.r2` by `generated/generate_r2_loader.py`.
- [generated/os_entry_candidates.csv](generated/os_entry_candidates.csv) and
  [generated/os_entry_candidate_failures.csv](generated/os_entry_candidate_failures.csv) —
  recursive vector/API/legacy/direct-control closure for OS implementation
  roots; generated by `generated/generate_os_entry_candidates.py`.
- [generated/os_boot_contracts.csv](generated/os_boot_contracts.csv) and
  [generated/os_boot_contract_failures.csv](generated/os_boot_contract_failures.csv) — first
  body- and byte-checked OS ABI batch covering boot, memory-test continuation,
  checksum-error, diagnostic, and string-copy entries; generated by
  `generated/generate_os_boot_contracts.py`.
- [generated/os_memory_test_contracts.csv](generated/os_memory_test_contracts.csv) and
  [generated/os_memory_test_contract_failures.csv](generated/os_memory_test_contract_failures.csv)
  — body- and byte-checked contracts for both destructive RAM-test entries and
  their A6 continuation stages; generated by
  `generated/generate_os_memory_test_contracts.py`.
- [generated/os_text_contracts.csv](generated/os_text_contracts.csv) and
  [generated/os_text_contract_failures.csv](generated/os_text_contract_failures.csv) — body- and
  byte-checked contracts for the public and internal alpha/text helpers plus
  bounded validation of all six computed text-effect cases; generated by
  `generated/generate_os_text_contracts.py`.
- [generated/os_numeric_display_contracts.csv](generated/os_numeric_display_contracts.csv) and
  [generated/os_numeric_display_contract_failures.csv](generated/os_numeric_display_contract_failures.csv)
  — body- and byte-checked numeric formatter, numeric display, direct glyph,
  alpha-address/write, timing, and descriptor-position contracts; generated
  by `generated/generate_os_numeric_display_contracts.py`.
- [generated/os_core_contracts.csv](generated/os_core_contracts.csv) and
  [generated/os_core_contract_failures.csv](generated/os_core_contract_failures.csv) — body- and
  byte-checked exception/IRQ, reset/boot, error-display, and OS-owned VBLANK
  contracts; generated by `generated/generate_os_core_contracts.py`.
- [generated/os_selftest_helper_contracts.csv](generated/os_selftest_helper_contracts.csv) and
  [generated/os_selftest_helper_contract_failures.csv](generated/os_selftest_helper_contract_failures.csv)
  — body- and byte-checked input debounce, display-test, sound-test, and
  diagnostic helper contracts; generated by
  `generated/generate_os_selftest_helper_contracts.py`.
- [generated/os_selftest_screen_contracts.csv](generated/os_selftest_screen_contracts.csv) and
  [generated/os_selftest_screen_contract_failures.csv](generated/os_selftest_screen_contract_failures.csv)
  — body- and byte-checked Color, Alpha, Motion Object, and Sound test screens,
  self-test loop, display clear, and game-ROM validation contracts; generated
  by `generated/generate_os_selftest_screen_contracts.py`.
- [generated/os_sound_contracts.csv](generated/os_sound_contracts.csv) and
  [generated/os_sound_contract_failures.csv](generated/os_sound_contract_failures.csv) — body-,
  bounded-shared-entry-, and byte-checked sound submission, polling, IRQ
  receive, ring-read, and reset contracts; generated by
  `generated/generate_os_sound_contracts.py`.
- [generated/os_coin_config_contracts.csv](generated/os_coin_config_contracts.csv) and
  [generated/os_coin_config_contract_failures.csv](generated/os_coin_config_contract_failures.csv)
  — checked coin accounting, packed configuration, high-score, active-player
  timing, and session-histogram contracts; generated by
  `generated/generate_os_coin_config_contracts.py`.
- [generated/os_eeprom_contracts.csv](generated/os_eeprom_contracts.csv) and
  [generated/os_eeprom_contract_failures.csv](generated/os_eeprom_contract_failures.csv) — checked
  EEPROM initialization, VBLANK worker, redundant-block codec, clear/queue,
  busy, and synchronous/asynchronous read contracts; generated by
  `generated/generate_os_eeprom_contracts.py`.
- [generated/os_operator_ui_contracts.csv](generated/os_operator_ui_contracts.csv) and
  [generated/os_operator_ui_contract_failures.csv](generated/os_operator_ui_contract_failures.csv)
  — checked cursor/display helpers, option-descriptor traversal/rendering,
  statistics summary/histograms, raw-bit and semantic game editors, and coin
  options; generated by `generated/generate_os_operator_ui_contracts.py`.
- [generated/os_callable_contracts.csv](generated/os_callable_contracts.csv) and
  [generated/os_callable_contract_failures.csv](generated/os_callable_contract_failures.csv) —
  reject-on-gap union of 168 implementation/shared roots, six bounded
  computed-dispatch cases, and all 56 byte-checked public API veneers;
  generated by `generated/generate_os_callable_coverage.py`.
- [generated/os_control_targets.csv](generated/os_control_targets.csv) and
  [generated/os_control_target_failures.csv](generated/os_control_target_failures.csv) —
  independent reconciliation of every direct, register-indirect,
  continuation, game-header-hook, and computed transfer in the 168-root OS
  closure; generated by `generated/generate_os_control_target_report.py`.
- [generated/os_ram_operands.csv](generated/os_ram_operands.csv),
  [generated/os_non_address_literals.csv](generated/os_non_address_literals.csv), and
  [generated/os_ram_operand_failures.csv](generated/os_ram_operand_failures.csv) — independent
  reconciliation of 81 OS RAM/video/color/EEPROM/hardware addresses plus the
  one checked address-shaped renderer stride; generated by
  `generated/generate_os_ram_operand_report.py`.
- [generated/os_data_xrefs.csv](generated/os_data_xrefs.csv) and
  [generated/os_data_xref_failures.csv](generated/os_data_xref_failures.csv) — direct references
  from the 168-root active OS closure into the exact 0x599A–0x6DA7 active data
  image; generated by `generated/generate_os_data_xrefs.py`.
- [generated/os_residue_contracts.csv](generated/os_residue_contracts.csv) and
  [generated/os_residue_contract_failures.csv](generated/os_residue_contract_failures.csv) — five
  byte-sweep-discovered, no-incoming active-image entries: the watchdog reset
  trap, three stack veneers, and the text-effect no-op; generated by
  `generated/generate_os_residue_contracts.py`.
- [generated/os_legacy_module_contracts.csv](generated/os_legacy_module_contracts.csv) and
  [generated/os_legacy_module_contract_failures.csv](generated/os_legacy_module_contract_failures.csv)
  — 21 checked entries in the runtime-dead 0x8000–0x9A0F retained game-support
  module; generated by `generated/generate_os_legacy_module_contracts.py`.
- [generated/os_all_function_contracts.csv](generated/os_all_function_contracts.csv) and
  [generated/os_all_function_contract_failures.csv](generated/os_all_function_contract_failures.csv)
  — complete 256-row ROM-wide union of 168 active roots, five active-image
  residue entries, 21 retained-module roots, six computed cases, and 56 API
  veneers; generated by `generated/generate_os_all_function_coverage.py`.
- [generated/os_rom_regions.csv](generated/os_rom_regions.csv),
  [generated/os_rom_data_catalog.csv](generated/os_rom_data_catalog.csv),
  [generated/os_rom_byte_coverage.csv](generated/os_rom_byte_coverage.csv), and
  [generated/os_rom_byte_coverage_failures.csv](generated/os_rom_byte_coverage_failures.csv) —
  byte-exact 64 KiB OS-ROM partition, 45 active/retained data subregions, and
  39 contiguous instruction/data/fill segments with no unknown byte;
  generated by `generated/generate_os_rom_coverage.py`.
- `check_confidence_labels.py` — enforces one of the five canonical confidence
  labels in every chapter-level section of `01_hardware.md` through
  `07_function_index.md`.
- `check_audit_completion.py` — cross-checks the full 128 KiB byte union,
  bidirectional data catalog, callable ABI union, control targets, RAM scans,
  empty failure reports, and absence of an active prioritized backlog.
- `make check` — regenerability and target-ROM regression checks for all of
  the above artifacts.
- `cd ../python-gex && uv run pytest -q` — complete split-ROM extractor and
  renderer regression suite, including exact reconciliation of all 117
  normalized maze pointers with its private `tests/data/maze_catalog.csv`
  snapshot (420 tests).
- `cd ../python-gex && GEX_TEST_ALL_MAZES=1 uv run pytest
  tests/test_golden_images.py -q` — regenerated pixel checks for all 117
  mazes plus the non-maze reference images (240 tests).

---

## Radare2 Project Files

`gauntlet.r2` is the legacy full project export. **Confidence: Verified** that
it contains stale version-specific settings and register-profile state that
produce errors under radare2 6.1.8.  Use the generated compatibility loader
for current analysis:

```bash
r2 -q -n -i doc/gauntlet_loader.r2 malloc://1
```

This maps `row9.bin`, `row10.bin`, and `row76.bin` at their canonical addresses,
sets `m68k`/`68010`/32-bit/big-endian decoding, imports the legacy OS function
entries and named flags, promotes every unique callable address in
`07_function_index.md` to an analysis function, and seeks to the game ROM. It intentionally omits
the legacy export's version-specific UI/evaluation state, obsolete register
flags, comments, and host type database.

Regenerate and require a zero-error load with:

```bash
cd doc
python3 generated/generate_r2_loader.py
python3 generated/generate_r2_loader.py --check --run-check
```

**Confidence: Verified** for the generated loader, both ROM callable-contract
unions, both byte reconciliations, and the independent RAM scans. The only
remaining questions in `08_known_issues.md` are explicitly unresolvable from
the supplied runtime artifacts.
