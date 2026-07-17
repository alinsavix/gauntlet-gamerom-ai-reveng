# Gauntlet II RE — Known Issues and Remaining Unknowns

This is the authoritative prioritized backlog. Confidence labels describe the evidence for the issue, not the eventual answer.

| Priority | Confidence | Issue | Next test |
|---|---|---|---|
| — | — | No active prioritized issue remains. | — |

## Unresolvable from the supplied artifacts

- **Unknown, unresolvable build-time intent:** the reserved header constants
  and explicitly bounded runtime-dead residue have no encoded pointer, xref,
  reachable dispatch, or runtime consumer. Their byte ranges, contents, and
  dead status are Verified; only the original editor/linker intent—information
  not present in the shipped runtime artifacts—cannot be recovered.
- **Unknown, unresolvable retained-module provenance:** the exact source-game
  revision and linker/editor symbol names for row9.bin's runtime-dead
  0x8000–0xF9F9 payload are not encoded in the supplied ROMs. Its bytes,
  instruction/data partition, 21 entry contracts, stale main-ROM call targets,
  data formats, and lack of Gauntlet II reachability are documented; only the
  original build identity remains unknowable from these artifacts.
- **Unknown, immaterial electrical value:** exact open-bus bits for decoded but
  unpopulated ROM sockets depend on physical board state and are absent from
  the ROM images. The decoded apertures and all program behavior that touches
  them are documented; no normal game path depends on a particular empty-
  socket value.

## Resolved in the 2026-07-14 diagram pass

- **Contradicted and corrected:** the position overview formerly approximated
  pixel position as scalar `slot_position × 32`, and the detailed
  `pf_stamp_update_regs` description reversed the packed row/column bit names
  while calling playfield RAM a 128×256 table. The verified representation is
  `slot = (row << 5) | column`, with unadjusted MOB pixels
  `(column × 16, row × 16)`. The playfield stamper computes byte address
  `0x900000 + (column << 8) + (row << 2)` in the column-first 64×64 word grid
  and writes its four descriptor words at `+0/+0x80/+2/+0x82`. The coordinate
  and tile-rendering diagrams now use this reconciled model. **Confidence:
  Verified** from the 0x5E542 instruction masks, shifts, base addition, and
  four stores.

## Resolved in the 2026-07-13 audit pass

- **Contradicted and corrected:** bytes 0x8000–0xF9F9 are not a monolithic
  font/data area. The complete OS-ROM account now has fourteen gap-free
  top-level regions, 39 byte-classification segments, and 45 exact data
  subregions. Active code has eight inline-data ranges; retained-module code
  occupies 0x8000–0x9A0F around five data islands; retained bulk data occupies
  0x9A10–0xF9F9. The byte sweep also found and contracted five unreferenced
  active-image entries. The ROM-wide function union is now 256 rows: 168 live
  implementation/shared roots, five active-image residue entries, 21 retained
  module roots, six computed cases, and 56 API veneers. Both independent
  control reports prove no incoming Gauntlet II transfer to the retained
  module. All new failure reports are empty. **Confidence: Verified** for
  bytes, partition, contracts, and reachability; retained-module semantic
  names/provenance are **Strong inference** / unresolvable as stated above.

- **Verified:** the independent OS RAM/hardware reconciliation analyzes all
  168 implementation/shared roots and records 81 unique absolute addresses
  with zero uncovered operands or analysis failures. It adds OS-lifetime
  aliases for three self-test label buffers and Motion Object scratch, exact
  hardware-register and video-endpoint flags, the sound-test result and
  saturating sound-poll busy byte, diagnostic alpha/palette targets, and the
  34-byte early-error destination. It also corrects 0x904FFA: this is bits
  15–8 of the big-endian counter at 0x904FF8 and is tested as the EEPROM-init
  drain timeout, not a standalone dirty flag. The address-shaped 0x00800002
  renderer stride is separately retained as a checked non-address literal.
  `generated/os_ram_operand_failures.csv` is empty. **Confidence: Verified.**

- **Verified:** the final independent OS control-transfer reconciliation
  analyzes all 168 contracted implementation roots and records 392 unique
  sites: 267 direct internal transfers, 94 constant register-indirect
  internal transfers, 13 inherited memory-test continuations, nine direct
  and eight register-indirect game-header hooks, and the one six-way
  text-effect dispatch. Every internal target maps to the callable union;
  there are no new roots, unresolved targets, or failures. Together with the
  230-row callable/dispatch/API union, this resolves the callable-entry/ABI
  backlog item. **Confidence: Verified.**

- **Verified:** `generated/os_callable_contracts.csv` now forms a reject-on-gap union
  of the 168 implementation/shared roots, six separately bounded
  computed-dispatch cases, and all 56 fixed public API veneers. Every veneer
  is independently checked for the absolute-JMP opcode and an implementation
  target with a contract; the 230-row union has zero duplicates, omissions,
  target gaps, or failures. The subsequent byte sweep found exactly five
  no-incoming active-image residue entries and no unclassified executable
  byte; those are separately contracted and included in the ROM-wide union.
  **Confidence: Verified.**

- **Contradicted and corrected:** the final 0x4896–0x5999 cluster is the
  operator statistics/options UI, not attract rendering. API 0x1D2 runs the
  statistics summary and histogram screens with an allow-clear argument; API
  0x248 edits configuration item 12 through a game descriptor stream or raw
  sixteen-bit fallback. Header word 0x40070 is therefore the default game
  settings word, not a screen-mode value. The 20-row operator-UI batch checks
  cursor/display helpers, descriptor traversal/rendering, statistics, raw-bit
  display, semantic and coin option editors, and both public API roots with
  zero failures. This closes the current OS implementation/shared-root
  semantic inventory at 168/168. **Confidence: Verified.**

- **Contradicted and corrected:** the public `get_eeprom_base`,
  `write_eeprom_config`, `process_coin_stats`, and `check_credits` identities
  were misleading. They respectively accumulate active-player time, activate
  one player's tracking bit, record a normalized session histogram, and
  consume credits. The high-score EEPROM record is five bytes (three score
  bytes plus one 16-bit base-40 initials value), not six. The 15-row
  coin/config batch now fixes those ABIs and also checks packed coin samples,
  stateful health conversion, difficulty-row reads, packed configuration,
  high-score expansion/insertion/ranking, and the internal writer at 0x3D18.
  The separate 11-row EEPROM batch checks persistent stack allocation,
  VBLANK serialization, the redundant-block syndrome codec and both register
  entries, three recovery clear helpers, both request veneers, busy state,
  and synchronous/asynchronous reads. Both batches have zero verification
  failures. **Confidence: Verified.**

- **Contradicted and corrected:** `send_sound_command` takes a response byte
  destination and count, not a callback pointer and parameter; IRQ6 advances
  that destination directly. Its shared register body at 0x4198 is now a
  promoted callable root. `reset_sound_cpu` takes two stack arguments rather
  than none, and `read_sound_data` returns -1 rather than unsigned 0xFF when
  empty. The eight-entry sound contract batch also bounds both shared latch
  veneers and verifies polling/IRQ/ring behavior with zero failures.
  **Confidence: Verified.**

- **Contradicted and corrected:** public large-font APIs 0x278, 0x26C, and
  0x206 are respectively `display_large_hex_value`,
  `display_large_text_at`, and `clear_large_text`, not a generic renderer,
  lookup, and styled draw. Their six-, four-, and one-slot ABIs and exact
  alpha-cell returns are now part of the expanded 16-row numeric/display
  batch, which passes with zero failures. **Confidence: Verified.**

- **Contradicted and corrected:** 0x0FCA, 0x17D4, and 0x1B20 are complete
  Color, Alpha, and Motion Object tests, not mere initialization/setup
  helpers; 0x229C is the complete Sound Test. The former `eeprom_validate` at
  0x21A0 instead validates the game ROM/Slapstic through hook 0x40054 and
  returns 1/0 after displaying any failed packed checks. The hook is now
  consistently named `game_rom_verify_veneer`. Finally, 0x129A is a
  non-returning repeating self-test loop: it does not read the mode long
  pushed by 0x0E14 and has no returning edge to that caller's encoded cleanup.
  All seven high-level contracts pass body and byte checks. **Confidence:
  Verified.**

- **Contradicted and corrected:** 0x904F8A is not a packed input snapshot.
  OS VBLANK stores an input-source pointer there: immediate 0x803000 or the
  pointer returned by the game hook. `read_debounced_input` indexes that
  source and maintains newly identified four-word previous-raw and stable
  arrays at 0x904F7A/0x904F82. The 13-row self-test helper batch also closes
  the alpha test-row copier, palette/sound initialization, incrementing fill,
  both large-glyph-range renderers, switch test, OS semaphore wait, next-test
  prompt, two sound-test waits, and packed-byte hex display with zero
  verification failures. **Confidence: Verified.**

- **Contradicted and corrected:** OS 0x0C52 is
  `display_working_ram_error`, not a generic string display: it has no string
  argument, always copies the literal at 0x0C86 to 0x906D00, and returns only
  by jumping through A4. Also, `wait_vblanks` observes the counter at
  0x904F04 that the text/VBLANK processor increments, not the distinct
  0x904004 semaphore. The 16-row core contract batch now verifies every CPU
  vector handler, reset/normal/self-test boot root, main-init continuation,
  early error display, OS VBLANK mode entry/handler, and detailed RAM-error
  renderer with zero failures. **Confidence: Verified.**
- **Contradicted and corrected:** `format_hex`'s fourth argument selects zero
  versus space padding; it is not an uppercase selector, because the direct
  formatter always emits uppercase. The decimal/hex display APIs at 0x260 and
  0x266 take six scalar slots `(coordinate0, coordinate1, value, width,
  pad_mode, color/style)`, not `(descriptor, color)`. The large-decimal API
  has the same six inputs and returns alpha-cell advance. The 13-row
  numeric/direct-display contract batch also fixes direct large-glyph returns,
  alpha word indexing, VBLANK count, and descriptor-position arguments with
  zero verification failures. **Confidence: Verified.**
- **Contradicted and corrected:** the public text-effect names, effect-type
  descriptions, and argument order did not match the implementation. The six
  computed cases at 0x2C22/32/64/82/C4/D0 implement timed clear, whole-chain
  blink, progressive draw, progressive clear, and the two cyclic line
  rotations; type 7 uses the separate whole-alpha path. Three-argument
  starters take `(descriptor, color/style, interval)`, while API 0x11E takes
  only `(descriptor, interval)`. The computed case sweep exposed four missing
  callable workers, two shipped stack veneers, and the shared character
  writer, raising the proven OS closure to 168 roots with zero decode
  failures. The 32-row text contract report validates 26 callable entries and
  all six inherited-frame cases. `draw_string` returns source bytes consumed
  including NUL, and `display_large_text` returns alpha-cell advance rather
  than a pixel width. **Confidence: Verified.**
- **Contradicted and corrected:** the earlier extractor change assumed the raw
  split-chip maze pointers were already linear, because the supplied
  `row10.bin` has normalized high bytes. The raw chips instead store addresses
  in the selected Slapstic bank's `0x38000–0x39FFF` aperture; `python-gex` now
  folds in each pointer's 2-bit bank value. A subsequent code-path audit also
  disproved the claim that pointer entry 116 was only an end sentinel:
  `show_level_start_screen` selects maze 115 for challenge tasks 0x50–0x56 and
  maze 116 for tasks 0x57–0x5D. The generator now validates all 117 live
  pointers, headers, and record boundaries against `generated/maze_catalog.csv`.
- **Verified:** the fine ROM-byte audit now classifies every byte in the mixed
  regions 0x40000–0x5561F and 0x56E54–0x5FFB1 as analyzed code or a named ROM
  range. `generated/rom_catalog_reconciliation.csv` gives all 329 parsed §5 rows an
  exact project-flag match, and `generated/rom_flag_reconciliation.csv` gives all 352
  non-code ROM flags an exact §5 or header-table row;
  `generated/rom_range_overlaps.csv` records 21 intentional
  nested/alternate views; there are zero unknown segments, suspicious
  code/data overlaps, or analysis failures. The sweep added 27 shipped
  callable entries (15 header veneers, the exception body, eight
  pointer-installed palette leaves, the options hook, and two tile-refresh
  entries), closing the checked union at 321/321. It also bounded the remaining
  header/reserved bytes, inline collision/score/scroll/options tables, and
  unreachable compiler/legacy residue in §5.
- **Verified:** an independent linear decode of the 34 proven executable
  ranges covers 93,722 bytes without a gap and extracts exactly the same 318
  explicit/indexed-base RAM literals as the 321-entry callable-body report.
  `generated/ram_linear_reconciliation.csv` has zero linear-only or callable-only
  candidates, every literal is covered by a named RAM flag, and
  `generated/ram_linear_scan_failures.csv` is empty. This closes the former concern that
  function boundaries might hide immediate-shaped RAM operands.
- **Verified:** the reference corpus and its ROM-independent manifest check
  contain exactly mazes 0 through 116. Maze 116 is regenerated from its full
  stream rather than the formerly truncated first-zero interpretation.
  `python-gex/tests/generate_reference_images.py` checks the complete required chip list before
  writing, verifies all eight header fields and the pointer/boundary span of
  every maze against its private `python-gex/tests/data/maze_catalog.csv`
  snapshot, records the headers in the manifest,
  and removes only truly out-of-range maze PNGs after a successful full render.
  The 231 regenerated PNGs match their stored dimensions and pixel hashes; all
  240 all-maze golden tests and all 420 extractor tests pass. **Confidence:
  Verified.**
- **Contradicted:** the former statement that most legacy tables remained
  unlabeled is no longer current. Every chapter-level section in
  `01_hardware.md` through `07_function_index.md` now has a canonical
  Verified/Strong inference/Hypothesis/Unknown/Contradicted evidence label;
  mixed-evidence sections use inline overrides for individual rows or claims.
  `check_confidence_labels.py` makes the 96-section requirement part of
  `make check` and rejects noncanonical
  `Confidence:` values.
- **Strong inference:** 0x40146 is an intentional watchdog-abort path. Atari's hardware memo specifies a 128 ms watchdog; 0x10000 lies in a decoded but unpopulated OS-ROM aperture, not outside all decode. A fetch exception recursively returns through OS 0x300 and game hook 0x40024 to the same JMP, while any non-faulting empty-socket value still leaves the watchdog unserviced. The exact open-bus word is board-state dependent, but the stable result is reset. RAM 0x904C00 is startup-cleared ordinary spare RAM with no post-clear writer found, so its nonzero test is a corruption guard rather than a palette inhibit or device latch.
- **Strong inference:** Atari's hardware map and MAME's schematic-verified decode both establish `0x040000–0x07FFFF` as the main-program ROM aperture. The supplied Gauntlet II image populates only `0x040000–0x05FFFF`; `0x060000–0x07FFFF` is an unpopulated decoded extension, not a mirror. Exact empty-socket bus bits are not recoverable from the ROMs and are immaterial to the audited program.
- **Verified:** ROM sizes and SHA-1 values match the canonical manifest; `row76.bin` is 128 KB mapped at `0x40000–0x5FFFF`.
- **Verified:** the level-data ROM is `row10.bin`, not `row9.bin`.
- **Contradicted and corrected:** `0x905F6F` is the low byte of the 16-bit vertical-scroll register, not a playfield-ROM bank selector.
- **Verified:** attract timers load 0x5DD/0x258/0x1C20; 0x5A1/0x21C/0x1BE4 are one-second input-lockout thresholds, not durations.
- **Contradicted and corrected:** maze vertical RLE writes at decreasing slot addresses (−0x20, or −0x1F for the odd-angle case).
- **Verified:** the game decoder stops at output cursor 0x400 and ignores terminators, while every stored maze record has a trailing zero delimiter used by offline tooling.
- **Verified:** the 29 `m2mainloop` callees have 37 direct call sites in the whole game ROM. Body analysis finds no stack-argument reads and every direct caller ignores `D0`/condition codes, establishing `void f(void)` for the complete batch. The interrupt-side `game_vblank` saves `D0-D1/A0-A2` and returns with `RTE`; the hand-written `input_debounce` leaf clobbers only `D0`.
- **Verified:** `doc/gauntlet_loader.r2` now maps all three ROMs, applies `m68k`/`68010`/32-bit/big-endian settings after the raw-file opens, and imports the retained function entries and flags with zero errors under radare2 6.1.8. `generated/generate_r2_loader.py --check --run-check` makes this reproducible; the full legacy `gauntlet.r2` export remains an archival annotation source rather than the supported loader.
- **Contradicted and corrected:** 0x56F00–0x5FFB1 is mixed code/data, not a pure table region, and the 0xE19E word at 0x5FFFE–0x5FFFF is not padding. `generated/rom_regions.csv` now verifies the complete physical ROM union and both actual solid-0xFF pads.
- **Verified:** 30 maze/Slapstic callable contracts now have body-checked stack offsets and explicit returns. This includes the unusual `find_maze` shared-stack input/`D1` output, the four frameless maze-number wrappers, register arguments for the bank-switch leaves, and `slapstic_verify`'s 0x0001FFFE success value.
- **Verified:** 26 player movement/collision contracts now have body-checked inputs and returns. `player_try_move` is a frameless wrapper over three normal stack arguments and returns its result in `D0.w`; the internal movement graph is register-based, the door helpers read a coordinate from their caller's saved-register stack, and `mob_probe_up/down` can return the non-slot boundary sentinel `0x0400`. The interpretation of a zero door status as “path handled” remains a **Strong inference** from its callers.
- **Verified:** 20 monster/shot-combat contracts now have body-checked inputs and returns. This distinguishes the normal `monsters_everything(first_mob_offset)` wrapper from its three inherited-frame branch entries, proves the shared-stack monster-type input to `monster_find_and_shoot`, records `D4`/Z from `find_unused_shot`, and fixes the complete target/shooter and boolean contracts for collision, reflection, wall, dragon, and impact helpers.
- **Contradicted and corrected:** the generated-loader and RAM-report Markdown parser required the function-name cell to end immediately after its first backticked name, silently omitting slash-separated alias rows. After the subsequent interior/shared, veneer, pointer-installed, and legacy-entry sweeps it recognizes 321 documented game entries. The loader contained 400 total OS/game entries at closure of the main-ROM pass and now grows as newly verified OS roots are promoted.
- **Verified:** `generated/control_targets.csv` analyzes those 321 entries plus 80 unique computed-dispatch destinations and reconciles 1,129 direct sites: 996 target documented game entries, 124 target documented OS API slots, eight target named RAM palette stubs, and one targets the separately tracked 0x10000 VBLANK abort path. It also records all 12 computed dispatches, the reset-vector jump, 192 register-indirect callable sites plus the separate null assertion, and zero analysis failures. Earlier sweeps added missing callable rows for `pf_palette_clear` (0x5FCCE), `pf_door_update_surrounding_xy` (0x5F7F0), `pf_wall_draw_stack` (0x5EAC2), and the RNG veneer/shared entries at 0x5FC22/0x5FC26/0x5FC2C.
- **Contradicted and corrected:** `monster_playerhit_jumptbl` is ten words at 0x49620–0x49633 for types 0x12–0x1B. The load uses backward-biased base 0x495FC; the former 28-entry description mistook live instructions for table bytes.
- **Verified:** 20 transporter/forcefield contracts now have body-checked inputs and returns. This proves the blocked/usable polarity of `tport_check_dest`, the one-based/fall-through result of `tport_find_id`, packed forward/reverse route words in `D0.l`, the stack and `D0` forcefield-query entries, and the inherited shared depth-list body used by the animation-placement helpers.
- **Contradicted and corrected:** 0x47DAE is not `tport_cycle_update`; it is `shot_impact_spawn`. `tport_cycle_start` initializes one of four effect-MOB channels, and loop 3 of `main_score_update` advances pictures 0x924–0x95A through byte counters at 0x90497C–0x90497F. Those bytes are an intentional `mob_effect_anim_counter` overlay, not transporter active flags.
- **Contradicted and corrected:** the temporary impact pool is four MOBs, 0x0D–0x10, not 0x0D–0x0F. `shot_impact_spawn` takes the first free channel; when full it derives a fallback from `shooter_slot & 3` but refuses to overwrite a channel carrying an active 0x924–0x95A transporter effect.
- **Contradicted and corrected:** `tport_route_read_pair` does not let its reverse lookup supersede the forward result. It returns the forward word in `D0` bits 31–16 and the reverse word in bits 15–0.
- **Contradicted and corrected:** the RAM report's `asm.flags=false` setting did not prevent exact named addresses from rendering as symbols, so the former 149-literal total omitted every such base. With `asm.sub.names=false`, `generated/ram_operands.csv` extracts 318 unique `0x904000–0x905FFF` literals from 321 independently analyzed game entry addresses. Every one is covered by a named RAM flag, and `generated/ram_operand_failures.csv` is empty.
- **Verified:** the 26-row dragon/thief/exit catalog contributes 23 newly covered callable entries; `main_handle_dragon`, `main_thief_anim`, and `main_exit_move` overlap the earlier main-loop batch and are not double-counted. The pass fixes stack arguments and return polarity for dragon proximity/fire, thief theft/collision/transport callbacks, exit lookup/transition, and the frameless shared exit-animation entry.
- **Contradicted and corrected:** 0x53E4A chooses the dragon's movement direction/state; it is not the per-frame position updater. 0x53D10 updates the four rendered dragon segments; it is not merely `dragon_change_dir`.
- **Contradicted and corrected:** `dragon_find_free_shot_slot` scans physical MOB slots 8 down to 5 and returns logical subslot 4 down to 1. The former “slots 5 down to 1” description conflated the returned subslot with the physical picture slot.
- **Contradicted and corrected:** `exit_get_id` returns a zero-based `exit_pos_table` index, not a MOB slot. A miss returns `level_exit_count`; the exit table begins at 0x910740 after the 32-word transporter table.
- **Verified:** the 24-row scoring/coin/HUD/sound/dialog catalog contributes 19 newly covered callable entries. Five rows overlap prior main-loop or maze batches and are not double-counted, bringing checked unique coverage to 167 entries.
- **Verified:** the 19-row startup/attract/demo/title/legend catalog contributes 15 newly covered callable entries. `one_time_init`, `main_attract`, `main_start_game`, and `main_logo_updcolors` overlap the earlier main-loop batch and are not double-counted, bringing checked unique coverage to 182 entries.
- **Contradicted and corrected:** 0x4CD1C is `load_legend_page`, not `load_demo_level`. It always loads maze 103 and dispatches page selector 0 to the overview, 2 to the rules, and other values to the monsters page. The distinct `attract_demo_init` at 0x449D4 loads maze 102 and installs the demo input stream.
- **Verified:** `scroll_apply(horizontal_delta, vertical_delta)` takes two signed words and returns D0.l=-1 after the zero/zero anchor-reset path or D0.l=0 after applying a nonzero scroll. `main_logo_updcolors` consumes this result.
- **Verified:** game-ROM address 0x40030 is an absolute-JMP callback veneer (`4EF9 00044A82`) targeting `game_playfield_init`, rather than a bare longword hook.
- **Verified:** the 19-row EEPROM/configuration/player-lifecycle catalog contributes 13 newly covered callable entries. Six rows overlap earlier main-loop or scoring batches and are not double-counted, bringing checked unique coverage to 195 entries.
- **Contradicted and corrected:** `player_join_finalize` (0x48A36, formerly `player_join2`) does not choose the character or create the MOB. `player_start_inner` (0x48BEC) performs placement and initialization and returns -1/0 for success/failure; the byte-index wrapper at 0x48BB6 calls the finalizer only after success.
- **Contradicted and corrected:** 0x44C7E is `show_continue_prompt`, not `update_maze_player_count`; it draws the PRESS START/WITHIN/TO CONTINUE lines and never decrements 0x904928. Conversely, 0x4D476 is `show_level_end_bonus_screen`, not the continue renderer: it calculates ordinary treasure and secret-room bonuses, removes departing sprites, restores secret state, and advances the saved maze/level.
- **Contradicted and corrected:** 0x4D1A4 is `secret_bonus_earned`, not `secret_continue_disallowed`. Its sole caller is the secret branch of `show_level_end_bonus_screen`; -1 selects the `5,000 × COINS` award and zero selects `NO BONUS !!`.
- **Contradicted and corrected:** 0x4A2CA renders score-per-coin, rank, “Enter your initials,” and three editable initial sprites, so its canonical name is `draw_player_initials_entry`; there is no `player_cleanup_slot` at 0x452D0, which is `setup_infopanel`.
- **Contradicted and corrected:** OS APIs 0x23C/0x242 are not interrupt-disable/enable calls. Both accept a sound-command word and write the sound latch at 0x803170; 0x23C retries until accepted and 0x242 makes one attempt and returns accepted/busy. Consequently `sound_play` tries immediate delivery only when speech traffic is idle and queues on a busy result.
- **Contradicted and corrected:** `highscore_check` ranks the player's score-per-coin value through OS 0x1C6 (`rank_high_score`), not the raw score through 0x1AE. `player_add_score_with_mult` only updates the raw score and redraw bit; it does not call the high-score checker.
- **Verified:** `dialog_first_encounter` normally takes player plus a 32-bit encounter mask; only the numeric-message record consumes a third word. Its `D0.l` result reports whether the selected record has a speech entry, not whether a dialog was merely requested.
- **Verified tool-surface limitation:** opening raw `row76.bin` at 0x40000 through a structured r2mcp `open_file` call does not auto-detect the 68010, so an unconfigured session renders valid code as invalid. The r2mcp server itself advertises `run_command` and `run_script`, which can set the architecture, map all three ROMs, and load `gauntlet_loader.r2`; however, those `X/exec` tools are not exposed in the active Codex MCP tool inventory even though the plugin launcher enables them with `-r`. Until that integration surface exposes either tool, substantive checks use direct radare2 with the same loader and engine.
- **Verified:** the 19-row player-runtime/name-entry catalog contributes 19 newly covered callable entries, bringing checked unique coverage at that stage to 214 entries. It records complete stack widths and returns, fixed OS-service/register exceptions, and direct control sites; the duplicate bodies at 0x5554E/0x555C4 are byte-identical to the live 0x55440/0x554B6 routines and have no discovered direct caller.
- **Contradicted and corrected:** 0x47FAC is `open_timed_doors`, not `award_walk_bonus`; it removes object types 0x0D/0x0E after the idle threshold and plays sound 0x12 ("Doors Open"). 0x50E34 is `player_damage_sample_update`, not a pickup detector, and 0x54FE8 is `secret_name_entry_update`, not a player entry animation.
- **Contradicted and corrected:** `death_potion_score` only chooses a popup type and returned score through the parallel 0x579E2/0x579D2 tables. `death_damage_accumulate` adds one player's supplied damage and dismisses the supplied Death MOB above 200; neither routine implements the formerly documented potion AOE.
- **Contradicted and corrected:** the helpers at 0x45866/0x4590E draw, announce, and clear the IT label but do not write `ram.it_player`; their caller stores the new tracked player only after both presentation calls.
- **Verified r2mcp stop record:** after successfully opening `row76.bin` at base 0x40000, a structured value search for 0x5554E was rejected with `[ERROR] Sandbox restricts search range`. Per the tool-failure rule, all further r2mcp calls stopped immediately; no indirect-reachability conclusion was drawn from the failed query. The generated configured control report establishes only that no direct call/jump to the duplicate was discovered.
- **Verified:** the 13-row MOB-list/depth-placement catalog contributes 13 newly covered entries, bringing checked unique coverage at that stage to 227 entries. It records the six-word frameless `mob_create` ABI, the normal wrappers versus D1/D2/A2-A6 register entries, physical-slot biases 0/+1/+0x11, the inherited 0x5DFA6 body, and `mob_depth_remove`'s `physical_slot_minus_one` convention.
- **Contradicted and corrected:** 0x5DE0A is `move_mob_slot`, not a pure copy: after inserting/copying the destination it falls through into source unlink-and-clear. 0x5DE44 is that register unlink-and-clear body, not merely `update_mob_backlinks`; 0x5DED4 is the distinct unlink-only body that preserves the source fields and upper type/state bits.
- **Contradicted and corrected:** the priority-head storage is one 64-word table at 0x905F80–0x905FFF. The 0x905F82 symbol is its 63-word tail view, not a second 64-word array extending beyond the RAM window. `mob_depth_key` at 0x904940 is a sort-key table for managed low MOB slots, not another backward-link table.
- **Contradicted and corrected:** 0x5E064 does not remove an arbitrary physical MOB or clear all five arrays. `mob_depth_remove(physical_slot_minus_one)` adds one, repairs the depth/priority chain, and clears only the depth key plus link/state words; callers separately clear or replace picture/H/V data.
- **Verified:** the 15-row playfield stamp/visibility/floor catalog contributes 15 newly covered entries, bringing checked unique coverage at that stage to 242 entries. It records normal versus D0/D1/D4 register entries, the shared renderer/visibility bodies, exact packed-coordinate and descriptor inputs, and all boolean returns.
- **Contradicted and corrected:** `pf_isblankfloor` returns -1 only for nonzero X with picture 0x8000 and object type other than 0x3F, otherwise zero. The former text claimed zero for picture 0x8000 plus type 0x3F, reversing both the success polarity and forcefield exclusion. `pf_is_connectable_floor_xy` shares those -1/0 leaves and adds level-flag/type-7–9 exclusions.
- **Verified:** `tile_on_screen_*` and `tile_near_screen_*` return -1 inside their respective tight/wide windows and zero outside. `maze_place_object_types` and `maze_convert_walls_to_exits` instead return ordinary 1 when they found/changed anything and zero otherwise.
- **Verified:** the 14-row wall/door catalog contributes 14 newly covered callable entries, bringing checked unique coverage at that stage to 256 entries. It records the register/normal-stack wrapper pairs, the shared replacement and redraw bodies, `pf_isdoor` class returns, and the fixed-register indirect predicates used by tile refresh and door drawing.
- **Contradicted and corrected:** the wall-renderer family includes a normal-stack entry at 0x5EAC2 (`pf_wall_draw_stack`) that was absent from the callable index. It enters the same renderer body as the D0/D1 register wrapper at 0x5EAB8; no direct control site was discovered, but its complete stack-load veneer makes it a shipped callable entry rather than an arbitrary interior label.
- **Verified:** `pf_isdoor`/`pf_isdoor_stack` return class 1 for pictures 0x9D18–0x9D3B, class 2 for 0x9D3C–0x9D7B, class 3 for 0x9D7C–0x9DAC, and zero otherwise. Door setup scans x=1–31 and y=0–31, while the surrounding-update entries redraw the four orthogonal neighbors through their shared body.
- **Verified:** the 13-row RNG/memory/display/Super-Sorcerer catalog contributes 13 newly covered entries, bringing checked unique coverage to 269 of 294. It includes the dormant normal-stack RNG veneer at 0x5FC22 plus the inherited-stack and register shared bodies at 0x5FC26/0x5FC2C, and records the exact recurrence, half-open return range, global-seed wrappers, memory units, and placement return.
- **Contradicted and corrected:** `memclear`, `memclear_core`, `copy_longwords`, and `palette_fade_copy` use pre-tested DBRA loops. Count N processes exactly N elements and count zero processes none; the former N+1 descriptions were wrong. Consequently the 0x20-longword priority clear ends exactly at 0x905FFF rather than overrunning RAM, and the palette initialization views at 0x5AD1E/0x5AD9E/0x5AE1E are adjacent 128/128/384-byte views rather than overlapping 132/132/388-byte views.
- **Verified:** `supersorc_place` tries all four players cyclically from the supplied start, then direction biases 0/−1/+1 with required clear runs 4/3/3. It returns the nonzero packed destination tile after updating the target MOB or zero after exhausting all candidates; the normal wrapper converts a physical MOB slot to the doubled array offset.
- **Verified:** the 11-row movement/path/door-record catalog contributes 11 newly covered entries, bringing checked unique coverage to 280 of 294. It establishes normal-stack arguments and returns for the occupancy, recursive cleanup, path-grid, direction, and door-record helpers, plus the A2 callback convention of `scan_move_path_interactions`.
- **Contradicted and corrected:** `tile_occupancy_test` takes one packed candidate slot, not an undocumented player/clearance pair, and returns -1 only when the in-bounds empty candidate has no neighboring rendered MOB inside both 0x7C0 axis thresholds. `nearby_mob_clearance_test` is the separate two-argument exclusion-aware scan and has the same -1/0 clear/blocked polarity.
- **Verified:** each path-grid byte stores `direction+1` in two nibbles. `path_grid_get_direction` reads the low nibble normally and the high nibble only when thief-mode bit 1 is set; invalid/unset values return 8. The high-nibble setter itself is disabled in that thief mode and otherwise refuses to overwrite a nonzero high nibble.
- **Contradicted and corrected:** the door endpoint scanners do not extend arbitrarily through a run. They test only the immediate above/below or left/right cells, append at most two entries, and return the updated count. Vertical direction codes are 0/2 and horizontal codes are 3/1; `door_record_endpoints` stores records per player.
- **Verified:** the seven-row reset/VBLANK/orchestration/sound/render catalog contributes seven newly covered entries, bringing checked unique coverage to 287 of 294. `game_start` and `m2mainloop` do not return, `game_vblank` is an interrupt-only RTE entry saving D0-D1/A0-A2, and `alpha_clear_rect` takes exact column/width/row/height dimensions with a 64-word row stride.
- **Verified:** the sound ring has eight physical slots but a usable capacity of seven. `enqueue_sound(uint8)` silently drops a command when `(head-tail)&7 == 7`; reset fills all eight slots with 0xFF and zeroes the byte indices.
- **Contradicted and corrected:** 0x571DA–0x571F9 is not dead residue. It is four live eight-byte forcefield cycle-delay profiles selected through the pointer table at 0x571FA; `game_start` installs profile 0 and maze setup selects `(level & 3)`. Only the zero word at 0x571D8 remains alignment/residue, and the former `forcefield_color_table` name was wrong because the consumer uses the bytes solely to reload a randomized timer.
- **Verified:** the seven-row thief-state/secret-room catalog closed the original 294-entry set. The later ROM-byte closure sweep added 27 shipped veneers, pointer-installed leaves, and dormant/legacy entries; the current machine union proves all 321 indexed entries have arguments, return behavior, purpose, and any exceptional convention recorded in a body-checked catalog.
- **Contradicted and corrected:** 0x4FCF0 is `thief_find_aligned_shooter`, not `find_richest_player`; wealth targeting remains at `thief_target_calc` (0x4DFF6). It returns the first active player whose shot is exactly aligned toward the thief, or -1. The paired 0x4E1B8/0x4E172 helpers begin/end shot-dodge mode rather than marking an item stolen or aborting a theft.
- **Contradicted and corrected:** 0x4E630 is `thief_track_victim_move(new_packed_pos, player_index)`, not `erase_mob_old_pos`. It updates the path-grid direction and `thief_victim_pos` only when the supplied player is the current target and moved; it never writes MOB picture/playfield memory.
