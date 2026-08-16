# gauntpy

A Python reimplementation of the Gauntlet II arcade game, built from the
reverse-engineering documentation in [`../doc`](../doc/INDEX.md) and
[`../book`](../book/README.md).

Not an emulator. The 68010 game code is reimplemented at the logic level while
keeping the original's structure: the same main-loop call order, the same object
model, the same tables and thresholds. Graphics data is read from the original
ROMs through [`gex`](../python-gex/README.md); sound is stubbed.

**Status: skeleton.** The simulation core, the main loop, and one worked-example
subsystem exist and are tested. The other 27 loop calls are stubs. See
[PLAN.md](PLAN.md) for the work breakdown.

## Try it

```bash
cd gauntpy && PYTHONPATH=src python -m gauntpy
```

```bash
cd gauntpy && PYTHONPATH=src python -m pytest tests -q
```

The demo prints the loop's call trace for a normal frame, shows the dialog gate
freezing exactly the sixteen gameplay calls, and shows `frame_overflow` setting
and decaying.

## What's here

| Module | What it is |
|--------|-----------|
| [`coords.py`](src/gauntpy/coords.py) | The three coordinate systems: maze cells, packed slots, world pixels, and the playfield tile grid |
| [`mob.py`](src/gauntpy/mob.py) | The MOB slot table — five parallel arrays, the doubly linked depth chain, and the 64 SLIP band heads |
| [`rng.py`](src/gauntpy/rng.py) | The game's LCG, ported from `random_core` (0x5FC2C) |
| [`state.py`](src/gauntpy/state.py) | `GameState` — the stand-in for working RAM, with the original's variable names |
| [`mainloop.py`](src/gauntpy/mainloop.py) | `game_frame` — the 28-call frame sequence as straight-line code |
| [`subsystems/`](src/gauntpy/subsystems/) | One module per work package. Every main-loop call exists with its ROM address and references; unimplemented ones are `@stub` |
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

Read [PLAN.md](PLAN.md) §3 for the ground rules and §4 for naming. The short
version: subsystem modules never import each other, everything shared goes
through `GameState`, **use the names from `doc/` and `book/`** rather than
inventing synonyms, cite every non-obvious constant with its section or ROM
address, and no floats anywhere.

Landing a work package means filling in stub bodies and deleting their `@stub`
decorators. You never wire anything up — `mainloop.py` already calls your
functions by name.

No ROM images or ROM-derived data may be committed. Tables are transcribed from
the documentation as cited source; pixels are read from your own ROMs at runtime
via `GEX_ROM_DIR`.

## License

GPL-3.0, matching the rest of the repository.
