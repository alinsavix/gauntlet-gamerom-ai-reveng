# 17. Gauntlet in Python

A description of the thief's route is useful. Watching its route grid
while the thief moves is useful in a different way. `gauntpy` gives this
book a playable companion: a Python reconstruction of the game's logic
with controls for looking behind the screen.

It is not an emulator. It does not execute the 68010 instruction stream
or reproduce the board's electrical timing. Instead, it implements the
documented operations in Python, retaining the main-loop order, packed
object fields, tables, and state transitions. Its window is a way to
explore that model, not an independent demonstration that the original
game behaves identically.

## How do I start?

You need Python 3.12 or newer, `uv`, this repository including its local
`python-gex` sibling package, and your own matching ROM files. Neither
the ROMs nor the optional ROM-derived sound recordings are distributed
here. The root [ROM appendix](../README.md#appendix-roms) describes the
program and level images; the [gex ROM list](../python-gex/README.md#tested-roms)
also covers the graphics assets needed by the windowed runner.

From the repository root in PowerShell:

```powershell
Test-Path .\python-gex\pyproject.toml
Set-Location .\gauntpy
uv run --all-extras gauntpy-play
```

The first command should return `True`. `uv` resolves gex from that local
checkout and installs the optional rendering dependencies, Pillow and
pygame-ce. Keep the ROM files in the repository's `ROMs` directory, or
set `$env:GEX_ROM_DIR` to their directory before launching. There is no
need to activate a virtual environment manually.

The default starts direct play as an Elf, with a four-times enlarged
display. Arrows move, Ctrl or Space fires, and Alt or Enter uses Magic.
Press `5` for a coin and `P` to pause. A connected gamepad can provide
the same movement, Fire, and Magic inputs.

To begin with the attract screens instead, run
`uv run --all-extras gauntpy-play --attract`. Insert a coin with `5`,
choose a class with the arrows, and commit with Enter. This follows
the modeled game's front end rather than dropping directly into a maze.

## What is worth changing first?

Layout and progression are separate choices:

```powershell
uv run --all-extras gauntpy-play --level 115 --maze 3 --character elf --full-playfield
```

Here `--maze 3` chooses stored layout 3, while `--level 115` supplies the
depth used by level-dependent rules. Without an explicit maze, level
selection follows the game's maze rotation. This is a useful way to ask
what depth changes while keeping recognizable geography.

`--full-playfield` shows the entire 512-by-512 world beside the gameplay
status panel. A white outline marks the ordinary camera window, splitting
at wrap seams when necessary. It does not move that camera or relax the
game's movement rules. Screen-wide text overlays are omitted in this
view, so use the normal view for title screens and captions. Full-playfield
mode defaults to native scale; `--scale 2` enlarges it.

For a focused encounter, `--keys 3`, `--potions 2`, or repeated
`--power` options seed direct-play inventory and powers. For example,
`--power reflective-shots` lets you examine a rebound without first
finding the item. These are host setup choices and cannot accompany
`--attract`. The optional `--reduce-text` setting is different: it selects
the ROM's shorter advice path during normal play, while the attract demo
retains its message timing.

The default random seed is zero. Use `--seed 1234` for another repeatable
starting stream or `--seed random` for a host-random initial value.
Matching a seed alone does not match a run: starting state and subsequent
inputs matter too.

## What is happening inside this frame?

Press **F1** to open diagnostics and **F2/F3** to change pages. Begin
with mode, level, maze, and camera: these explain where the model thinks
it is. The player pages expose health, inventory, and raw inputs; timer
and level-flag pages help distinguish a dormant rule from one currently
enabled.

For a moving actor, select an occupied MOB with `[` or `]`. Its raw words
connect the visible sprite to [the five-array record](06_a_world_in_ten_bytes.md).
The routing pages show pursuit and escape grids; thief and dragon pages
expose their specialized state. The audio page names recently accepted
commands even when playback is disabled. The event log is inferred from
successive snapshots while the panel is open, not a recording of every
instruction executed.

These pages read an immutable post-frame snapshot outside modeled game
and video RAM. F5–F11 are different: they are deliberate host interventions,
including a level skip, inventory grants, room-timer control, and secret-room
helpers. Keep that distinction in mind when describing what a run shows.

Press **F11** to try the current level again from its captured starting state.
The same pickups, players, timers, video memory, and random stream return; the
host does not generate another maze. The checkpoint is replaced whenever a new
playable level finishes setup, including bonus rooms. It is unavailable during
attract or new-level splashes, and after loading a saved state until the
next new level. A mid-level capture cannot tell us how that level began.
Rewinding preserves `P` pause but clears F8's timer hold and diagnostic history,
stops current audio, and isolates subsequent EEPROM writes from the local file.

Press **F4** to save the complete modeled state. The terminal prints the
JSON filename under `traces\state-dumps`. In the following command, replace
the example filename with that printed name:

```powershell
uv run --all-extras gauntpy-play --load-state .\traces\state-dumps\your-capture.json
```

Loading resumes without booting or rebuilding the level. The snapshot
includes object arrays, players, video memory, timers, inputs, and RNG
state. It is not a physical-machine save state or a recording of future
input. Do not combine it with fresh-start options such as `--maze` or
`--seed`. Resumed sessions suppress external EEPROM writes, leaving
newer persistent settings alone.

## Where do the pieces live?

`GameState` in `state.py` holds modeled working state. `mob.py` preserves
five parallel lists of native-format words rather than replacing the
dungeon with an unrelated object hierarchy. Python integers are not
automatically 16-bit registers, so the logic explicitly preserves
observable masks and wraparound.

`mainloop.py` calls the subsystems in order; `tick` advances a modeled
frame without imposing wall-clock pacing. Game-side presentation routines
write modeled display memory. The renderer reads that memory with
ROM-derived assets to produce pixels. `host\shell.py` supplies the
window, input sampling, pacing, and diagnostic interface. Reading those
three boundaries—game, renderer, host—makes the project much easier to
navigate.

ROM acquisition lives in `maze_rom.py`; game-side maze setup still owns
placement and random choices. The EEPROM model likewise talks to a device
interface, while the host chooses file-backed or isolated storage. A resumed
snapshot restores its captured device image without reopening the current
save file. Protecting that file does not freeze the game's EEPROM timer.

With `--sound`, the host maps accepted commands to local
`sounds\0xNN_description.wav` files, or a library selected by
`GAUNTPY_SOUND_DIR`. It applies queue, priority, loop, and fade behavior,
but does not emulate the 6502 or synthesize the sound chips. A mixed
recording cannot separate individual instrumental parts when only some
hardware channels are suppressed. Muting playback leaves modeled
command production intact.

Finally, `uv run --all-extras gauntpy-play --benchmark 600 --workload benchmark-mobs`
measures the Python host, not the arcade CPU's budget. It separates input,
game update, raster composition through window blitting, and display
flip, alongside the cumulative host loop. Sound, the limiter, and external
EEPROM writes are disabled. Use it to compare host costs, not to infer
how many original CPU cycles a monster consumed.

### For the full chapter

Add a guided thief inspection from launch through F4 capture and resume,
with screenshots of two diagnostic pages. Introduce synthetic scenarios
only after that ordinary-maze workflow.

### Source notes

- Setup, controls, snapshots, audio, and workload details:
  [gauntpy README](../gauntpy/README.md) and
  [current command parser](../gauntpy/src/gauntpy/host/application.py).
- Architecture: [state](../gauntpy/src/gauntpy/state.py),
  [MOB tables](../gauntpy/src/gauntpy/mob.py),
  [main loop](../gauntpy/src/gauntpy/mainloop.py),
  [compositor](../gauntpy/src/gauntpy/render/compositor.py), and
  [host](../gauntpy/src/gauntpy/host/shell.py).

[Previous: Waking the cabinet](16_waking_the_cabinet.md) |
[Contents](README.md) |
[Next: Reading the ROMs](18_reading_the_roms.md)
