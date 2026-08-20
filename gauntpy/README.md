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

## Play it

With [uv](https://docs.astral.sh/uv/) (recommended — it resolves the local
`gex` package, Pillow, and pygame automatically) and your Gauntlet II ROMs in
`../ROMs` (or `GEX_ROM_DIR` set):

```bash
cd gauntpy && uv run --all-extras gauntpy-play
```

A window opens on a real Gauntlet II maze with your hero's genuine class sprite.

| Key | Action |
|-----|--------|
| **arrow keys** | move |
| **Ctrl / Space** | fire |
| **Alt / Enter** | Magic (also start / commit a character) |
| **5** | insert a coin |

Walls collide, the camera follows, the HUD tracks score/health, health drains,
you pick up items and open doors, you fire, and walking into an **exit loads the
next level** — the opening act plays mazes 0–4 as levels 1–5, then the cabinet
rotation takes over.

By default the runner drops you straight into a level. Options:

```bash
uv run --all-extras gauntpy-play --level 2 --character elf --scale 3
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
| [`coords.py`](src/gauntpy/coords.py) | The three coordinate systems: maze cells, packed slots, world pixels, and the playfield tile grid |
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
