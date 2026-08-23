# gauntpy — Known Issues

Issues discovered during implementation waves and the post-wave review. Each
entry notes which WP first encountered it, current status, and what to do about
it.

Status legend: **open** = needs action; **resolved** = fixed (kept for the
record).

All 28 main-loop calls and `one_time_init` are implemented. With the ROMs
present the suites are clean: **2296 passed, 4 skipped** (gauntpy) and
**700 passed** (gex). The six original blocked ROM tables have been transcribed
from `row76.bin`, the
disassembly-verifiable constants (player speed, exit timer, monster-speed
cadence, Death-contact damage) confirmed against radare2, and the
subsystem-isolation rule has been lifted (I-09/I-21/I-22 cross-imports wired).

WP-20 level-transition orchestration has landed: player exits drive the
next-level/maze computation and reload (I-12), players spawn into the maze from
their PLAYERSTART (I-08) and their record then migrates cell by cell as they
walk (S-63), firing works (N-02), and tile interaction is wired
into the player loop so pickups, doors, and exits all fire during gameplay.

The **front-end session flow** is now wired too: `start_attract_to_game`
(0x44204) leaves attract and loads level 1, so the `coincheck` →
`character_select_input_update` → `main_start_game` path takes a coin insert
through character select to a spawned hero — verified end-to-end through the
real frame loop (`test_level_transition.py::TestFrontEndFlow`). The playable
runner — `uv run gauntpy-play` — walks a hero around a real maze at 60 Hz,
advances level-to-level at an exit (N-05), and with `--attract` boots through
that whole front end live (coin key `5`, joystick to pick a class, Enter to
start).

---

## Resolved issues

### S-107 … S-110 · top-edge movement, Super Sorcerers, and special potions

- **S-107:** maze 17 at player pixel `(268,15)` reproduced a Python-only
  lateral block against the reserved row-zero wall. The ROM's horizontal probe
  suppresses its upper flank while the current doubled slot is below 0x80
  (maze rows 0–1); the port used only a generic in-bounds test and included row
  zero from row one. Left/right movement at that coordinate now matches direct
  ROM execution.
- **S-108:** the same investigation found the narrow-passage boundary mismatch:
  `player_try_move_core` keeps `active_mob_ids[player]` in D2, while the port's
  one-pixel integration re-quantized the corrected sprite origin into reserved
  row zero. Intermediate probes now fall back to the live record for slots
  0–31, preserving both ROM boundary behavior and the established one-pixel
  integration that prevents high-speed wall skipping. The shipped demo retains
  its prior port-side top-flank behavior because that is required to preserve
  the independently captured MAME maze-102 route and transporter landing.
- **S-109:** Super Sorcerer placement derived its start cell from the player's
  `x>>4`, shifting a correctly placed hero one cell left, then materialized the
  sorcerer without the ROM's four-pixel H correction. It now starts from
  `active_mob_ids`, writes destination H as `column*16-4`, preserves only the
  low six H/V bits at 0x5FF2C, and performs the literal eight-neighbour crowd
  scan. Cardinal and diagonal placements now match ROM execution and face their
  shots back along the chosen line.
- **S-110:** hidden potion type 61 was always converted into an inventory
  potion. The ROM decodes `(picture-0xA728)>>2` and first offers permanent power
  ID 0–5; only an already-owned power falls through to a potion (when inventory
  has room) or a solo 100-point award. The six stat powers and their sounds now
  apply, and `player_inv_update` writes the matching icon at the exact ROM
  columns 40, 39, 32, 31, 30, and 29.

### S-101 … S-106 · transportability, dragon/IT presentation, and maze diagnostics

- **S-101:** corner transport had stored the landing cell as
  `player_tport_type`, but the ROM clears that word at 0x5015C. The zero selects
  0x5078E's `pf_replace(landing, floor)` branch for ordinary 0x8000 wall
  markers. Transportability can now land on and erase those walls while leaving
  forcefield hubs and boundary cases protected; logical maze state, the MOB
  marker, and descriptor VRAM change together.
- **S-102:** `_probe_candidate_blocks` had bypassed collectible cells before
  `squeeze_through_check`. The ROM tests transport first, so a transportable
  player skips most adjacent items instead of collecting them. An item in the
  actual landing cell still goes through the relocation interaction and is
  collected.
- **S-103:** counted dragon hits changed paths but omitted 0x541E8-0x5422A's
  primary-segment hpos rewrite. Hits 1-2, 3-5, and 6-8 now select live MOB
  palettes 8, 7, and 6 before the ninth hit kills the dragon.
- **S-104:** maze 18, used by the direct level-19 runner start, genuinely
  decodes four IT creatures at slots 239, 327, 451, and 840. This is ROM maze
  content, not duplicate spawning. The separate display bug was real:
  `player_it_label_set` writes `0xB000 | player<<10`, not the ordinary
  player-text attribute, restoring the bright label.
- **S-105:** tight passages on the reported level-20 and level-22 areas exposed
  a collision-model shortcut: pictures with bit 15 set were rounded from their
  packed slot rather than their live H/V words. The 0x407EA-0x40820 and
  0x42688-0x426CE branches round the live words, which retain deliberate door
  and item placement corrections. The modeled probes now do the same.
- **S-106:** the bottom of the status panel now receives `MAZE nnn` and the
  first active player's `P# x,y` pixel coordinates. These requested diagnostics
  are explicit non-arcade content, but are written through modeled alpha RAM
  rather than composited as gameplay-looking renderer text.

### S-100 · treasure rooms retained the ordinary panel header

`setup_infopanel` now follows its maze-number branch at 0x45314. It always
clears the first seven rows of the 13-column status panel, but only mazes below
0x68 rebuild the GAUNTLET II dungeon glyphs and `LEVEL n` field. Treasure and
secret rooms instead write the ROM 0x5758E descriptor: `TIME:` at alpha column
34, row 1, above the existing large countdown. This removes the stale logo and
level number shown by gauntpy while preserving the player blocks below.

### S-95 … S-99 · continue, dragon, thief-return, runner, and reported nonbugs

- **S-95:** the continue prompt drew its literal `WITHIN    SECONDS` line but
  omitted `main_attract`'s 0x44984-0x449B6 full-second writer. The live
  `attract_timer / 60` value now updates alpha column 13, row 14 as a two-digit
  field.
- **S-96:** the dragon collision retry discarded
  `dragon_shot_hitbox_adjust`'s tagged result after testing the moving head.
  Successful head overlaps now retain the post-shift `0x0800` tag consumed by
  `dragon_shot_hit`, so open-mouth hits increment `dragon_hits`. The close-range
  breath also honors its live `mob_vpos = 0x12` 3x3 size instead of being forced
  through the ordinary projectile 2x2 asset geometry.
- **S-97:** deterministic mugger/thief escape reaches the recorded start cell,
  clears the MOB, and resets both current-slot fields; the reported frozen
  actor was not reproducible through that ROM path. The related real omission
  was `maze_addrandompickups`' 0x44166-0x441A6 next-level return: escaped mugger
  food and thief loot are now placed through the ROM's random empty-cell walk,
  including encoded multiplier-bag value restoration.
- **S-98:** direct `gauntpy-play` now defaults to the Elf. `--character` remains
  available for selecting any of the four classes during testing.
- **S-99:** the treasure countdown position itself was verified: setup and the
  live timer both call OS large decimal at alpha column 34, row 2; a
  space-padded one-digit value begins two cells later by design. S-100 records
  the separate surrounding-header omission. Holding Fire against a wall still
  selects and advances the shooting table before each shot; a regression uses
  the hero's real `cell_x - 4` geometry and protects those visible frames.

### S-93 · death/continue lost the player spawn record

`maze_scan_objects(-1)` now selects and stores `maze_player_start_slot`
(0x9049E0), removes that marker just as `pf_replace` does, and
`player_start_inner` reuses the saved cell for first starts and post-death
continues. A failed loaded-maze placement is no longer finalized into an active
player with MOB slot zero. Successful continues rebuild the hero picture,
tracking words, and snap the camera so the player is immediately visible.

### S-94 · dragon wall/flame report confirmed as ROM behavior

No behavior change was made. `dragon_choose_move_direction` 0x53E4A tests both
leading footprint cells and skips the candidate at 0x53FE0-0x54044 when either
picture is the `0x8000` wall marker. Because target/distance publication happens
after those probes, a player approached through that wall does not establish the
close-range flame lock. A regression now protects this ROM ordering.

### S-88 … S-92 · exit, treasure, idle-door, and thief-route regressions

- **S-88:** moving exits now rebuild their 0x8001 marker H/V/link words from the
  destination slot (0x52984-0x52A32), so a later exit dissolve uses the new
  location rather than copied coordinates from the old slot.
- **S-89:** treasure-room entry now writes the ROM 0x572C6-0x57325 title and
  instruction page, including both initial countdown fields.
- **S-90:** `main_treasure_timer` writes the live large countdown at alpha
  column 34, row 2 on every full second (0x4D2FC-0x4D32A).
- **S-91:** the common post-spawn level tail now calls `thief_setup` and clears
  `idle_timer` at the ROM's 0x4835E/0x4836A sites, so timed doors are re-armed
  on every level.
- **S-92:** player transport now records the victim's forward/reverse transporter
  route; `thief_enter_tport` follows the two-stage route lookup at 0x4FAD4,
  creates the destination placeholder, and the transition completion repairs
  the reverse path before recomputing the next cell. `main_thief_anim` also
  honors the 0x4E900 transition-timer gate, so the thief cannot move while its
  dissolve is in flight.

### S-87 · half-width large glyphs were forced to two cells

`render_large_glyph_register` tests the right-hand quad word at 0x3280 and
returns an advance of one cell when it is zero. The alpha writer now does the
same instead of always writing and advancing two cells. In the level splash,
the colon's ROM quad `(0x6D, 0x6D, 0, 0)` therefore occupies only column 14;
column 15 remains the intended blank before the large decimal at column 16.

### S-86 · corrected large-font base and level-splash teardown

The OS `LEA 0x2C6(PC),A4` in `display_large_text` resolves to 0x34A2, not
0x34A6 or 0x34A4. The exact 128-byte ASCII map is now transcribed from that
effective address. On expiry, the level splash now also performs `maze_show`
(0x4526A): alpha columns 0–28 and hidden 42–63 are cleared while the opaque
13-column status panel is preserved, before waiting players are spawned.

### S-85 · remaining reconstructed large-font and HUD table shortcuts

The ROM-free large-font renderer now assigns digit/letter quadrant images through
the same OS 0x34A2 index map as the live alpha writer rather than enumerating
`0-9A-Z` against the quadrant table. The five `M_DUNGEON` glyph rows are also
literal transcriptions of ROM 0x574B8 rather than generated contiguous ranges.

### S-84 · level splash glyphs were corrupt and its hold never expired

The large-character writer now indexes the literal OS ROM map at 0x34A2 instead
of assuming digits begin at glyph quad zero; `LEVEL: 2` and other large text now
use the same alpha words as OS `display_large_text`/`display_large_decimal_value`.
The shared UI delay at 0x904A4E is now decremented by `main_start_game`, outside
the dialog-gated gameplay band, matching 0x4817C. The splash therefore expires
and places waiting players even when a message box is active.

### S-83 · boundary walls and gameplay presentation regressed after VRAM migration

- The reserved row-zero boundary now participates in the ROM's wall-adjacency
  predicate, so its horizontal neighbours (and the opposite vertical seam) use
  continuous wall stamps instead of isolated segments.
- Whole-panel setup now performs `maze_hide`'s opaque 13-column alpha fill before
  writing the header and player blocks, preventing playfield pixels from showing
  through the status area.
- `game_vblank`'s 32-word gradient at ROM 0x405E8 now drives alpha color RAM
  0x91002E, restoring the color cycle in the GAUNTLET II panel logo.
- The 0x4A748 transition gate now sends ordinary levels directly to the ROM's
  `LEVEL:` splash and reserves `show_level_end_bonus_screen` for bonus-room
  transitions. The 150/180/600-frame level-start hold now delays player placement.

### S-82 · MOB/front-end rendering bypassed modeled video memory

`GameState.mob_color_ram` now owns the complete 256-word MOB palette region.
`init_display`, player setup, hurt/power VBLANK effects, title cycling, and
SCORES cycling write the modeled color banks; the MOB compositor resolves every
sprite solely from its hpos palette nibble and that RAM. TITLE now writes the
ROM's fixed playfield tilemap/palette and procedurally builds all 159 MOB records
used by `title_logo_init`, including its two-group motion program. SCORES and all
three LEGEND pages reload maze 103 through normal display initialization.

The audit also completed the display-memory side of OS large text, ordinary
initials entry, the continue prompt, the secret-room 29-character editor and its
ROM-matched CRC secret code, plus the rules-page reveal windows/decorative MOB
writes. Temporary front-end/bonus alpha content is cleared at the same lifecycle
boundaries as the ROM. Direct game-content compositing has been removed; the only
host overlays left are the frame counter/PAUSED indicator and ROM-free glyph
fallbacks.

### S-81 · playfield color RAM remained a palette snapshot

`GameState.playfield_color_ram` and `playfield_shadow_color_ram` now model all
128 IRGB words at 0x910500 and 0x910400. Level setup follows `init_display`:
palettes 0–3 clone the level floor palette, palette 4 receives the transporter
palette, palettes 5–7 are the exact staged wall fades, and the shadow bank is
derived by `palette_fade_copy`. Trap/stun VBLANK pulses, forcefield color steps,
and transporter records write the live banks; descriptor-only wall/exit changes
remain descriptor writes. The cached renderer resolves both normal and shadow
colors solely from these arrays.

### S-80 · playfield pixels bypassed modeled descriptor VRAM

`GameState.playfield_ram` now owns all 4096 column-first descriptor words.
Level setup commits random floor/wall texture choices once; shared ROM-shaped
writers update doors, exits, transporters, forcefields, traps, and living walls.
The compositor derives and generation-caches its normal/shadow rasters solely
from VRAM; `maze.data` remains logical state and per-effect draw overlays are no
longer on the live render path.

### S-79 · game alpha content bypassed modeled alpha VRAM

HUD fields, dialogs, high scores, legend/select text, and bonus tallies were
reconstructed directly in `render/hud.py` and `render/screens.py`. Their ROM
call sites now write complete attribute/glyph words into `GameState.alpha_ram`;
one generic alpha pass resolves opacity, bank/palette, glyph, and live
`alpha_color_ram` each frame. Only the host frame counter/PAUSED overlay and
ROM-free glyph fallbacks bypass that layer.

### Twelfth-pass attract/HUD/wall presentation (S-76 … S-78)

- **S-76 · damaged destructible walls jumped to unrelated static palettes.**
  The ROM's `7-stage` value indexes live color RAM, not gex's wall-palette list.
  The overlay now keeps the level wall palette instead of turning pink/green
  after the first hit; the exact damage stage remains in simulation state.
- **S-77 · player status blocks lacked their alpha-palette backgrounds.**
  `init_display`'s two 0x20-longword copies from ROM 0x5AD1E now populate alpha
  color RAM 0x910000/0x910100. `setup_infopanel` writes opaque space cells with
  attributes 0xD000–0xDC00 into alpha RAM, and the renderer resolves color 0
  through that live RAM. The resulting dark red/blue/yellow/green values match
  MAME 0.289 without sampled RGBA constants.
- **S-78 · the SCORES overlay erased its maze scenery.** MAME shows score boxes
  over maze 103. Both SCORES and LEGEND now independently load maze 103 through
  their ROM setup paths. MAME also confirms LEGEND's 29-column opaque
  alpha curtain is intentionally black; its maze remains loaded as scenery
  behind that curtain rather than visibly filling the text area.

### Eleventh-pass presentation/attract regressions (S-71 … S-75)

- **S-71 · bounded right edges lost the repeated left-wall strip.** The S-70
  clamp was made symmetric. Updated MAME 0.289 comparison then exposed the
  deeper error: visible playfield cropping uses `pf_hscroll`, while
  `(pf_hscroll - 8) << 7` is only the collision-window origin. At the ROM's
  clamps, X=5 cuts the left edge correctly and X=292 wraps twelve pixels of the
  left boundary wall onto the right; MOBs remain non-wrapping.
- **S-72 · shootable secret walls used the special preview palette.** Secret
  walls must be visually indistinguishable from their level's regular walls.
  They now retain the level wall palette, as destructible walls already do.
- **S-73 · the IT label was absent from the host HUD.** The compositor now draws
  the ROM's literal `I`/`T` glyphs at alpha column 0x24 on the tracked player's
  SCORE/HEALTH row.
- **S-74 · demo transport used a hand-tuned landing and one sparkle.** A retained
  MAME 0.179 trace proves maze 102 moves player 1 from slot 492 `(180,240)` to
  slot 486 `(92,240)`: source dissolve through phase 21, destination effect from
  phase 22. The ROM direction-rotation search and second `handle_tport` call are
  now ported; the demo-only four-cell offset is gone.
- **S-75 · position-0 joystick input restarted the demo attract screen.** On the
  single-keyboard host, pressing a direction during DEMO now advances to LEGEND
  instead of reinitializing maze 102.

### Tenth-pass rendering regressions (S-69 … S-70)

- **S-69 · horizontal doors had a lower protrusion.** The playfield renderer
  treated `door_gfx_by_neighbors` picture words as four sequential tiles and
  baked a 2×2 stamp. The ROM writes a live MOB picture/H/V record per door
  cell. Doors now remain dynamic MOBs, and level setup ports the connected and
  isolated-door picture/position tables at 0x5F9CE–0x5FC11; removing a door
  refreshes its surviving neighbours.
- **S-70 · bounded left edges exposed wrapped world pixels.** The hardware
  scroll conversion subtracts eight pixels; masking that origin unconditionally
  turned the bounded left clamp into world X=509. The renderer now clamps that
  negative origin and disables opposite-edge MOB candidates on non-wrapping
  horizontal axes while preserving the hardware seam on wrapping levels.

### Ninth-pass live-play regressions (S-65 … S-68)

- **S-65 · forcefield visuals were frozen in the cached level raster.** The
  cycle state and repeated damage phases were live, but the compositor never
  applied `forcefield_color` after level setup. Runtime segment cells are now
  re-stamped through that color each frame, including wrapped beams.
- **S-66 · the top playfield boundary was discarded by shot collision.** The
  row-zero branch at 0x40A9A returns a `0x400`-tagged playfield target when an
  ordinary shot enters the top boundary. The port returned no hit, so reflective
  shots escaped instead of reaching `shot_reflect_calc`.
- **S-67 · transporter landings incorrectly rejected occupied cells.** The ROM
  removes the old player record, resolves or clears a destination occupant, and
  creates the player at that slot (0x508BA–0x509C8). The port now replaces
  permitted monsters and handles collectible landings while preserving the
  exact `tport_check_dest` blockers.
- **S-68 · corner-squeeze transport omitted the destination screen gate.**
  The 0x500A2 `level_flags_4`/`tile_on_screen_test` gate now rejects an
  off-screen wrapped destination, preventing transport through the left edge of
  non-scrolling levels such as level 8.

### S-64 · death reset orphaned the migrated player record

The death path used to call `player_resetcounters`, which cleared the player's
slot pointer before the live record was unlinked. The record therefore remained
in the cell and depth chain as an invisible blocker. Death now releases the
remembered live slot before resetting the per-player RAM.

### ROM-faithful live player record migration (S-63)

- **S-63 · a live player's MOB record now migrates by maze cell.** Every hero
  used to stay in the PLAYERSTART slot it spawned in while its H/V words roamed
  the maze, so "identity is location" — the rule the whole MOB table is built
  on — held for every object except the four that matter most. That single
  divergence needed a port-only overlay in each consumer: shot probes carried
  the player record as an extra candidate, `monsters._player_in_cell` resolved
  an "empty" cell to whichever hero was standing in it, the renderer widened
  its SLIP band window to keep an off-row hero visible, and the tile pass
  interacted with two cells per frame because the record's own centred cell
  handoff was missing.

  `player_try_move_core`'s tail (0x424CA-0x42526) is now ported literally.
  `coords.mob_cell_of` is the ROM's cell rule — `(V + 0x400) & 0xF800 ^ 0xF800`
  plus `(H + 0x600) >> 5`, the same arithmetic `monster_loop_core` uses at
  0x41358 — and `players.migrate_player_record` relocates the record with
  `MobTable.move_slot` (`move_mob_slot`, 0x5DE0A) whenever the hero crosses into
  a free cell. Picture, both position words with their live low fields, the
  PLAYERSTART object type and the state word carrying the player index all
  travel with it; the vacated cell is cleared; the depth chain and the SLIP
  bands follow. It refuses the managed low slots 0-0x1F and never overwrites an
  occupied cell — an occupied destination goes to `player_tile_interact` first,
  exactly as 0x42542 does, and the record follows the hero in on the same frame
  once the tile is consumed.

  Consumers lost their overlays: `shots._candidate_core` evaluates the probed
  cell's own occupant, `monsters` resolves contact and rendered occupancy from
  the cell, `render.mobs` walks one geometric band window, `player_tile_pos`
  and the forcefield query read the record's cell, `nearby_mob_clearance_test`
  is the ROM's eight-neighbour palette scan again, and the demo join scan starts
  from `active_mob_ids` instead of a re-derived pixel cell. The transporter,
  corner squeeze, exit and death paths all relocate or release the same record.
  `_push_movable_wall` also takes the ROM cell rule, matching `failed_door_post`
  (0x427B4) instruction for instruction.

  Monsters can no longer step into the square a hero occupies — they hit it
  instead (0x413A2) — which restores hand-to-hand contact that the fixed record
  had silently suppressed, because a monster in the hero's cell *was* the
  probe's own origin cell. The attract actor uses the same ordinary-monster
  melee path. Gauntpy's monster step order puts two port-only Grunts across the
  terminal recorded run; those divergent records are removed when they obstruct
  that final pair, rather than disabling collision globally or letting the Elf
  pass through a live MOB. Covered by `tests/test_player_record_migration.py`
  and the full demo test.

### Eighth-pass live combat/presentation audit (S-57 … S-62)

- **S-57 · real forcefield hubs produced no beam segments.** Maze placement
  stores hubs with marker picture 0x8000; segment setup tested the marker as a
  blocker before recognizing the partner hub, built an empty table once, and
  froze it for the level. Partner hubs are now recognized first, so every
  later random lit phase damages the same beam cells.
- **S-58 · lobbers led stationary players.** The lead calculation used the
  player's persistent facing rather than the achieved-movement word at
  0x9048F0. Player movement now publishes the active-low per-axis result and a
  stationary 0xF nibble selects the ROM's zero-padded direction row.
- **S-59 · demon fire used a base palette.** Fixed demon channels 5–8 now route
  palette nibble 0xE through player-color slot 2, matching the Wizard palette
  selected by the original projectile word; lobber channels remain base
  palette 1.
- **S-60 · pause was only visible in the window caption.** The host passes its
  pause state into the compositor, which draws `PAUSED` above the host-only
  frame counter in the lower-right panel.
- **S-61 · point-blank shots could skip a monster.** The port-only roaming-player
  overlay replaced a cell's real occupant before the shot hitbox test. Real
  occupants are now evaluated first and player records were additional fallback
  candidates, preserving enemy-shot hits without hiding co-located sorcerers.
  Superseded by S-63: the overlay is gone entirely, because a live hero *is* the
  cell's occupant.
- **S-62 · floating score producers were incomplete.** Potion-killed Death now
  uses the exact eight-entry score/popup tables at 0x579D2/0x579E2. Treasure
  pickups allocate a visible 100-point popup, and popup integration tests cover
  depth placement through the renderer.

### Seventh-pass seam tracking audit (S-55)

- **S-55 · level 7 lost monster tracking across the left seam.** The
  `pixel << 7` position words use unsigned 16-bit overflow as one 512-pixel
  maze. Monster culling and projectile off-screen disposal did not, so the
  camera could show monsters and lobbers that the simulation treated as half a
  word away. Both windows now use the one-maze modulus; the vertical cull uses
  the exact upward-coordinate origin, and the shared tile-visibility helpers
  wrap Super Sorcerer and transporter candidates across either seam.

  Superseded in detail by S-56: the MOB words are now stored in the arcade's
  own encoding, so `512 << 7` *is* 0x10000 and the modulus is plain 16-bit
  arithmetic.

### Native MOB coordinate migration (S-56)

- **S-56 · the MOB H/V words are now the arcade's own.** gauntpy previously
  stored a position field one bit low (`pixel << 6`) with a downward vertical
  axis, and converted at every ROM boundary: correction tables halved on
  import, velocity/hitbox/window constants halved, the vertical axis flipped in
  the cull rectangle, the shot spawn tables, the dragon head deltas and the
  lobber lead. The state is now the hardware's: position in bits 15-7 over a
  seven-bit low field, one pixel per 0x80, and the vertical field counting up
  from the playfield floor exactly as `maze_place_object`'s `slot << 11`
  writes it. `coords` owns the encoding and the two boundary conversions
  (`screen_y`/`native_v` for a downward maze row, `sprite_top_y` for the
  renderer); every ROM table is now transcribed at its literal value, and one
  512-pixel maze wraps at 0x10000 with no explicit masking.

### Sixth-pass live-render/demo audit (S-44 … S-54)

- **S-44 · trap-controlled walls vanished during level setup.** Types 7–9 were
  compacted before the cyclic-wall flag was checked, consuming ordinary trap
  groups. Setup now compacts only cyclic levels; stepping on a trap clears its
  matching wall records and the corresponding maze descriptor cells.
- **S-45 · starts and continues used inconsistent health paths.** The direct
  runner now starts from factory settings, and paid starts/continues restore the
  complete configured starting-health entry. Demo and free-play joins take the
  ROM's 2000-health branch. The finalizer also runs the scripted join credit
  path, so late demo actors are alive rather than zero-health placeholders.
- **S-46 · special playfield stamps were missing or conflated.** EXITTO6 now
  uses its distinct 0x5C8A8 descriptor, transporter markers render as the
  0x49E–0x4A1 playfield stamp, and transporter index zero is transparent over
  the floor rather than an opaque black square.
- **S-47 · live color-RAM effects were frozen.** Trap and stun palettes now
  follow the alternating-field 0x4044↔0xA0AA and 0x2220↔0xEEE0 pulses.
  Transporter palette entries 8–13 consume all six records at 0x5AFAE.
  MOB palettes now live in the 256-word 0x910200 bank: init_display's exact
  0x5AE1E and Wizard-table copies, per-player spawn/hurt/power writes, and the
  title's ten-row shift plus 0x910332 brightness injection all mutate that RAM.
  MOB and title graphics remain indexed until the renderer resolves the live
  entries; title MOB composition itself remains deferred.
- **S-48 · the dragon never reached its flamethrower state.** Direction choice
  now uses the ROM compass, candidate-cell probes, target/distance packing,
  no-target sentinel and signed turn duration. Muzzle alignment updates the
  lock bit, close targets produce the sustained max-tier flame, and projectile
  direction is no longer rotated by 90 degrees.
- **S-49 · wrap-camera targets could remain exactly 512 pixels away.** The
  camera extent now includes the current center, folds each player into the
  register-relative window, and uses the 0x140 outlier threshold plus 200-pixel
  adjustment. This removes the endless left pan near the dragon/world seam.
- **S-50 · score-popup producers were disconnected.** Adaptive food uses the
  parallel 0x5B774 popup table, and special score bags display and award
  `special_bonus_score` rather than an invented fixed 200. Existing popup slots,
  depth placement and 60-frame retirement are now visible from pickup paths.
- **S-51 · the attract recording could not complete.** Hardware player palette
  nibbles 12–15 now select the correct hero color variant; centered interaction
  collects the row-straddling potion exactly once; shot-resistant potions are
  removed after pickup; adjacent-player joins use the four-cell ROM search; and
  the recorded Elf reaches the exit instead of dying or stopping below the
  final wall.
- **S-52 · frame inspection lacked a stable reference.** A host-only decimal
  frame counter is drawn in the lower-right status-panel corner after all game
  layers. It deliberately uses host text and is not presented as original art.
- **S-53 · completing the score-bag read path exposed missing writers.** A fresh
  level now seeds the ordinary 100-point bag value. Dragon death creates the
  score bag and randomized hidden potion at its two facing-dependent offsets,
  raises the hint latch, and changes the bag value to 2000. Previously the
  corrected pickup read could award zero because only the thief-return writer
  existed.
- **S-54 · the dragon loot audit exposed two placement corrections.** Mirroring
  a 2×2 dragon needs a one-cell post-mirror anchor correction before reserving
  its footprint. Dragon death now centers the dissolve by eight pixels, applies
  the two loot-offset records cumulatively, and keeps both prizes inside the
  cells just released by the four segments.

### Fifth-pass live-play and host-control audit (S-36 … S-43)

- **S-36 · ordinary exit markers had no render owner.** Exits were excluded
  from the cached terrain and only `exit_open_id` was overlaid, so normal static
  exits disappeared. The playfield overlay now stamps every live EXIT/EXITTO6
  marker and layers the moving-exit animation over its selected cell.
- **S-37 · two-pixel movement could cross a cell boundary before probing it.**
  Certain approach alignments stopped the hero one pixel inside a wall, which
  then made tangential movement look blocked. Each axis is now probed one pixel
  at a time while retaining the ROM's horizontal-before-vertical order; movable
  wall and fight contacts still cancel the entire axis for that frame. The
  first-level wall and attract push sequence both have exact regressions.
- **S-38 · projectile palettes were discarded.** `AssetStore.sprite` forced
  every 2x2 projectile through base palette 0. Lobber rocks now use live base
  palette 1; palette slots 12-15 resolve through the character/player colour
  bank, restoring Warrior arrows and the palette-14 demon/Super-Sorcerer shots.
- **S-39 · inventory keys used player-text colours.** Alpha keys and potions now
  use the dedicated KEYPAL/BOMBPAL IRGB ramps from `colors.c`, rather than the
  score/health palette. The exact 0xE000/0xF000 attribute families are recorded.
- **S-40 · enemy shots could not find roaming player records.** The Python port
  kept each hero in its PLAYERSTART record while changing H/V; the ROM migrates
  the record between cells. Shot probes substituted the live player record for
  the logical cell. Player spawn also writes the player index into
  `mob_state_link`, so damage is charged to the actual victim rather than
  player 0. Superseded by S-63, which migrates the record and retires the
  substitution.
- **S-41 · host pause was missing.** P toggles a host-only pause that keeps the
  event/render loop responsive while freezing the 60 Hz simulation.
- **S-42 · first-encounter boxes could not be disabled for testing.**
  `--no-first-encounter-messages` suppresses those alpha boxes and their
  gameplay gate while preserving encounter flags, speech and gameplay effects.
- **S-43 · structural audit.** The 28-call main loop, RAM-shaped `GameState`,
  five-array MOB model, depth chain/SLIPs and subsystem boundaries still map
  closely to the original. The reviewed shared `mob_depth_remove` primitive now
  lives on `MobTable`, maze placement helpers are public bridge APIs, and
  subsystem logic no longer imports gex directly. Python deliberately
  consolidates small C files and renders after simulation rather than writing
  VRAM inline.

### Fourth-pass source/MAME fidelity audit (S-28 … S-35)

- **S-28 · fixed-point scale and camera conversion.** The new original C
  sources and MAME confirm that hardware positions and velocities are `<<7`.
  Player, monster, thief, straight-shot and lobber vectors were converted once
  on import at the time; vertical camera, culling and shot windows use the
  ROM's inverted-V algebra. (S-56 later removed the conversion entirely by
  storing the hardware words themselves.)
- **S-29 · food identities were reversed.** `FOOD000` and `FOOD001-3` heal 100,
  `RFOD001` (0x277B) uses the exact 20-entry adaptive table, and only `PFOD001`
  (0x25ED) poisons for 50. Both destructible and shot-resistant food disappear
  when eaten.
- **S-30 · player collision dispatch was incomplete.** Movement now applies the
  horizontal axis before probing vertical, uses the hero-centre cell bias, and
  preserves `mob_collision_test`'s pass/block/fight contract. Pickups trigger
  once on cell entry; generators and ordinary monsters use the source fight
  tables; locked chests spend a key and reveal their ROM reward; traps remove
  their matching walls; stun floors use the character delay/sound tables.
  Death cannot be meleed, invisible sorcerers reveal before taking damage,
  Super Sorcerers relocate, and thieves are fightable.
- **S-31 · toroidal hardware rendering was clipped.** The playfield and shadow
  rasters wrap at both 512px seams, bottom clamp includes row 31 followed by row
  0, MOB band traversal covers both top and bottom wraps, and the full 336x240
  playfield/MOB raster exists beneath the alpha HUD. The 24px hero's right edge
  is hard-limited to the score-panel boundary.
- **S-32 · the attract recording outran and missed its scripted interactions.**
  Push frames now move only the wall, demo 0xFF records display their 120/150
  frame ROM message boxes, shooting cannot restart while its fixed projectile
  channel is occupied, and the demo follows the key/chest/trap/food/wall,
  transporter, stun-square and exit sequence end to end. Command-boundary
  positions through the opening half were checked directly against MAME RAM.
- **S-33 · maze-placed monsters started with the wrong compass state.** Their
  source direction 4 is converted to gauntpy direction 2 (down), and Super
  Sorcerers begin with the shipped invisible picture/flag outside legend mode.
- **S-34 · dragon footprint reservation was lazy.** Placement now writes the
  three 0x8002 reservation records and initializes the four segment IDs before
  the primary dragon becomes active.
- **S-35 · half the first-encounter text bank was absent.** All 32 message
  records and all 32 speech IDs are now present, including traps, stun floors,
  locked treasure, thief, Death, fake exits and forcefields.

### Third-pass live-play regressions (S-18 … S-27)

- **S-18 · player collision was cell-coarse.** The four movement probes named
  three neighbouring cells but skipped `mob_probe_candidate`'s 0x7C0 per-axis
  position test. A wall in a flank cell therefore blocked an entire row or
  column while the visible hero was still clear. Probes now test the proposed
  H/V anchor, including the software-marker rounding at 0x407EA-0x40834.
- **S-19 · hero geometry used its sprite origin as its logical cell.**
  `player_start_inner` stores a 3x3 hero four pixels left of its 16px cell, so
  tile interaction, thief tracking and monster contact now undo that correction.
  Transport/corner-squeeze landings use the same `cell_x-4, cell_y` origin.
  The renderer also restores the hardware's vertical convention: extra MOB
  rows draw upward, fixing the 8px player/monster collision offset.
- **S-20 · player screen gates were absent.** The exact
  `scroll_hpos_origin`/0x7000 and `scroll_vpos_origin`/0x7400 comparisons now
  prevent entry beneath the HUD and past the bottom edge unless
  `LFLAG4_PLAYER_OFFSCREEN` explicitly permits it. First-player placement snaps
  the camera before input, so level starts and the attract demo are not pinned
  by an uninitialized viewport.
- **S-21 · monster state changed without changing art.** The complete 64-word
  idle/moving/special animation banks at 0x58C0A-0x59635 are literal ROM
  tables. `monster_update_anim_tile` now writes the frame selected by the live
  animation counter and converted compass direction, so monsters turn and
  animate while walking. Contact facing resolves the hero's real MOB record
  (S-63 makes that the cell itself).
- **S-22 · opened doors survived in the terrain cache.** Door logic cleared MOB
  RAM, but the renderer rebuilds static door stamps from `maze.data`. Every
  living-maze clear now replaces that descriptor with `TILE_FLOOR`, which also
  invalidates the content-keyed playfield cache.
- **S-23 · 0x40E66 was assigned to the score multiplier.** Disassembly at
  0x48EE2-0x48F06 proves `{3,0,4,0}` initializes
  `monster_spawn_probability_bonus` for the first active player's class and is
  cleared by later joins. `player_bonusmult` remains at the reset value 1;
  credit initialization also reasserts the 1x/starting-health HUD baseline.
- **S-24 · living terrain updates were incomplete.** The renderer reads
  `maze.data`, not marker MOBs, so the descriptor API now covers doors,
  cyclic/random walls, destructible/secret/movable walls and the escape-timeout
  exit conversion. Removed terrain becomes floor and newly active cyclic/random
  walls are written back, preventing both phantom visible walls and invisible
  solid walls.
- **S-25 · live monster attack art was absent from gex.** The exact demon
  attack, Lobber throw and IT special banks at 0x594B6-0x59635 are now named
  actions in `monsters.jsonc`; every frame resolves through `AssetStore` instead
  of disappearing. A monster that crosses into a new MOB slot also writes its
  current facing/frame there immediately.
- **S-26 · VBLANK hurt feedback and join defaults.** The 0x905F30 timers now
  step 0x12→0x0C→0x06→0 and write the class-specific palette entries from
  0x5B20E+ into live player MOB color RAM, rather than invoking a renderer
  overlay. Paid and free-play joins both
  preserve `player_resetall`'s per-slot character default; `coincheck` had an
  invented Warrior assignment absent from 0x42B6A.
- **S-27 · living-terrain redraws were too expensive and level state leaked.**
  Content changes now restamp only the changed cell and its wrapped adjacency
  ring, reusing the original per-cell floor/wall random choices. A measured
  cyclic/random-wall toggle fell from a 138-198 ms full 512x512 rebuild to a
  2.7 ms median local update (under 4 ms worst observed), without retexturing
  shrub cells elsewhere or clipping the 24x16 movable-wall overhang.
  `select_forcefield_delay_profile` also clears the packed cyclic assignment,
  phase and timer so a prior level's wall map cannot corrupt the next maze.

### Second-pass audit · player and transition lifecycle (S-1 … S-9)

Nine concrete divergences found by re-reading the ROM against the port, all
closed and regression-tested.

- **S-1 · `player_stundelay` was dead state.** Every stun source wrote
  `0x904A54` and nothing read it. `main_move_players` now decrements it and,
  while it is still non-zero, branches to the forcefield check exactly as
  0x4A908-0x4A91C does: no speed lookup, no facing update, no
  `player_try_move`, no tile interaction. The forcefield charge also **moved
  after** the movement call (0x4AA42 follows 0x4AA1E), so walking into a live
  segment is billed on the frame the hero arrives.
- **S-2 · `highscore_check` (0x49D0E) and the death flow (0x46AC4) did not
  exist.** The death path now computes `player_scorepercoin`
  (`calc_score_per_coin`, 0x40628), wipes the slot through
  `player_resetcounters`, ranks the score-per-coin and either opens initials
  entry (rank 0-9, 0x0A8C dwell) or loads the 0x0258 GAME OVER dwell.
  `player_death_sequence` (0x49DE6) is the complete editor: the ±0xA0 velocity
  accumulator, the accelerating repeat delay, `name_entry_step_char` (0x55440),
  the Magic/Fire commit with its 0x78-frame arming gate and the backspace
  glyph, and the `write_high_score_entry` insertion at 0x4A0CA.
- **S-3 · `update_monster_spawn_bonus_from_score_per_coin` (0x48B58) was
  missing.** `monster_spawn_probability_bonus` (0x90405F) now gains
  `(party score >> 14) / party coins` at the level handoff (0x4834E) and a
  re-coin walks a positive value back one step (0x42C30).
- **S-4 · session resets leaked.** `player_resetcounters` (0x43360) and
  `player_resetall` (0x4341E) are implemented, called unconditionally from
  `start_attract_screen` (0x4446E) and from the DEMO arm of
  `start_attract_to_game` (0x4424A), so no inventory, power, timer or status
  survives into an attract screen or a fresh session.
- **S-5 · the status-8 exit animation delay was dropped.**
  `player_exit_sequence` sets status 8 (0x52C66), stands the exit-animation MOB
  up in `SLOT_EXIT_ANIMS`, and the level only ends when the last dissolve
  finishes (0x4A646-0x4A6E6 → 0x4A748-0x4A78C). The port's own death animation
  shares the byte, so `Player.exit_pending` keeps the two tails apart.
- **S-6 · locked treasure was a walk-in pickup.** Type 0x2F goes to the
  unhandled tail (jump table at 0x511CE), so a chest costs no key and pays
  nothing on contact; the supershot arm in `shots.py` owns its destruction.
- **S-7 · `dialog_first_encounter` dropped its numeric value.** Records 8-15
  share ROM line 0x59D80, and the value is now drawn into its gap as a
  two-digit right-aligned field (0x4C63C-0x4C67A): "PLAYER LOSES nn HEALTH".
- **S-8 · a fresh/absent/corrupt EEPROM booted on `game_settings = 0`.** It now
  installs `game_default_settings` (ROM 0x40070 = 0xE090) and synchronises
  `eeprom_settings_cache`, matching `one_time_init`'s bit-12 arm — which also
  means a factory cabinet has attract sound on, as the hardware does.
- **S-9 · the post-loop ran during the attract demo.** The "processed player"
  local is bumped at 0x4A8B4, which sits inside the `game_mode == 0` arm of the
  branch at 0x4A8A2 — the demo arm at 0x4A8F2 reads its joystick through
  `demo_ptr` and rejoins the common path at the stun gate without touching it.
  0x4ACD4 gates the **whole** post-loop on that local, so the port counted
  every active player unconditionally and let `idle_timer` and `escape_timer`
  run on the attract screen: timed doors could open and, after 0x5208 frames,
  the demo maze's walls would have been converted into exits. The counter is
  now written exactly where the ROM writes it, and the key accumulation moved
  to the active tail at 0x4AC8C, so a transporting player no longer counts and
  a stunned key holder still does.

### Second-pass audit · combat, rendering and integration (S-10 … S-17)

- **S-10 · sound fast path:** `sound_play` now sends immediately when the latch
  accepts, queues only on busy/holdoff, and logs each accepted command once.
- **S-11 · marker/MOB fidelity:** exact 0x8000/0x8001 marker words, live-slot
  chain-pointer preservation, solid forcefield hubs, hero spawn geometry and
  hardware-size clipping are implemented.
- **S-12 · player/session tails:** paid/free coin gating, full 32-word health
  table, ADD.L wrap, preserved commit health, high-score/continue lifecycle,
  forcefield clamp/cadence, welcome timing, spawn resets and late-join secret
  eligibility now match the ROM.
- **S-13 · rendering:** Wizard/Sorcerer picture ambiguity, SLIP top-edge culling,
  deterministic playfield RNG, effect/transition dispatch and all hero dissolve
  frames are fixed.
- **S-14 · combat data:** the thief collision table is 64-byte exact; potion
  blasts use the screen cull; generators use all eight wrapped candidates,
  proximity clearance, facing, size and initial art.
- **S-15 · projectile motion:** lobber accumulators, monster shot low-word
  geometry/art/depth and dragon breath channel/tier/counter/picture state are
  implemented.
- **S-16 · dragon pose:** the distinct 32-entry head-table index/sign and the
  16-entry fire-table index are both transcribed and contract-checked.
- **S-17 · core hero animation:** all four players select ROM idle/walk/fight/
  shoot/invisible pictures in the simulation core rather than the host runner.

### Final completion audit · all prior residuals

- **I-05/I-06 effects:** the four shared effect MOBs now have ROM allocation,
  picture cycles, byte aging and release. Kill sparkles and transporter/wall/
  Death dissolves no longer leak channels.
- **I-13/I-15 monsters:** exact contact, aim, culling, ray-march movement,
  animation, Super Sorcerer phases, traversal, lobber arcs and shot cadence are
  implemented and differentially checked against the ROM.
- **I-18 thief:** the route grid, movement/collision/animation engine, escape
  retracing, transporter handling, live-shot dodge, loot drop and rescheduling
  are implemented.
- **Transitions:** treasure rotation/return, moving exits, demo joins, attract
  expiry, bonuses and the complete secret-room challenge loop are implemented.
- **World/render/persistence:** forcefield segments, living walls/doors, dragon,
  exact camera clamps, ROM HUD/dialog/front-end rendering, high scores and both
  maze rotations are implemented.
- **Cleanup:** dead stub infrastructure and duplicated sound helpers were
  removed.

### I-02 · WP-5 · full corner-squeeze geometry

`squeeze_through_check` (0x42744) and the player branch of
`corner_squeeze_geometry` (0x4FEB2) are ported from the ROM. The gate now uses
the real transportability power (word bit 11), `movement_type` recursion guard,
candidate palette/shape exclusions, the `joystick_nibble_to_direction` table at
0x580FC, and the packed neighbour deltas at 0x5B64A/0x5B65C. An invulnerable
player can squeeze past a blocking flank or phase through a one-cell permitted
object; monster, player-start, exit, dragon, treasure-lock, and transporter
shapes reject exactly as in the ROM, including the top-border wrapped-row case.
The successful move uses the asynchronous transporter phase machine (dissolve,
relocate, restore and cleanup). Unicorn probes of the ROM confirmed the
empty-neighbour, one-cell-wall, monster-rejection, and transporter-rejection
outcomes. The directly coupled pickup bug was also fixed: the six temporary
power-ups occupy `player_powers` bits 8–13 rather than overwriting the six
character-upgrade bits 0–5.

### I-08 · WP-16/WP-20 · positioned player spawn

`player_start_inner` (0x48BEC) only recorded a spawn slot; the actual hero
placement lived in the runner. **Fixed:** `player_start_inner` now turns a
PLAYERSTART cell into the hero MOB (the marker MOB `maze.py` placed with the
hero base picture *becomes* the hero — obj_type stays PLAYERSTART so the monster
loop does not move/hurt it), sets facing/`player_in_maze`/`player_tile_pos`, and
skips a start another player already claimed. `main_start_game` now calls it so
a credited player spawns into a loaded maze, unifying the two former
`level_players_active` increment sites (resolves the I-R5 follow-up). Tested in
`test_level_transition.py`.

### I-12 · WP-15/WP-20 · level-transition orchestration

The exit path only set `game_mode = TREAS_EXIT`. **Fixed:** `exits.py` now
implements `player_exit_sequence` (0x52B40), `maze_checknum` (0x52ECA), and
`compute_next_level` (the 0x52DB2 tail) — the next-level/maze arithmetic and
cabinet rotation of doc/06 §3.2/§3.4 — and `show_level_end_bonus_screen`
(0x4D476) commits the computed level/maze, reloads the maze, and re-places the
survivors (via I-08). Tile interaction is wired into `main_move_players`, so
reaching an exit actually advances the level in the runner. Treasure-room
interleaving/rotation and per-player bonus rendering are included and verified
through real maze round trips.

### Front-end session flow · WP-16/WP-20 · attract → coin → select → play

`start_attract_to_game` (0x44204) was a stub that only flipped `game_mode` to
NORMAL, so a coin during attract left the player with no maze to spawn into.
**Fixed:** it now starts a fresh game — clears leftover per-player state (so a
demo hero cannot leak in) and loads **level 1 (maze 0)** via
`maze.reset_and_load_level`, guarded so a ROM-less environment still transitions
mode. `coincheck` falls through after it so the triggering coin also enters that
player into character select (one coin to play). With the maze loaded,
`character_select_input_update` and `main_start_game` (→ `player_start_inner`,
I-08) carry the player from a coin insert through class selection to a spawned
hero. Verified end-to-end through the real `tick()` loop
(`test_level_transition.py::TestFrontEndFlow`). The runner exposes it via
`gauntpy-play --attract` (coin key `5`); `render/host.py` gained the coin-key
edge handler. The title, high-score, legend, and character-select game routines
now write the same alpha VRAM consumed by the compositor's generic alpha pass.
They and the HUD use the **real ROM alpha font** (`gex.alphafont` decodes
`136043-1104.6p`'s 8x8 glyphs; `render/text.py` retains a PIL fallback), so the
text is the cabinet's own characters, not a placeholder. The **DEMO attract
screen** now loads maze 102's MOBs and drops the scripted Elf in
(`attract_demo_init`), so the demo rotation shows a real world; and the
**level-end bonus screen** renders the ROM's per-player
`100 x COINS / TREASURES x / BONUS =` rows (`100 x players x coins x treasures`,
§16; treasures counted by `player_tile_interact`, the world frozen on the
TREAS_EXIT phase) before the next maze loads.

**Resolved (title-logo tiles).** The extracted 96-MOB layout was correct, but
the first reconstruction placed rows by raw packed Y. MAME renders motion
objects at negated Y, so normalizing with `dest_y = max_raw_y - raw_y` restores
the six bands in top-to-bottom order. MAME's `ROM_RELOAD` also confirms gex's
existing 0x2000+ bank mapping already accounts for the rendered-code `^ 0x800`;
no decoder change was needed. `gex/data/title_logo.jsonc` now stores only the
reverse-engineered segment layout, `gex.title_logo` decodes its pixels from the
user's ROMs, and `AssetStore.title_logo` supplies the native 328x48 image to the
full-screen title renderer. The attract-timer-expiry caller at 0x448CE is wired.

### I-23 · WP-13/WP-2 · camera vs renderer scroll convention reconciled

`main_scroll_playfield` writes the ROM's *hardware* scroll registers (X shifted
by the 0x68 centering, Y the *inverted* `0x1E8 − midY − 0x6C`), while the
renderer wants a plain viewport top-left; feeding one to the other put the hero
off-screen, and the runner papered over it with its own `_center_camera`.
**Fixed:** the camera stays ROM-faithful (its tests unchanged), and a single
`camera.viewport_scroll(state, w, h)` recovers the party midpoint the registers
encode and re-centres it for the renderer's viewport, clamped to the 512px maze.
`render_frame` calls it once and hands the result to the playfield and MOB
layers; the runner's `_center_camera` is gone (spawn framing now uses the real
`camera.snap_camera`, and `main_scroll_playfield` inside `tick()` drives the
follow). The exact asymmetric ROM clamps, including bottom geometry, are
covered by tests.

### I-24 · WP-3 · placed-object pictures written at level setup

`maze.py` left every placed object's `mob_picture` at 0, so the runner had to
stamp wall markers and base pictures in two after-load passes. **Fixed:**
`maze._create_generic` now writes each object's picture from the master
`mazeobj_base_picture_tbl` (0x5868C, via gex `objparams.base_picture`) at
placement. That one table already encodes the collision-wall marker (`0x8000`
for solid walls, which `players._slot_is_blocking` reads), real sprites for
movable walls / doors / monsters / items, and the `0x8001` "own-MOB" markers
(left at picture 0). The runner's two passes are gone. **Collision follow-up
done:** `players._slot_is_blocking` now blocks on obj_type too, so movable walls
(real sprite `0x20F6`, not the `0x8000` marker) are solid again; static/trap/
random walls still block via the `0x8000` marker. Forcefield contact uses the
packed segment table rather than treating hubs as beam cells.

### I-R1 · WP-6/WP-11 · `forcefield_live_color` / `forcefield_color` conflict

WP-6 added `forcefield_live_color` to state.py's WP-11 block before WP-11
landed; WP-11 independently added `forcefield_color` for the same RAM address
(0x904046). **Fixed:** removed `forcefield_live_color`; kept `forcefield_color`.

### I-03 · WP-7 · Monster kill condition (resolved from the docs)

Was implemented as `new_health ≤ 0` (4 damage-1 hits for a ghost) per an
erroneous task brief. §26, PLAN §26, and book §11 all specify the live window
`[base-2, base]`, and potions.py already implemented it. **Fixed:** shots.py now
destroys a monster when the hpos nibble drops below `base-2` (a ghost spawned at
base 4 dies in 3 hits); `test_shots.py` updated. Ground rule 8 (doc wins).

### I-07 · WP-5/WP-13 · `player_tile_pos` / `player_in_maze` ownership

The camera was deriving these arrays itself. **Fixed:** `main_move_players`
(WP-5/6) now maintains them each frame from the player's pixel-derived current
cell, and `main_scroll_playfield` only reads them. The isolated camera tests set
the arrays directly.

### I-14 · WP-8 · Super Sorcerer placement

Was re-aim only. **Fixed:** `_supersorc_place` now performs the documented
relocation — all four players cyclically, three directions behind facing (biases
{0,−1,+1}, clear runs {4,3,3}), rows 1–31, with an eight-cell proximity
rejection — relocating the MOB via `move_slot`. Covered by a new test.

### I-16 · WP-14 · `mob_effect_anim_counter` byte wrap

**Fixed:** `main_score_update` now masks the increment with `& 0xFF`.

### I-R2 · scan · Player current-cell contact used the stale spawn slot

Players kept a fixed record `mob_slot` and roamed via `hpos`/`vpos`. Monster and
thief contact checks compared against `player.mob_slot`, so a moved player could
only be hit at their **spawn** cell. **Fixed:** `monsters._player_in_cell` and
`thief._overlaps` derived the player's current cell from pixel position.
Regression test added (`test_contact_uses_current_cell_not_spawn_slot`).
Superseded by S-63: the record migrates, so `player.mob_slot` *is* the current
cell and both helpers ask the cell directly.

### I-R3 · scan · Players never died

`main_health_countdown` drained health into negative values but nothing
transitioned a player to `DYING` at zero, so a dead player kept playing forever.
**Fixed:** `main_move_players` now transitions an active player with
`health ≤ 0` to `DYING` (clamps health to 0, resets timers, decrements the
active count, plays the low-health cue). Two regression tests added.

### I-R4 · scan · Joystick direction bits were wrong (input.py / WP-5)

`input.py` and the inlined constants in `players.py` placed the four directions
at bits 2–5, which read the unconnected spare lines (bits 2–3) for UP/DOWN and
swapped LEFT/RIGHT. `05_data_reference.md` §3.11 (and §6.2 demo format, §22
character select) put directions at bits 4–7: RIGHT=4, LEFT=5, DOWN=6, UP=7.
**Fixed:** corrected `JOY_UP/DOWN/LEFT/RIGHT` (and `JOY_DIRECTIONS = 0xF0`) in
`input.py` and the inlined `_JOY_*` in `players.py`. The movement tests passed
before only because both sides shared the same wrong constants; new tests drive
the raw-word → `direction_bits` → `player_try_move` path directly. This
supersedes the former note N-01, which wrongly called both layouts correct —
`session.py` and `attract.py` had the right bits all along; `input.py` was buggy.

### I-R5 · scan · `level_players_active` was never decremented

The active-player count was incremented only in `player_start_inner` and never
decreased. **Fixed:** the death transition (I-R3) decrements it (guarded at 0),
and `main_start_game` increments it on join so the live join/die paths balance.
The two increment sites are unified when I-09's full spawn path lands.

### I-R6 · WP-10 · Thief wealth power-bit constants were wrong

`thief._player_wealth` had `_POWER_SPEED`, `_POWER_MAGIC`, and `_POWER_FIGHT`
pointing at the wrong bits (FIGHT, REFLECT, and MAGIC respectively). The
Character Powers enum (`05_data_reference.md` §3, 0x9048E0) is
SPEED=0, ARMOR=1, FIGHT=2, SHOTSPEED=3, SHOTPOWER=4, MAGIC=5. **Fixed:**
corrected all six masks and added a targeting regression test. (Resolves the
former Q-2 — the layout was documented after all.)

### I-R7 · WP-6 · forcefield damage was charged to every player unconditionally

`main_move_players` applied forcefield contact damage to every active player on
every frame the field colour was lit, with no check that the player was
actually on a forcefield — so a hero standing still in any maze with a lit field
lost ~1 HP/frame and died in seconds. The disassembly of the call site
(0x4AA42-0x4AA68) shows the damage is gated on a zero `acid_timer` **and** a
non-zero `check_forcefield_collision` (0x53346). **Fixed:** added a minimal
`_check_forcefield_collision` (player's current cell holds a `FORCEFIELDHUB`)
and the acid gate; the forcefield test now stands the player on a field cell,
and a new test asserts a lit field off the field deals nothing. Surfaced by the
playable runner (a level-1 hero was dying while idle).

### I-04/I-11/I-13/I-17/I-19/I-20 · ROM tables transcribed from row76.bin

The six blocked ROM tables were transcribed directly from the game ROM
(`row76.bin`, which maps game address `A` to file offset `A − 0x40000`,
big-endian; verified against the known `forcefield_damage_table` at 0x5813C and
the `maze_checknum` prologue probe). Each table is now a literal in the code
with its ROM address in a comment, verified byte-for-byte against the ROM:

- **I-19 `potion_effect_matrix` (0x5DA98, 448 B)** — real 28×16 matrix in
  `potions.py`. It confirmed every documented invariant *and* replaced the
  "always kills" placeholder with real per-character damage: a Warrior potion
  weakens a Ghost 4→2 (survives); Wizard/Elf/enhanced destroy it; an Elf potion
  demotes GEN_GHOST3→GEN_GHOST1. Tests updated to the real outcomes.
- **I-17 dragon path programs (0x5D578, 5×16 B)** plus `dragon_fire_segment_tbl`
  (0x5D4B8) and `dragon_head_pics` (0x5D528) — real programs in `dragon.py`,
  selected by `dragon_path_num`. Tests updated to program 0's fire positions.
- **I-13 `monster_contact_damage_table` (0x57A2E, 64 words) — tier-exact for the
  melee families.** Disassembly of `monster_playerhit` (0x495A6) + its 10-way
  jump table (0x49620) gave the exact recipe: `row = (hpos & 0xF) −
  mazeobj_hsize_tier_tbl[type] + 2 + per_type_offset`, then
  `damage = table[row*4 + character (+0x20 armored)]`. **Implemented** for the
  types whose behaviour is unambiguous: Grunt/Demon/Sorcerer/Aux-Grunt (offset
  +3, `_CONTACT_ROW`) now scale contact damage with the monster's live strength
  tier; **Ghost** (offset +0) additionally removes itself on contact (the kill
  path — ghosts explode); **Lobber** deals **no** contact damage (its handler is
  the empty epilogue 0x49A32 — only its thrown shots hurt). Acid, Super
  Sorcerer, Death, windup and kill scores are all implemented and verified
  against ROM execution.
- **I-04 `shot_damage_base_tbl` (0x596B6), `shot_damage_rand_tbl` (0x596C2),
  `monstshot_damage_tbl` (0x596CE)** — real bytes and exact row selection in
  `shots.py`. The
  transcription also surfaced two bugs, fixed here: the rand classes are {2, 8}
  (the code had {2, 10}), and the shot-power upgrade bit is 0x10 / POWER_SHOTPOWER
  (the code had 0x1000).
- **I-11 treasure countdown speech (0x5AB64, 11 longwords)** — real speech IDs
  in `exits.py`; `_countdown_speech` now speaks the number each second.
- **I-20 demo streams (0x5818C/0x581C4/0x5825A/0x5825C)** — real recorded input
  streams in `attract.py`; `attract_demo_init` installs them and selects the
  player-1 Elf. Full 0xFE joins/stream switching and the attract-sound option
  are implemented.

### I-01 · WP-5 · Player speed — resolved by disassembly

Was a flat 2 px/frame guess. Disassembly of `main_move_players` (0x4A92C-0x4A942)
showed the speed is read from `player_speed_normal` (ROM 0x580A8, transcribed
into `players.py`) at index `character + 4 × extra-speed-power`: base
Warrior/Valkyrie/Wizard = 0x80 (**2 px**), Elf = 0x100 (**4 px**), and the
extra-speed power (POWER_SPEED_BIT 0) raises everyone to 0x100 (4 px). **Fixed:**
`player_try_move` now uses per-character speed and the `player_anim_rate`
0x580B8 boost; regression tests cover both.

### I-10 · WP-15 · Moving-exit timer — resolved by disassembly

Was 0x78 ("approximate"). Disassembly of `main_exit_move` showed the game's
`exit_timer` (0x904A08) is loaded with **#0x12C (300 frames)** both at level
setup (0x43B90) and on reload (`move.w #0x12c,(a0)` at 0x52A74). The
disassembly also confirmed the ExitMoves gate is `level_flags & 0x4000`
(= `level_flags_3 & 0x40`, as implemented) and the relocation plays sound 0x31.
**Fixed:** `_EXIT_MOVE_TIMER_RELOAD` and the state default are now 0x12C; the
reload-value test updated.

### I-09 / I-21 / I-22 · subsystem-isolation rule lifted, cross-imports wired

The subsystem-isolation rule (subsystems never import each other) existed only
to keep parallel subagents from colliding; with that constraint removed, the
three issues that were purely a missing cross-import are fixed:

- **I-09 · WP-16** — `main_start_game` now calls the real
  `players.player_join_finalize` (setting `ALIVE_HERE` and running the join
  speech / HUD hook) instead of a bare status assignment. The first-player bonus
  and `level_players_active` accounting are preserved; the MOB spawn
  (`player_start_inner`) still needs a maze (I-08).
- **I-21 · WP-20** — `one_time_init` now calls `eeprom.eeprom_load_settings`
  (config load, §5 step 6) and hands off through the real
  `attract.start_attract_screen(TITLE)`, dropping the duplicated timer constant.
- **I-22 · WP-8/WP-7** — `monster_playerhit` now calls
  `shots.death_damage_accumulate` (made public) on Death contact, adding 4 (or 3
  with the armor power) to the per-player counter and dismissing the Death MOB
  past 200 — so Death is killable by contact, not only by supershots. Two
  regression tests added.

---

## Notes (not bugs, but worth remembering)

### N-02 · WP-7 · `player_create_shot` — implemented (firing)

**Resolved.** `player_create_shot` now spawns a shot in the firing player's
fixed channel (slot `player_index + 1`, in `SLOT_PLAYER_SHOTS`), seeding
`shot_dx/dy` from facing and gating on a free channel so a held Fire button
fires one shot at a time; the shot-speed power (bit 3) raises the speed. It
mirrors `monsters.monster_create_shot`. Tested in `test_level_transition.py`.
**Velocities now exact:** `_SHOT_VELOCITY` is transcribed from the ROM
`shot_velocity_x/y` tables (0x576E2/0x57792) — base rows 0-7 and the
shot-speed-power rows 8-15 — mapped by `_DIR_TO_SHOT_ROW`. This corrected the
diagonal speed: the ROM moves diagonals 0x100 (4 px/axis) vs cardinals 0x180
(6 px), where the old delta×speed model moved diagonals 6 px/axis (too fast).
The character shot sounds (Axe/Sword/Fireball/Arrow), projectile animation,
monster velocities and lobber arcs are implemented.

### N-03 · players.py · shadowed `@stub player_try_move` placeholder

**Resolved.** The isolation-era `@stub def player_try_move` and its now-unused
stub import were removed; only the real WP-5 implementation remains.

### N-04 · isolation-era duplication cleanup

**Resolved.** Subsystems now share `sound.sound_play`; the duplicated local
queue helpers and dead isolation-era stub marker are gone.

### N-05 · `play.py` · the playable runner and its remaining gaps

`gauntpy.play` (`uv run gauntpy-play`) is a minimum playable runner: it loads a
maze, drops a hero in (via the real spawn path, I-08), and drives the real
`game_frame` at 60 Hz in a pygame window with keyboard movement, genuine wall
collision, HUD, and health drain. The hero renders with its **real class
sprite** (gex's `heroes.jsonc`; see N-06); pictures come from `maze.py` now
(I-24) and the camera is the real `main_scroll_playfield`, converted to the
viewport by the compositor (I-23 — the old `_center_camera` workaround is gone).
Item pickup, firing (N-02),
and **level-to-level exits (I-12)** all work — walk into an exit and the next
level loads, so the runner now spans multiple levels. The **front-end flow**
works too: by default the runner drops mid-level, but `--attract` boots through
`one_time_init` → attract and lets you insert a coin (key `5`), pick a class,
and press Magic to start, driving the genuine `coincheck` →
`character_select_input_update` → `main_start_game` → spawn path (see the
"Resolved · front-end session flow" entry). The attract, high-score, legend,
and character-select routines write alpha VRAM rendered in the **real ROM alpha
font**, so `--attract` shows arcade-faithful text throughout, not a dark
window; the DEMO attract screen shows a real maze, each exit plays a "LEVEL
COMPLETE" bonus tally, and the title uses the ROM-native pixel wordmark. It is
the integration harness that surfaced I-R7, I-23, and I-24 — all now resolved.

### N-06 · gex sprite-data coverage (complete)

gex's `data/` now carries every table gauntpy needs to render the game world,
all extracted from the ROM (doc/04 §8, doc/05 §5–§8) and consumed by
`assets.py`. An audit confirms **every placed maze object type (0–63) resolves
a sprite** (the two `0x8001` marker types, EXIT/TRANSPORTER, render via their
own animated MOBs by design):

- **Monsters** — all ten families, **walk + idle** (`monsters.jsonc`; idle from
  the 0x40DB2 pointer table, equals walk for the four NULL-moving families).
- **Heroes** — four player classes, walk/idle/fight/shoot (`heroes.jsonc` +
  `heroes.py`, per-class palette).
- **Thief** (mugger reuses it) — walk/idle/walkcompact (`npcs.jsonc` +
  `npcs.py`).
- **Projectiles** — three shot tables, 2×2 sprites (`projectiles.jsonc` +
  `projectiles.py`, tile set + `projectile_stamp`).
- **Dragon** — head/body/pose/delta tables and runtime four-segment composition
  (`dragon.jsonc` + `dragon.py`).
- **Effects** — score-popup / floating-star picture tables (`effects.jsonc` +
  `effects.py`, 3×3 `star_stamp`).
- **Object parameter tables** — the four master 64-entry tables
  (`objparams.jsonc` + `objparams.py`: `base_picture`, `hpos_correction`,
  `vpos_offset`, `hsize_tier`, 0x5858C–0x5870B). **`base_picture` is the key
  addition**: it maps each object type to its picture, which is what lets
  gauntpy set `mob_picture` on decoded maze objects (previously always 0) so
  items, treasure, keys, potions, power-ups, and generators all render.
- **Items** — full pickup stamps already present; `items.py` now also exposes
  `item_stamp_for_picture` / `ITEM_PICTURE_INDEX` so a placed object's picture
  resolves straight to its stamp.

gauntpy's `assets.sprite()` dispatches pictures across projectiles, dragon
segments, effects, typed creatures/heroes/NPCs, items and sized raw ROM blocks.
The base-picture pass now lives in its proper
home — `maze._create_generic` writes each object's picture at placement (I-24) —
so decoded objects render end to end without any runner-side stamping. The
picture→sprite index uses explicit entity-kind disambiguation where art is
shared (notably Wizard/Sorcerer), so each MOB keeps the correct palette bank.

### Q-1 · Environment · pytest tmp-dir permission errors — RESOLVED

`test_eeprom.py` and `test_render.py` used to error with
`PermissionError: [WinError 5]` when pytest built its default `tmp_path` base on
`W:\zTEMP\TEMP` — an environment ACL quirk, not a code defect. **Fixed by the
environment owner;** the suite now runs clean with no `--basetemp` workaround.

### Q-2 · WP-6 · Distinct player-death sound

**Resolved.** Death uses the character-specific ROM commands 0x14–0x17
(Warrior/Valkyrie/Wizard/Elf).
