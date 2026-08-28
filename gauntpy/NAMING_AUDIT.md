# gauntpy naming audit

This report supersedes the naming direction recorded in `bc2139a`. It compares
one-to-one Python routines and modeled words with
[`../doc/07_function_index.md`](../doc/07_function_index.md) and
[`../doc/05_data_reference.md`](../doc/05_data_reference.md), after rechecking
the disputed routines directly in the ROM.

## Result

No unresolved one-to-one naming discrepancy remains.

| Surface | Result |
|---|---:|
| Modeled `GameState` rows audited | 35 |
| Explicit policy names in the table below | 25 |
| Other prior field alignments retained | 10 |
| Direct Python routine rows audited | 36 |
| Policy/disassembly-selected routine names below | 3 |
| Other prior direct-routine alignments retained | 33 |
| Prior literal-table changes retained | 40 |
| Callable rows classified complete / intentionally omitted | 272 / 50 |
| Unclassified one-to-one discrepancies | 0 |

## Method

1. Treat the ROM address as object identity.
2. Use direct disassembly and callers to establish semantics before naming.
3. Apply the approved Python policy name to source, tests, references,
   generated contracts, audits, comments, and applicable persisted fixtures.
4. Update the canonical address references to the verified result.
5. Keep different names only at an explicit representation boundary.
6. Enforce the result through `tests/test_rom_function_audit.py`.

## Approved modeled names

| Address | Final name |
|---|---|
| 0x904B4A | `forcefield_hurt_timer` |
| 0x904049 | `forcefield_step` |
| 0x904048 | `forcefield_step_timer` |
| 0x910780 | `forcefield_segment_table` |
| 0x90401A | `cyclic_wall_timer` |
| 0x90401C | `cyclic_wall_phase` |
| 0x910600 | `cyclic_wall_assignments` |
| 0x9048A6 | `random_wall_timer` |
| 0x9048A0 | `random_wall_low_mark` |
| 0x9048A2 | `random_wall_target` |
| 0x9048A4 | `random_wall_current` |
| 0x904A9A | `dialog_box_width` |
| 0x904A9C | `dialog_box_height` |
| 0x904A08 | `exit_move_timer` |
| 0x904063 | `secret_player` |
| 0x904065 | `secret_trick_id` |
| 0x904064 | `secret_trick_last` |
| 0x904A4E | `global_delay_timer` |
| 0x90404B | `sound_queue` |
| 0x9049EE | `sound_holdoff` |
| 0x9049F4 | `sound_retry_count` |
| 0x904012 | `eeprom_write_timer` |
| 0x904B94 | `eeprom_settings_cache` |
| 0x904010 | `maze_number` |
| 0x90400E | `maze_stride` |

The other ten addressed field alignments remain `vblank_semaphore`,
`player_joystick`, the four collision-distance words,
`monster_spawn_probability_bonus`, both monster-cull origins, and
`player_tile_or_tport_dest`.

## Direct routine decisions

| Address | Final name | Evidence |
|---|---|---|
| 0x4D1A4 | `secret_check_winner` | Tests the current secret objective/progress predicates and returns the winner-eligibility result consumed by the bonus path. |
| 0x51E80 | `door_open_start` | Both direct calls, 0x51DD8 and 0x51E24, follow an unlocked-door interaction. The body classifies the door, seeds or scans its two fronts, and always reaches `main_open_doors` at 0x51F9E before returning. Endpoint recording is intermediate setup; the caller-visible action starts opening. |
| 0x4C9A2 | `demo_message_show` | The sole direct call at 0x4A5A8 follows a 0xFF demo record. The body indexes `dialog_tip_ptrs` at 0x5815C, computes box dimensions, calls `dialog_position_box`, writes up to three lines through OS `draw_string`, and loads `dialog_timer`. It never calls `sound_play` or `sound_speech_play`; “speech” describes neither its body nor its effect. |

The generator inputs and generated movement/startup/callable contracts use
these same names. `ROM_FUNCTION_AUDIT.csv` points each direct Python port at
the selected symbol.

## Persisted-data policy

- Schema-1 state dumps require the current `GameState` field names. The
  renamed-field migration has been removed; only the independently existing
  schema-1 added-field and bytearray-shape handling remains.
- EEPROM rotation JSON uses `maze_number`, `maze_stride`,
  `treas_mazerand_num`, and `treas_mazerand_adder`. There is no renamed-key
  lookup.
- The deterministic scripted-run golden was audited and contains no affected
  state-field keys, so its persisted values remain unchanged.

## Remaining intentional discrepancies

These are representation differences, not unresolved naming drift.

| Category | Reason |
|---|---|
| Merged or decomposed routines | Python may combine assembly wrappers/shared bodies or split interrupt work among state writers. `ROM_FUNCTION_AUDIT.csv` records the equivalent owner. |
| `MobTable` methods | The class encapsulates multiple MOB list, insertion, removal, relocation, and depth-placement leaves rather than exposing every ABI entry. |
| Player-record fields | Fields on a `Player` omit a redundant `player_` prefix that is necessary for global ROM arrays. |
| `player_in_maze` | This is a polarity-normalized Python view of `player_tport_phase`, not a second one-to-one word. |
| Sound queue indices | Python list operations replace the ROM ring's separate byte buffer and head/tail words. |
| Host/container state | Diagnostics, snapshots, decoded maze objects, and renderer caches have no one-to-one arcade RAM identity. |
| Slapstic and ABI veneers | gauntpy consumes decoded maze data and does not emulate bank-switch command leaves, CPU traps, stack veneers, or register-entry aliases. |

The 50 intentionally omitted callable entries are counted by category in
[`ROM_FUNCTION_AUDIT.md`](ROM_FUNCTION_AUDIT.md). All other 272 callable rows
have complete caller-visible Python equivalents, including explicitly recorded
merged boundaries.

## Regression coverage

`tests/test_rom_function_audit.py`:

- joins all 322 callable rows to the canonical function index;
- imports direct Python ports under the selected names;
- binds addressed `GameState` fields to `doc/05_data_reference.md`;
- verifies the forcefield and cyclic-wall table-backed fields; and
- scans tracked source, documentation, generated contracts, audits, and
  fixtures for stale policy identifiers.

EEPROM and state-dump regressions also verify that renamed persisted fields are
not migrated.
