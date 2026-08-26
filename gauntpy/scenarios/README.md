# Synthetic scenario fixtures

These `.gsc` files are deterministic **synthetic test fixtures**. They are not
decoded ROM mazes, MAME captures, or evidence of original Gauntlet II behavior.
A result found only here may motivate a ROM/MAME investigation, but must not be
recorded as a fidelity fact until stronger evidence confirms it.

Run a fixture headlessly:

```text
gauntpy-scenario run scenarios/narrow-lane-thief.gsc --every 60
```

Play it interactively:

```text
gauntpy-play --scenario scenarios/narrow-lane-thief.gsc
```

## Format

The header is `key = value`, followed by optional `[legend]` and `[events]`
sections and one required `[maze]` section. The maze is exactly 32 rows of 32
characters. Row zero must be all `#`, preserving the game's reserved top
boundary. `.` and space are floor.

The grid is the pre-placement decoder view. Level mirror bits in `flags` are
applied by the normal placement path, just as they are for a ROM maze. Timed
event row/column arguments name the resulting live packed-maze coordinates.

```text
format = gauntpy-synthetic-maze-v1
name = example
description = Short purpose of the fixture.
frames = 1200
level = 16
maze_number = 15
flags = 0x05028064
seed = 0
character = elf
health = 5000
wallpattern = 0
wallcolor = 0
floorpattern = 0
floorcolor = 0
input = live

[legend]
x = MONST_SUPERSORC

[events]
300 input right
600 input live
1200 activate_thief 1 28 mugger

[maze]
################################
...exactly 30 more 32-character rows...
################################
```

`input` accepts `live`, `idle`, the four cardinal directions, and hyphenated
diagonals. It defaults to `live`, which leaves player-one input under the
interactive host; use `idle` for an explicitly scripted stationary player.
Input events persist until another input event changes them.

`activate_thief row column [thief|mugger]` deploys the selected visitor from an
empty live packed-maze cell through the normal game-side thief deployment
routine. Event frames are absolute 16-bit `GameState.frame_counter` values
(`0`–`65535`), so pending and fired events survive an F4 dump/resume.

Default symbols:

| Symbol | Object |
|---|---|
| `.` / space | floor |
| `#` | regular wall |
| `m`, `s`, `w`, `?` | movable, secret, destructible, random wall |
| `@`, `E` | player start, exit |
| `G`, `g`, `d`, `l`, `z`, `a` | Ghost, Grunt, Demon, Lobber, Sorcerer, Acid |
| `T`, `C`, `f`, `p`, `k` | treasure, locked treasure, food, potion, key |
| `O`, `F` | transporter, forcefield hub |

The `[legend]` section can bind any other single character to a `MazeObjIds`
name or numeric object ID.

State dumps embed the normalized complete file, SHA-256, source filename,
current scripted input, and fired-event indices. They never depend on the
original `.gsc` file still existing or remaining unchanged.
