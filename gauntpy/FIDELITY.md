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
9. **Randomness.** Route every game draw through `state.getrandom()`. Literal
   ROM tables carry their address in a nearby comment.
10. **Evidence order.** Running ROM/MAME and direct ROM disassembly outrank
    prose. Correct stale documentation when stronger evidence disagrees.

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
