# 9. The next maze

Suppose you return to the same cabinet after someone else has played. The
opening rooms are familiar. You reach level six expecting the next familiar
layout, and instead find a different maze. The ROM has not changed,
and the game has not rolled a die to choose that room. Another party has
changed where the machine remembers being.

The explanation begins with a distinction that the screen need not teach
you: a **level** measures progress through a game; a **maze** is a stored
layout. Level six is not the name of one permanent map.

## Five familiar rooms, then the game's memory

Ordinary progression through the first five levels uses maze records zero
through four in order. After that, the game enters a rotation through records
5–101. Two pieces of persistent game state control it: a resume position and a
stride, meaning the extra number of records to advance beyond the usual one.
Both belong to the EEPROM-backed settings.

On a fresh configuration the resume position is maze 5 and the stride is
zero. Leaving the fifth opening maze selects that resume position. Finishing
a selection on maze 5 also advances the stride, so the following selections
can move two records at a time: 7, 9, 11. Eventually the selection wraps
beyond 101. A final landing on 5 advances the stride again, cycling through
extra-step values zero to seven.

The resume position does not follow every successful exit. When the last
player dies at level six or beyond, the game records the maze where that
party finished, restoring the queued ordinary maze first if necessary after
a treasure detour. The game's persistence machinery saves that state.
A later game repeats the five opening records, then resumes there.

For a simple illustration, take a saved resume position of 37 and stride
one. The next party's level six uses maze 37; ordinary progression then
selects 39 and 41. The displayed levels still advance seven, eight, and
onward. The arithmetic is deterministic, but knowing only the level number
is not enough to predict it. Level one's `EXIT TO 6` offers a shortcut to
the saved resume position without walking through the remaining opening
rooms.

## A small record can describe a large room

The ROM contains 117 live maze records altogether. Besides the five opening
and 97 rotation mazes, it holds one demo layout, one layout used behind
legend and score screens, eleven treasure rooms, and two secret-room
layouts. Those special uses account for the rest.

A record begins with eleven bytes describing its objective, rule flags,
art, colors, and reusable horizontal or vertical patterns. Its remaining
bytes are instructions for filling a 32-by-32 grid. Repeated walls and
empty corridors compress well because the decoder can say “do that again”
instead of naming every cell.

Consider the beginning of maze zero's actual stream. The numbers below are
hexadecimal bytes, not coordinates:

| Byte | Result |
|------|--------|
| `35` | Place a key and remember that object type. |
| `80` | Repeat the remembered type once: another key. |
| `47` | Use the first horizontal pattern: eight floor cells, then treasure. |

Three bytes advance through eleven cells. The meaning of `47` comes partly
from the header's reusable pattern, so it need not mean treasure in another
record. Vertical patterns can write upward from the current position,
adding a column while the main reading cursor continues across the grid.
Decoding begins on the second row; setup supplies the solid top boundary.

![Maze zero rendered from its stored layout](img/ch09_maze0.png)

This is a description of logical contents, not a saved screenshot. Later
work connects wall artwork, finds transporters and exits, places the party,
and applies live rules.

## The lock on the maze data

Those records occupy 32 KB, but the processor sees them through an 8 KB
window. Atari's Slapstic protection chip determines which of four banks
appears there. It changes banks in response to particular sequences of
memory accesses. The game's lookup uses a pointer table and packed bank
numbers, performs the required access sequence, then reads the chosen
record.

The Slapstic therefore controls access to a maze's bytes, not which maze the
party deserves next. Selection has already answered that question.

Nor does selecting the same record guarantee identical play. Setup can
mirror it, add depth-dependent rules, and adjust pickups. A dragon encoded
in a layout is suppressed before level twelve. The same corridors encountered
later can support a different fight. Persistent selection, stored layout,
and live setup are three separate causes of variation—and only some of
them use the random-number generator.

### For the full chapter

- Trace two complete sessions against one resume/stride diagram, including
  game over, catalog wrap, and the `EXIT TO 6` bypass.
- Extend the three-byte example to maze zero's first decoded row and one
  upward-written span.
- Pair one stored maze with two level configurations; distinguish changed
  geometry, changed rules, and changed pickups.

### Source notes

- [Maze catalog](../doc/06_maze_catalog.md), §§1–3 and 8: all 117 records,
  persistent selection, record format, and decoder boundaries. Relevant ROM
  entries include `player_exit_sequence` (`0x52B40`) and `maze_checknum`
  (`0x52ECA`).
- [Game subsystems](../doc/04_game_subsystems.md), §5: maze decoding
  (`0x4C1BC`), setup, level gates, and Slapstic access.
- [Hardware reference](../doc/01_hardware.md), §11: the protected bank
  window. The readable [decoder implementation](../python-gex/src/gex/mazedecode.py)
  illustrates the documented bytecode; it is not an independent ROM source.

[Previous: What a quarter buys](08_what_a_quarter_buys.md) |
[Contents](README.md) |
[Next: The living maze](10_the_living_maze.md)
