# gauntpy

A Python reimplementation of the Gauntlet II arcade game, built from the
reverse-engineering documentation in [`../doc`](../doc/INDEX.md) and
[`../book`](../book/README.md).

Not an emulator. The 68010 game code is reimplemented at the logic level while
keeping the original's structure: the same main-loop call order, the same object
model, the same tables and thresholds. Graphics data is read from the original
ROMs through [`gex`](../python-gex/README.md). Sound-board commands are captured
in a deterministic host log. With `--sound`, the pygame harness plays
command-named static WAVs without emulating the separate sound CPU.

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
genuine class sprite. Use `--scale` to override it. Audio is off by default;
pass `--sound` to enable playback from the local recording library. The host
normally limits simulation to 60 frames per second; `--uncapped` removes that
wait and disables sound for accelerated testing while retaining one complete
game update per rendered frame.

Put the locally generated recordings in `sounds/`, named
`0xNN_description.wav` by sound-board command byte. The directory is ignored
because the recordings are ROM-derived and are not distributed by this
repository. `GAUNTPY_SOUND_DIR` may point at another library. The directory is
examined only with `--sound`; if requested playback has no library, the runner
prints a warning and continues silently.

The host plays effects concurrently, serializes speech through the sound
board's priority queue rules, loops Death/forcefield/slow-motion beds until
their matching stop commands, and applies the theme and treasure-music fades.
All 62 sequence commands also carry their verified physical-channel and
priority records: equal-priority members replace, higher-priority members
suppress lower playback, and a lower sequence can resume when the winner ends.
Because each local WAV is already mixed, partial suppression inside one
multi-channel recording cannot separate its individual stems.
This consumes accepted `sound_log` bytes only; it does not alter the game's
sound ring, timing, or modeled state.

For repeatable performance work, run a fixed number of measured frames:

```bash
uv run --all-extras gauntpy-play --benchmark
uv run --all-extras gauntpy-play --benchmark 2000 --scale 1
uv run --all-extras gauntpy-play --benchmark 600 --workload benchmark-generators
uv run --all-extras gauntpy-play --benchmark 600 --workload all
```

`--benchmark [FRAMES]` defaults to 600 measured frames after up to 30 warm-up
frames. It disables the limiter, sound playback, and external EEPROM writes,
then reports mean, median, nearest-rank p95, minimum, and maximum durations for
host input/event sampling, the complete game update, game-raster composition
through window blitting, total presentation through display flip, and the
complete host loop. The raster interval is nested inside presentation, and
both are nested inside the complete loop; they are not additive columns.
`--workload NAME` builds a repeatable named workload before measuring it;
`--workload all` runs and reports every workload separately, with the requested
measured-frame count applied to each one.

Use the timed graphical stress workload to exercise different display and
simulation shapes continuously:

```bash
uv run --all-extras gauntpy-play --stresstest 60
uv run --all-extras gauntpy-play --stresstest 60 --workload benchmark-mobs
uv run --all-extras gauntpy-play --list-workloads
```

`--stresstest SECONDS` runs uncapped and silent, cycling through the ROM-backed
TITLE, DEMO, dragon level, moving/fake-exit level, SCORES, and LEGEND setup
paths plus synthetic open-arena, generator, monster-family, random-wall, and
cyclic-wall fixtures, followed by the pathological suite below. Select one
workload with `--workload`; the default and `--workload all` rotate through the
complete catalog. The synthetic fixtures play deterministic
direction/Fire/Magic scripts, while the ROM-backed phases continue to use the
normal game-side screen or level setup routines.

Scenario-backed workload names are exactly their `.gsc` filename stems, so the
name printed in the console can be pasted directly after `--workload`. The
generator and monster benchmarks contain 81 generators and 196 ordinary
monsters respectively, with dense subsets inside the initial camera view.

Benchmark and stress modes check the MOB depth chain, reciprocal links, and
SLIP bookmarks after every game update and stop at the first inconsistent
frame. This check is read-only host instrumentation; it does not repair state
or alter game logic. Synthetic workloads are engineering fixtures for load,
regression, and profiling coverage, not evidence of original-game behavior.

| Pathological workload | Edge under test |
|---|---|
| `pathological-ten-dragons` | ten 2x2 bodies contending for one dragon state machine |
| `pathological-slot-saturation` | 899 linked records with almost no free maze cells |
| `pathological-projectile-channels` | all 12 fixed player/demon/lobber channels seeded around the initial view |
| `pathological-four-players` | four visible heroes alternate movement, Fire, and Magic phases |
| `pathological-boxed-generators` | generators repeatedly finding no legal spawn |
| `pathological-overlapping-specials` | exits/transporters overwriting dragon segments |
| `pathological-wall-intersection` | moving, random, cyclic, and forcefield systems together |
| `pathological-wrap-seams` | actors and projectiles crowded against both wrap seams |
| `pathological-counter-wrap` | events before and after frame `0xFFFF -> 0x0000` |

The four-player and projectile fixtures use setup hooks in the host workload
module to join the extra heroes and seed the fixed shot channels through normal
game-side creation routines. The counter fixture starts its modeled frame word
at `0xFFF0`. These hooks prepare state only; no stress-only branches run inside
the simulation.

| Key | Action |
|-----|--------|
| **arrow keys** | move |
| **Ctrl / Space** | fire |
| **Alt / Enter** | Magic (also start / commit a character) |
| **5** | insert a coin |
| **P** | pause / resume |
| **gamepad D-pad / left stick** | move |
| **gamepad A / button 1** | fire |
| **gamepad B / button 2** | Magic (also start / commit a character) |
| **gamepad Back / button 7** | insert a coin |
| **gamepad Start / button 8** | pause / resume |
| **F1** | show / hide the host diagnostics panel |
| **F2 / F3** | previous / next diagnostics page |
| **F4** | save a complete modeled-state JSON dump |
| **F5** | show the next level's normal `LEVEL n` splash |
| **F6** | give the host player one key |
| **F7** | give the host player one potion |
| **F8** | pause / resume the current treasure or secret-room timer |
| **F9** | arm this maze's secret trick; perform it and exit |
| **F10** | force the host player into a secret room on exit |
| **[ / ]** | select the previous / next occupied MOB |

The first connected gamepad is used, including devices connected after launch.
Keyboard and gamepad controls may be mixed; both map to the same active-low
cabinet input word before the original debounce and game routines consume it.

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
timers and active depth gates, a separate raw/decoded level-flags page, actor
counts and raw MOB words,
thief/dragon AI, display memory, live pursuit/escape routing grids,
audio queues, a rolling event log inferred from snapshots while the panel is
open, synthetic-scenario event queues/timers, and a 120-sample render-time
graph. The displayed `RENDER` value is a rolling average of the latest ten
frames. The graph labels its dynamic Y axis in milliseconds and marks the
16.67 ms frame budget. The AUDIO page shows the twelve most recently accepted
sound commands chronologically, one per line with hexadecimal command number
and the description from the local WAV library (or the known control-command
meaning).
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
Synthetic-scenario dumps additionally embed the complete normalized fixture,
its SHA-256 and source filename, plus event progress, so resume never depends on
the original file remaining present or unchanged.

F5–F10 are host troubleshooting controls, not original cabinet inputs. The
level skip uses the live cabinet maze rotation, enters the normal `LEVEL n`
splash, and respawns the surviving party when its presentation timer expires.
Inventory grants update the selected host
player's game-side counters and alpha-RAM inventory display. F8 gates only
`main_treasure_timer`, so actors, input, combat, and every other frame routine
continue while the room clock is held; it clears automatically when that room
ends. F9 runs the
current maze through the ROM's objective-setup block with the availability
counter open, including the normal solo-party cancellation, so the listed trick
must still be completed before exiting. From level 6 onward, F10 sets the
selected live player as the sole winner and disables further ordinary-objective
selection, but the exit animation and between-level secret-room handoff still
run.

By default the runner drops you straight into a level. Options:

```bash
uv run --all-extras gauntpy-play --sound --level 2 --character elf --scale 3
```

`--level` selects the dungeon level and follows the cabinet's maze rotation
after level 5. `--maze` selects an exact stored maze independently; combine
them when reproducing a layout at a particular difficulty depth:

```bash
uv run --all-extras gauntpy-play --level 115 --maze 3
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

Use the cabinet ROM's **Reduce Text** operator setting from the command line:

```bash
uv run --all-extras gauntpy-play --reduce-text
```

In normal play the ROM selects its alternate short-message bank, where only
the food entry is populated. Most first-encounter messages—including initial
damage, potion use, and destructible walls—therefore produce no speech, box,
chime, or pause. The surviving food box holds for 120 rather than 150 frames.
Negative attract modes retain the full message bank, so the recorded demo keeps
its dialog timing. Speech for retained records remains controlled independently
by the cabinet's Disable Speech setting.

Or boot through the **real front end** — attract → coin → character select →
start — exactly as the cabinet does:

```bash
uv run --all-extras gauntpy-play --attract
```

Press **5** to insert a coin, steer to pick a class, and press **Enter** to
start.

Verify and decode a secret-room contest code from the two fields Atari asked
the player to submit:

```bash
uv run python -m gauntpy.secret_code_verifier "ALINSA" FB9-AD9
```

On Windows, `verify-secret-code.bat` wraps that `uv` invocation.

The title, high-score, legend, and character-select screens render in the
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

For minimized reproductions, load a declarative synthetic maze:

```bash
uv run --all-extras gauntpy-play --scenario scenarios/narrow-lane-thief.gsc
uv run --all-extras gauntpy-scenario run scenarios/narrow-lane-thief.gsc \
  --every 60
```

The `.gsc` format is documented in `scenarios/README.md`: a normal level-flags
longword and other setup fields, an exact 32x32 ASCII grid, optional symbol
bindings, and a small allowlisted event language. These fixtures use normal
game-side state/VRAM writers but are always labeled **synthetic**. They are
reproduction tools, not evidence of ROM behavior.

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
