# gauntpy

A Python reimplementation of the Gauntlet II arcade game, built from the
reverse-engineering documentation in [`../doc`](../doc/INDEX.md) and
[`../book`](../book/README.md).

Not an emulator. The 68010 game code is reimplemented at the logic level while
keeping the original's structure: the same main-loop call order, the same object
model, the same tables and thresholds. Graphics data is read from the original
ROMs through [`gex`](../python-gex/README.md); sound-board commands are captured
in a deterministic host log.

**Status.** The simulation core, the main loop, and all 28 per-frame subsystem
calls are implemented and tested. ROM data tables are transcribed from the ROMs
and verified against radare2/Unicorn. The playable runner covers boot, attract,
coin/character selection, gameplay, treasure/secret rooms, and level rotation.
See [PLAN.md](PLAN.md) and [ISSUES.md](ISSUES.md).
Contributors should also read the concise [fidelity rules](FIDELITY.md) before
changing simulation state or coordinate arithmetic.

## Play it

With [uv](https://docs.astral.sh/uv/) (recommended — it resolves the local
`gex` package, Pillow, and pygame automatically) and your Gauntlet II ROMs in
`../ROMs` (or `GEX_ROM_DIR` set):

```bash
cd gauntpy && uv run --all-extras gauntpy-play
```

A window opens at **4x scale** on a real Gauntlet II maze with your hero's
genuine class sprite. Use `--scale` to override it.

| Key | Action |
|-----|--------|
| **arrow keys** | move |
| **Ctrl / Space** | fire |
| **Alt / Enter** | Magic (also start / commit a character) |
| **5** | insert a coin |
| **P** | pause / resume |
| **F1** | show / hide the host diagnostics panel |
| **F2 / F3** | previous / next diagnostics page |
| **F4** | save a complete modeled-state JSON dump |
| **F5** | immediately load the next level |
| **F6** | give the host player one key |
| **F7** | give the host player one potion |
| **[ / ]** | select the previous / next occupied MOB |

Walls collide, the camera follows, the HUD tracks score/health, health drains,
you pick up items and open doors, you fire, and walking into an **exit loads the
next level** — the opening act plays mazes 0–4 as levels 1–5, then the cabinet
rotation takes over.

The **F1** panel is host-only: it reads an immutable post-frame snapshot and
shows mode, level/maze, camera, RNG, IT owner, demo pointers, MOB counts, and
per-player state. It does not use the arcade alpha renderer or write modeled
video/game memory. Its text remains at native host resolution when the game
raster is enlarged with `--scale`, using an anti-aliased system monospace font.
Its pages cover overview, players and raw input, decoded demo records, level
flags/timers, actor counts and raw MOB words, thief/dragon AI, display memory,
audio queues, a rolling event log inferred from snapshots while the panel is
open, and a 120-sample render-time graph. The displayed `RENDER` value is a
rolling average of the latest ten frames.

**F4** atomically saves every modeled `GameState` field, including players,
MOB tables and links, logical maze data, playfield/alpha/color RAM, path grids,
timers, inputs, and the RNG seed. Files are written under
`traces/state-dumps/`, which Git ignores; the exact path is printed to the
terminal. Resume one of those files without rerunning boot or level setup:

```bash
uv run --all-extras gauntpy-play --load-state traces/state-dumps/state-frame-....json
```

Saved states are versioned, exact runtime snapshots. Original schema-1 captures
are migrated for the handful of fields added since F4 shipped; an otherwise
incompatible schema or `GameState` shape is rejected rather than partially
loaded. Resumed sessions do not write EEPROM JSON, so loading an older gameplay
snapshot cannot roll back newer settings, high scores, or maze rotation.

F5/F6/F7 are host troubleshooting controls, not original cabinet inputs. The
level skip uses the live cabinet maze rotation and respawns active players
without the bonus/splash delay. Inventory grants update the selected host
player's game-side counters and alpha-RAM inventory display.

By default the runner drops you straight into a level. Options:

```bash
uv run --all-extras gauntpy-play --level 2 --character elf --scale 3
```

Direct play can seed inventory and temporary powers for testing:

```bash
uv run --all-extras gauntpy-play --keys 3 --potions 2 \
  --power reflective-shots --power transportability
```

`--power` may be repeated and accepts `invisibility`, `repulsiveness`,
`reflective-shots`, `transportability`, `super-shots`, and `invulnerability`.
These test-start options cannot be combined with `--attract`.

Runs use RNG seed zero by default so repeated playthroughs stay reproducible.
Select another repeatable stream with `--seed 1234`, or request a host-random
power-on value with `--seed random`. A seed applies to direct and attract starts;
loaded state dumps retain their saved RNG state and reject `--seed`.

For uninterrupted testing, suppress first-encounter pop-up boxes (speech and
gameplay effects still occur):

```bash
uv run --all-extras gauntpy-play --no-first-encounter-messages
```

Or boot through the **real front end** — attract → coin → character select →
start — exactly as the cabinet does:

```bash
uv run --all-extras gauntpy-play --attract
```

Press **5** to insert a coin, steer to pick a class, and press **Enter** to
start. The title, high-score, legend, and character-select screens render in the
cabinet's **own alpha-ROM font**, while the native 328x48 title wordmark is
assembled from the graphics ROMs at runtime, driven by the genuine `coincheck`
→ `character_select` → `main_start_game` path.

## Try the diagnostics

```bash
cd gauntpy && uv run gauntpy        # headless loop-structure demo (no ROMs/deps)
cd gauntpy && uv run pytest -q      # the test suite
```

The demo prints the loop's call trace for a normal frame, shows the dialog gate
freezing exactly the sixteen gameplay calls, and shows `frame_overflow` setting
and decaying.

For deterministic gameplay investigations, use the scenario runner:

```bash
cd gauntpy
GEX_ROM_DIR=../ROMs uv run gauntpy-scenario list
GEX_ROM_DIR=../ROMs uv run gauntpy-scenario run level7-seam --every 4
GEX_ROM_DIR=../ROMs uv run gauntpy-scenario run forcefields \
  --output traces/scenarios/forcefields.json
```

The catalog includes level 1, the level-7 seam, forcefields, dragon range,
attract-demo playback, and point-blank combat. Traces are compact JSON and
deterministic from the same committed state.

Without uv, everything still runs from the source tree directly (set
`PYTHONPATH=src`, and `GEX_ROM_DIR` for the graphical runner):

```bash
cd gauntpy && PYTHONPATH=src python -m gauntpy
cd gauntpy && PYTHONPATH=src python -m pytest tests -q
cd gauntpy && GEX_ROM_DIR=../ROMs PYTHONPATH=src python -m gauntpy.play
```

## What's here

| Module | What it is |
|--------|-----------|
| [`coords.py`](src/gauntpy/coords.py) | The three coordinate systems: maze cells, packed slots, world pixels, and the playfield tile grid — plus the native MOB H/V word encoding (position in bits 15-7, vertical measured up from the playfield floor) |
| [`mob.py`](src/gauntpy/mob.py) | The MOB slot table — five parallel arrays, the doubly linked depth chain, and the 64 SLIP band heads |
| [`rng.py`](src/gauntpy/rng.py) | The game's LCG, ported from `random_core` (0x5FC2C) |
| [`state.py`](src/gauntpy/state.py) | `GameState` — the stand-in for working RAM, with the original's variable names |
| [`mainloop.py`](src/gauntpy/mainloop.py) | `game_frame` — the 28-call frame sequence as straight-line code |
| [`subsystems/`](src/gauntpy/subsystems/) | The 28 main-loop calls and supporting systems, each tied to its ROM address and references |
| [`subsystems/input.py`](src/gauntpy/subsystems/input.py) | `input_debounce` — the worked example of a completed work package |

`game_frame` calls its subsystems by name, directly — the loop is a function,
not a table something interprets. [test_mainloop.py](tests/test_mainloop.py)
parses it and checks the call order against
[`main_loop_contracts.csv`](../doc/generated/main_loop_contracts.csv), so the
sequence cannot drift from the ROM's without a test failing.

## Design in one paragraph

A thing in the maze is a **MOB slot**: one index into five parallel arrays of
16-bit words. For dynamic objects the slot number *is* the packed maze cell
address, so "what is in that cell?" is arithmetic rather than a search, and
moving a monster means moving its record to another slot. All slots are threaded
onto one doubly linked chain sorted by depth, which serves as both draw order and
iteration order; 64 SLIP bookmarks index into that one chain so the renderer can
skip to the bands it needs. The main loop advances every system by exactly one
frame, sixty times a second, through a fixed sequence of 28 calls — sixteen of
which are skipped as a block whenever a message box is up.

## Contributing

Read [PLAN.md](PLAN.md) §3 for the ground rules and §4 for naming. Reuse shared
subsystem APIs instead of duplicating them, keep persistent state in
`GameState`, **use the names from `doc/` and `book/`**, and cite every
non-obvious constant with its section or ROM address. `mainloop.py` calls the
28 subsystem entries directly in ROM order.

No ROM images or ROM-derived data may be committed. Tables are transcribed from
the documentation as cited source; pixels are read from your own ROMs at runtime
via `GEX_ROM_DIR`.

## License

GPL-3.0, matching the rest of the repository.
