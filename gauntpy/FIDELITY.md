# gauntpy fidelity rules

This is the short, authoritative checklist for changes to gauntpy. Detailed
evidence remains in `../doc/`, generated contracts, and the book.

## Runtime invariants

1. **Native MOB words.** H/V positions are the arcade's words: position in
   bits 15–7, low field in bits 6–0, one pixel = `0x80`. One 512-pixel maze is
   one 16-bit wrap.
2. **Vertical points up.** Native V counts upward from the playfield floor.
   Convert to downward screen Y only through `coords.py`.
3. **Coordinate boundary.** `coords.py` owns encoding, masks, pixel/slot
   conversion, biased logical cells, position replacement, and deltas. Do not
   introduce literal `0xFF80`, direct H/V `<< 7`/`>> 7`, or hand-packed
   pixel-to-cell formulas elsewhere. `test_coordinate_boundaries.py` enforces
   this.
4. **Identity is location.** Dynamic MOB records, including live players, move
   to the packed maze slot they occupy. Fixed slots 1–29 are the documented
   projectile/effect/score/transition reservations and use explicit depth keys.
5. **Low bits are not coordinates.** H low bits contain software flags and
   palette; V low bits contain sprite size. Position updates preserve them.
6. **Player identity.** A live player record stores the player index in the
   state field. Never infer the victim solely from a picture or color.
7. **Palette routing.** Every MOB hpos nibble resolves directly through the
   authoritative 256-word `GameState.mob_color_ram`; slots 12–15 are the live
   player-color palettes. Hurt, power, effect, and title animation are game-side
   color-RAM writes, never renderer overrides. Alpha/HUD code likewise writes
   complete words to `GameState.alpha_ram` / `alpha_color_ram`; render modules
   must not reconstruct content from gameplay state or sampled UI RGBA constants.
8. **Simulation/render boundary.** Simulation writes native state. Rendering
   reads it and performs screen-coordinate conversion; rendering state never
   feeds gameplay. The playfield's authoritative pixels are the 4096
   column-first words in `GameState.playfield_ram`, resolved through the live
   128-word `playfield_color_ram` and `playfield_shadow_color_ram` banks;
   `maze.data` is logical gameplay/catalog state, never a renderer input.
   Gameplay VBLANK effects, including the HUD-logo gradient at alpha color RAM
   `0x91002E`, must likewise mutate modeled color RAM before rendering.
9. **Randomness.** Route every game draw through `state.getrandom()`. Literal
   ROM tables carry their address in a nearby comment.
10. **Evidence order.** Running ROM/MAME and direct ROM disassembly outrank
    prose. Correct stale documentation when stronger evidence disagrees.
11. **Effective table addresses.** For PC-relative ROM operands, transcribe from
    the CPU's resolved effective address (and cross-check the loader/catalog),
    not from the textual address of the following instruction.
12. **Display lifecycle writes.** Screen transitions must port their alpha-RAM
    teardown as well as setup. In particular, `maze_hide` makes columns 29–41
    opaque and `maze_show` clears every other alpha column while preserving them.
13. **Large text is variable-width.** The OS quad record's right-hand word is
    also a width flag: zero means a one-cell glyph. Writers must return and use
    the ROM's one/two-cell advance rather than positioning by character count.
14. **Relocated markers need fresh geometry.** A packed MOB slot is identity and
    location, but copying a marker record does not recompute its H/V words.
    Relocation routines that the ROM rebuilds (such as moving exits) must derive
    coordinates from the destination slot.
15. **Level-start common tails are state resets.** Calls after player placement
    (`thief_setup`, `maze_show`, `idle_timer` clear) apply to every handoff arm;
    do not bury them in only ordinary or secret-room setup.
16. **Transport routes are bidirectional state.** Player transport writes the
    forward source link and reverse destination/landing direction. A thief first
    resolves the linked destination, then reads the opposite table at that ID
    for its arrival direction; one route word cannot substitute for both reads.
    While that shared transition timer is nonnegative, the actor's ordinary
    movement loop must remain gated; only the transition owner moves its record.
17. **Persistent spawn identity outlives its marker.** Maze setup stores the
    randomly selected PLAYERSTART slot before replacing that marker with floor.
    First starts and continues use the saved word, not a search for a marker that
    no longer exists.
18. **Dragon movement probes gate targeting.** In `dragon_choose_move_direction`,
    the two leading `0x8000` wall checks occur before the player/distance is
    published. Flame-lock targeting must not bypass blocked footprint probes.
19. **MOB size outranks asset-family defaults.** A picture's table family does
    not determine its dimensions. Decode the live V-word size; in particular,
    ordinary projectiles are 2x2 but max-tier dragon breath is 3x3.
20. **Collision tags survive representation shifts.** ROM helpers may tag a
    doubled MOB index before the caller shifts it back to a packed cell. Preserve
    the corresponding shifted tag (`0x1000` doubled becomes `0x0800`) through
    dispatch instead of reducing every collision result to a bare slot.
21. **Prompt setup and live fields are separate writes.** Literal OS strings can
    deliberately leave holes for later per-frame writers. Port both owners; the
    continue prompt's seconds come from `main_attract`, not
    `show_continue_prompt`.
22. **Escaped thief loot returns through random placement.** The thief/mugger
    departure clears its live MOB at the recorded start cell and stores carried
    loot for `maze_addrandompickups`; the next level recreates that pickup using
    the ROM's empty-cell walk rather than retaining an actor or renderer overlay.
23. **Info-panel headers are maze-mode state.** A whole-panel rebuild first
    clears rows 0–6. Only maze numbers below 0x68 restore the dungeon logo and
    level field; treasure/secret rooms write `TIME:` over that blank region.
    Do not treat the ordinary header as permanent HUD decoration.
24. **Corner transport has a zero pad identity.** `corner_squeeze_geometry`
    stores zero in `player_tport_type`; at the move milestone that zero enables
    `pf_replace(..., floor)` for an ordinary `0x8000` landing wall. Preserve the
    logical maze, MOB marker, and playfield descriptor write together.
25. **High-bit collision pictures still use live geometry.** The player probe's
    `0x8000` branch rounds the candidate MOB's live H/V words; it does not rebuild
    them from the packed slot. Door and item pictures can have bit 15 set while
    carrying deliberate placement corrections.
26. **Dragon damage is a live MOB palette change.** Counted hits 1–2, 3–5, and
    6–8 rewrite the primary dragon segment's hpos palette nibble to 8, 7, and 6.
    Do not represent this progression as a renderer tint.
27. **Reserved row zero is never a player probe origin.** The ROM keeps the
    current `active_mob_ids[player]` slot in D2. Gauntpy's one-pixel integration
    may derive an intermediate body cell, but it must fall back to the live
    record when that cell is in reserved slots 0–31. Horizontal flank gates use
    doubled-slot thresholds, so row zero is not an upper flank from row one.
    Keep the explicit demo compatibility path until its retained MAME route can
    survive removal; do not weaken normal gameplay geometry to preserve it.
28. **Special actors may have actor-specific placement anchors.** Super
    Sorcerer placement begins at the target player's live MOB slot and writes
    its destination H position four pixels left of the cell. A generic
    `pixel>>4` start or cell-origin placement changes its firing line.
29. **Hidden-potion pictures encode permanent powers.** Type 61 picture
    `(picture-0xA728)/4` is power ID 0–5. Only a duplicate grant falls through
    to the inventory-potion/solo-score branches.
30. **Visible sprite overlap is not collision penetration.** Player collision
    compares corrected MOB anchors with a strict 0x7C0 window and resolves H
    before V. A sprite can visibly approach or slide into wall artwork before
    the next anchor comparison blocks; do not tighten this with sprite boxes
    unless ROM/MAME diverges at the same state.
31. **Dialogs are part of recorded-demo timing.** A first-encounter call can
    freeze `main_move_players` and its demo pointer while animation work outside
    the dialog-gated world band continues. Port the producer's dialog write;
    never compensate by retiming or editing the ROM input stream. Host options
    that suppress gameplay hints must not suppress DEMO dialogs.
32. **Resolve stack arguments before porting alpha rectangles.**
    `alpha_clear_rect` consumes `(column, width, row, height)` even though 68000
    callers push those values in reverse order. Transpose the call, not the
    visual result, and regression-test the exact transparent cells.

## Investigation workflow

1. Reproduce the reported behavior with the smallest deterministic scenario.
2. Fix that behavior and its tightly coupled causes first. Do not start a
   whole-codebase audit unless the user requests one or the work is an explicit
   audit batch.
3. Run the smallest targeted tests and affected ROM contract generators during
   iteration. Run the complete gauntpy suite once at the end.
4. Record terse source/ROM findings while working. Update `doc/`, `book/`, and
   `ISSUES.md` once per completed batch instead of repeatedly during iteration.
5. Commit the completed, verified batch at the end of the turn. Do not include
   ROMs, local EEPROM/NVRAM, `extra_docs/`, or generated traces.

## Deterministic scenarios

`gauntpy-scenario` provides reusable traces for:

- `level1`
- `level7-seam`
- `forcefields`
- `dragon-range`
- `demo-playback`
- `close-combat`

Use these before writing an ad hoc reproduction. Save disposable output under
`traces/scenarios/`, which Git ignores.

## MAME traces

Whenever an investigation needs MAME:

1. Search `traces/mame/` for a reusable capture first.
2. Save the Lua script, raw trace, and local metadata under
   `traces/mame/<scenario>/<timestamp>/`.
3. Metadata must record MAME version, driver, ROM hashes, exact command,
   watched addresses, initial RAM writes, input script, and frame convention.
4. Keep the trace for future comparisons, document conclusions in the normal
   references, and **never commit the trace files**.

See `traces/README.md` for the local workspace convention.
