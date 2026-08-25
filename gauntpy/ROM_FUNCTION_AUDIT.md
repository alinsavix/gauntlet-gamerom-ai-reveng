# Game-ROM function coverage audit

This report compares gauntpy with the callable-entry inventory generated from
the shipped game ROM. The source inventory is
[`../doc/generated/callable_contract_coverage.csv`](../doc/generated/callable_contract_coverage.csv).
It currently contains **322 unique addresses and 322 unique names**.
[`ROM_FUNCTION_AUDIT.csv`](ROM_FUNCTION_AUDIT.csv) is the exhaustive crosswalk:
one row per entry with its classification, Python equivalent, evidence, and
confidence. This document summarizes that machine-readable report.

The earlier 321-entry total became stale when `dragon_head_pose_update`
(`0x545FA`) was added to the inventory. This audit classifies every current
entry; a function not listed in the exception tables below is in the complete
set.

## Result

| Classification | Entries |
|---|---:|
| Complete Python equivalent, including merged helpers | 272 |
| Partial Python equivalent | 0 |
| Intentionally omitted platform/ABI/dead entry | 50 |
| Missing game behavior | 0 |
| **Total** | **322** |

“Complete” means the caller-visible game behavior is represented, not that the
Python source preserves the ROM's function boundary. The port deliberately
merges register-entry wrappers, shared assembly bodies, and small leaves into
Python helpers.

## Missing game behavior

**None.** `player_hurt_speech_timer` (`0x49A98`) now owns the exact
predecrement/reload cadence, acid silence gate, literal character voice banks,
and `monster_playerhit` call site.

## Partial equivalents

**None.** The former eight entries are now complete:

- `maze_addrandompickups` (`0x43F68`) includes its hidden-potion cadence,
  character/player/difficulty adjustment, spawn-bonus attenuation, monotonic
  food-removal sweep, deferred loot, and special pickup draws.
- `thief_test_move_tile` (`0x4E7FC`) includes transporter and corner recovery.
- The four `door_traverse_*` entries use the shared ROM-shaped ray march.
- `scroll_to_slot` (`0x46C5E`) accepts and centers an arbitrary packed slot.
- `score_screen_color_cycle` (`0x4DE76`) was already a correct 16-word rotation;
  the audit had miscounted its twelve-iteration move loop as eleven.

## Intentionally omitted entries

These entries do not represent missing live game logic in the Python model.

| Kind | Count | ROM entries |
|---|---:|---|
| Hardware veneers, traps, and reset setup | 17 | `0x40000 game_start_veneer`<br>`0x40006 game_vblank_veneer`<br>`0x4000C game_irq1_watchdog_trap`<br>`0x40012 game_irq3_watchdog_trap`<br>`0x40018 game_irq2_watchdog_trap`<br>`0x4001E game_irq6_sound_veneer`<br>`0x40024 game_exception_veneer`<br>`0x40030 game_playfield_init_veneer`<br>`0x40048 game_options_veneer`<br>`0x40054 game_rom_verify_veneer`<br>`0x400DE scroll_to_slot_veneer`<br>`0x400E4 init_display_veneer`<br>`0x400EA maze_setup_veneer`<br>`0x400F0 pf_replace_veneer`<br>`0x400F6 mob_clear_veneer`<br>`0x40140 game_exception_abort`<br>`0x4014C game_start` |
| Slapstic paging/verification | 11 | `0x40CC4 maze_select_alt_bank`<br>`0x40CF2 maze_init`<br>`0x40D24 maze_select_bank`<br>`0x40D4E maze_select_bank_special`<br>`0x43826 slapstic_cmd_bitwise`<br>`0x56E58 slapstic_cmd_bank0`<br>`0x56E6E slapstic_cmd_bank3`<br>`0x56E84 slapstic_cmd_bankX`<br>`0x56E90 slapstic_cmd_maze_init`<br>`0x56E98 slapstic_cmd_bankX_special`<br>`0x56EAA slapstic_verify` |
| ABI-only register/stack entry variants | 12 | `0x41C30 player_try_move_core`<br>`0x42598 mob_collision_test_preserve_d1_a`<br>`0x425B4 mob_collision_test_preserve_d1_b`<br>`0x5DE44 moblist_remove_and_clear_regs`<br>`0x5DED4 moblist_unlink_regs`<br>`0x5E542 pf_stamp_update_regs`<br>`0x5E5D2 tile_near_screen_d4`<br>`0x5EA26 pf_isblankfloor_stack`<br>`0x5EAC2 pf_wall_draw_stack`<br>`0x5F598 refresh_tile_visual_stack`<br>`0x5F772 pf_isdoor_stack`<br>`0x5FC56 pf_isff_d0` |
| Unreferenced duplicate/legacy bodies | 3 | `0x5554E name_entry_step_char_copy`<br>`0x555C4 name_entry_draw_char_copy`<br>`0x5F644 refresh_tile_visual_legacy` |
| Operator/no-op hooks | 2 | `0x449CC attract_noop_hook`<br>`0x5317C game_options_display` |
| C-runtime primitives | 4 | `0x45BE8 string_length`<br>`0x5FD58 memclear`<br>`0x5FD64 memclear_core`<br>`0x5FD6A copy_longwords` |
| Obviated representation conversion | 1 | `0x5E868 maze_special_floor` |

The Slapstic rows are platform boundaries because gauntpy obtains decoded maze
records through gex rather than emulating the bank-switch device. The ABI rows
share behavior with a separately ported Python body. The `0x5E868` conversion
is unnecessary because gauntpy never creates the ROM's intermediate `0x8003`
marker representation.

## Complete set

The **complete set is the 272 entries in the source inventory after subtracting
the 50 addresses in the intentionally omitted table
above**. This definition is machine-checked by
`tests/test_rom_function_audit.py`, so every inventory entry belongs to exactly
one category and additions cannot silently inherit “complete” status.

The largest merged families are:

- `game_vblank` (`0x4017E`) is decomposed across `mainloop.tick` and the modeled
  palette/VBLANK writers.
- The eight player hurt/power palette leaves (`0x404A0`–`0x4051A`) are literal
  tables plus `display.player_palette_vblank`.
- Player probe leaves (`0x425D0`–`0x4270C`) are represented by
  `players.mob_probe_*`, `_probe_candidate_blocks`, and the top-boundary gate in
  `player_try_move`.
- Monster shared/interior entries (`0x40FAE`, `0x4119A`, `0x414A4`) are folded
  into the monster walk and dispatch helpers.
- The four `ray_march_*` entries (`0x5E10C`–`0x5E35E`) share
  `monsters._ray_march`.
- Playfield register/stack variants and initialization passes are folded into
  `maze`, `playfield_vram`, and `maze_objects`.
- MOB insertion/removal/depth wrapper families (`0x5DC58`–`0x5E064`) are
  represented by `MobTable`.
- Dragon, thief, transporter, door, name-entry, and legend helper boundaries
  are commonly merged into their owning subsystem rather than exposed under
  the ROM symbol.

## Non-ROM compatibility corrections

The source audit also found explicit behavior that is not present in the ROM.
These are not ordinary Python representation choices; they alter game-side
decisions to keep the current port synchronized or compensate for incomplete
upstream behavior.

| Python location | Correction |
|---|---|
| `players._probe_candidate_blocks` | In DEMO, every random-wall candidate is treated as nonblocking so host timing cannot derail the recorded route. |
| `players._player_fight_collision` | On the final active demo record, colliding Grunt/Aux-Grunt records are deleted because Python's earlier monster evolution put them across the route. |
| `players.mob_probe_left/right` | DEMO retains an upper flank from maze row one where the normal ROM threshold suppresses it. |
| `players.player_try_move` | DEMO bypasses the normal fallback from reserved row-zero intermediate cells to the live player record. |
| `players.player_try_move` | Multi-pixel movement is integrated and collision-resolved one pixel at a time; the ROM proposes the complete axis delta once. |
| `score.main_score_display` | Live score/health values are compared with host latches to force redraws because some Python producers do not set the ROM dirty bits. |

Host-only controls, diagnostics, ROM-free glyph fallbacks, and the
single-keyboard attract shortcut are excluded from this table because they do
not pretend to be arcade game behavior.

The demo corrections are the highest-risk shortcuts: they make a retained
trace pass by changing collision outcomes rather than by reproducing the
earlier RNG, wall, monster, or movement state that made the ROM recording pass.
They should be removed only after the underlying divergence is traced.
