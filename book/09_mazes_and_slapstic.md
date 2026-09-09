# 9. The next maze

Suppose you return to the same game after someone else has played. The
opening rooms are familiar. You reach level six expecting the next familiar
layout, and instead find a different maze. The ROM has not changed, and the
game has not rolled a die to choose that room. Another party has changed
where the game remembers being.

The explanation begins with a distinction that the screen need not teach
you: a **level** measures progress through a session; a **maze** is a stored
layout. Level six is not the name of one permanent map. Knowing the level
number tells us something about the rules that will apply, but not enough
to draw the corridors.

There are three questions to follow. Which record comes next? How do its
bytes describe a place? What happens to that description before anybody
starts walking?

## Two parties, one remembered position

Ordinary progression through the first five levels uses maze records zero
through four in order. After that, the game enters a rotation through
records 5–101. Two EEPROM-backed words control this journey. The **resume
position** says where a new party enters the rotation. The **stride** is
the extra number of records to advance beyond the usual one.

A stride of one therefore means a two-record step, not a one-record step.
The stride ranges from zero through seven, giving effective steps of one
through eight. Neither value belongs to a particular hero. They describe
the shared game's progress across sessions.

Here is an illustrative pair of sessions, using the ROM's selection
arithmetic rather than an observed play recording. Begin with resume
position 98 and stride one:

| Session A reaches | Stored maze | Stride after selection |
|-------------------|-------------|------------------------|
| Level 1 | 0 | 1 |
| Levels 2–5 | 1, 2, 3, 4 | 1 |
| Level 6 | 98 | 1 |
| Level 7 | 100 | 1 |
| Level 8 | 5 | 2 |
| Level 9 | 8 | 2 |

The opening levels ignore the stride. Leaving maze 4 produces candidate
5, and the selection routine substitutes the saved resume position:
98. The following ordinary exit advances twice, through 99 to 100.

Leaving 100 takes two more steps. The first reaches 101. The second would
reach 102, outside the ordinary rotation, so it wraps to 5. The selection
has finished on 5, which increases the stride to two. The next exit takes
three steps, through 6 and 7 to maze 8.

Suppose the last surviving player now dies and the party does not
continue. The player-removal path records maze 8 as the resume position.
This write occurs when the active-player count reaches zero, and only
from level six onward. Earlier successful exits did not keep advancing
the resume word behind the scenes.

```text
Before A:       resume 98, stride 1
A's journey:    opening five -> 98 -> 100 -> 5 -> 8 -> last death
After A:        resume  8, stride 2

B's journey:    maze 0 -> EXIT TO 6 -> 8 -> 11 -> 14 -> last death
After B:        resume 14, stride 2
```

*Illustrative ordinary-maze progression. Treasure detours, if scheduled,
temporarily interrupt this line without replacing its queued destination.*

Session B starts with maze 0 again. This party takes its `EXIT TO 6`,
bypassing the other four opening levels. The shortcut explicitly sets
the next level to six and asks the same validator about candidate maze
5. The saved resume position turns that into maze 8.

Crucially, the shortcut neither uses nor increases the stride. Session B
inherits stride two, then advances to 11 and 14 on its ordinary exits.
If everybody dies at 14, that becomes the next party's entry point.
The two parties have both visited level six, but one saw maze 98 and the
other maze 8.

Maze 0 is the only stored layout containing an `EXIT TO 6`; it also has
an ordinary exit. Choosing between them is choosing between the opening
sequence and the remembered rotation, not between two routes to the same
next room.

## A wrap is not always a new stride

There is a small but important ordering detail in the validator. Its
“candidate 5 means resume” substitution happens on entry. A later wrap
sets the candidate to 5 *inside* its validation loop, past that
substitution. Otherwise a lap could bounce straight back to the resume
position instead of reaching the beginning of the rotation.

And the stride changes only after the complete step sequence, if its
final destination is 5. With stride one, leaving 101 goes through
wrapped maze 5 and then finishes on 6. That crosses the boundary without
increasing the stride. Leaving 100, as Session A did, finishes exactly
on 5 and does increase it.

On a fresh configuration the resume position is 5 and the stride is
zero. Ordinary play therefore begins 0, 1, 2, 3, 4, 5. That first landing
on 5 increases the stride to one, producing 7, 9, 11 afterward.
Taking the opening shortcut instead reaches 5 without that increase:
the next ordinary exit can reach 6. Even the familiar fresh-game
sequence needs its route specified.

The displayed level counter has a separate wrap. An ordinary advance
beyond 999 subtracts 994, returning the display to level six. It does
not thereby reset the maze rotation. The two counters answer different
questions all the way through the game.

Persistence is also distinct from an immediate physical write. The game
maintains the values in RAM and its EEPROM service saves changed state;
a catalog wrap requests an early save. Recording a party's last maze
does not mean that every exit writes the EEPROM. We will return to the
storage machinery when the game boots in Chapter 16.

## The detours have their own itinerary

The ROM holds 117 live maze records, divided this way:

| Records | Use |
|---------|-----|
| 0–4 | Five opening layouts |
| 5–101 | Ninety-seven ordinary rotation layouts |
| 102–103 | Demo, then legend/high-score background |
| 104–114 | Eleven treasure rooms |
| 115–116 | Two secret challenge layouts |

Treasure rooms use another persistent position and another stride. Their
effective step is one through four, wrapping within the eleven-room
range. This is separate from the countdown deciding *when* a treasure
room interrupts ordinary play.

At level six the game seeds that countdown with a random three, four,
or five. Later ordinary-level transitions spend it, and a treasure
visit reloads it with another such draw. The room to use, however,
comes from the treasure rotation. Random timing and persistent room
selection are different operations.

While the detour runs, the queued ordinary maze remains available.
Even if everybody dies in the treasure room, the last-player path
restores that queued maze before recording the ordinary resume
position. A future party will not enter the treasure catalog merely
because the previous party died there.

## Getting the bytes through the Slapstic

Once selection has produced a maze number, the processor still needs its
data. The maze ROM contains 32 KB arranged in four 8 KB banks. The
processor reads the selected bank through the same address window,
`0x38000–0x39FFF`. Changing banks changes what those addresses contain.

Atari's Slapstic protection chip controls that selection by watching
sequences of memory accesses. This is more elaborate than storing a bank
number into an ordinary register. The accesses themselves participate
in the command.

Two short helpers show the idea concretely. One temporarily masks
interrupts, writes at `0x38000`, then writes at `0x38010` to select
bank zero. Another uses `0x38000` followed by `0x3801C` to select bank
three. These are not attempts to rewrite the maze ROM. The protection
hardware observes the address sequence; the processor then reads ROM
through the resulting bank mapping.

The lookup first selects bank three to read a packed bank table. Each
byte holds four two-bit bank numbers. It selects bank zero to consult
the maze-pointer table, then the appropriate selection path makes the
record's bank available. Level setup also uses the Slapstic's bitwise
command path, whose table-selected accesses precede a latch access at
`0x3FB60`.

The distinction matters when explaining the apparent surprise at level
six. The Slapstic makes access conditional on the right protocol; it
does not decide where the party should go. The persistent selection
arithmetic has already answered that question.

Nor does bank switching generate a maze. Beyond the window waits a
particular compressed record, beginning with eleven bytes of settings
and followed by instructions for building the grid.

## Read the first row before drawing it

Maze zero gives us a small example directly from the ROM. Its record
starts at offset `0x01E0` in the maze image. The header selects the
visual patterns, colors, flags, and four reusable compression contexts.
For this record, horizontal context one is `6E`: skip a run of floor,
then place treasure. Vertical context one is `0E`: repeat vertical
doors upward.

The decoder uses a 32-by-32 grid, numbering both rows and columns from
zero. Its main cursor starts at slot 32, row 1, column 0. Row zero
is supplied separately as a solid top boundary after decompression.

These are the first eight actual stream bytes. Hexadecimal names the
bytes; columns and counts below are decimal:

| Byte | Action on row 1 | Next column |
|------|-----------------|-------------|
| `35` | Key at column 0; remember the key type | 1 |
| `80` | Repeat that type once, at column 1 | 2 |
| `47` | Eight floor positions, then treasure at 10 | 11 |
| `C4` | Skip five floor positions | 16 |
| `31` | Food at 16 | 17 |
| `42` | Three floor positions, then treasure at 20 | 21 |
| `C9` | Skip ten floor positions | 31 |
| `35` | Key at 31 | Next row |

Eight bytes have advanced across all thirty-two columns. The counts
add up: `1 + 1 + 9 + 5 + 1 + 4 + 10 + 1 = 32`.
The floor spans do not require thirty-two individual “empty” objects.
They move the cursor through already clear space.

Why does `47` mean eight floor positions and treasure? Its low nibble
is seven, giving a count of eight. Its context selector chooses the
header's `6E`; that context supplies the “floor then object” mode and
the treasure type. `42` uses the same context with count three.
The byte's meaning is shared between the instruction and its header.

Next comes `6F`. It selects horizontal context two, `54`, whose mode
is again floor followed by an object, this time a demon. The count is
sixteen, so the stream skips row 2's first sixteen positions and places
a demon at column 16. The same little grammar has described supplies
and an enemy without needing a separate compression scheme for each.

There is a catch: finishing a row does not make that row final.

## A column can arrive from below

Farther into this same record, byte `58` is encountered with the main
cursor at slot 295: row 9, column 7. The low nibble gives nine
placements. Vertical context one supplies the vertical-door type.

```text
Main cursor before: 295 = 9 × 32 + 7

Written slots: 295, 263, 231, 199, 167, 135, 103, 71, 39
Written rows:    9,   8,   7,   6,   5,   4,   3,  2,  1
Column:         7 throughout

Main cursor after: 296 = row 9, column 8
```

This is an upward-writing operation, not nine forward steps through
the stream's output. Each placement subtracts 32 from the temporary
writing position, while the main cursor advances just one cell.
The door at row 1, column 7 arrives long after our first-row table.

A following `59` at row 10, column 24 similarly writes ten doors
upward, reaching row 1. Later still, `BF` writes sixteen wall cells
up from row 16, column 0, replacing the key provisionally placed at
row 1, column 0.

The completed first row therefore contains a wall at column 0, keys
at 1 and 31, doors at 7 and 24, treasure at 10 and 20, and food at
16. Its other positions are floor. This distinction between *cursor
progress* and *finished contents* is essential to reading the format.
Copying our first eight instructions straight into a final picture
would put a key where the full record eventually requires a wall.

![Maze zero reconstructed from its stored layout](img/ch09_maze0.png)

*ROM-derived layout rendering, not an original-game screenshot. The
completed vertical door runs and later wall writes are included; the
start-position cross is a layout annotation, not a hero.*

The decoder stops when its main cursor reaches 1024, not when it finds
a special end instruction. Most stored records have a trailing zero
delimiter useful to offline tools, but the game does not need to read
it. A byte can be meaningful data or an unused file delimiter depending
on whether the output cursor has already finished its work.

## Turning the record into this visit

Decompression supplies logical objects, not a photograph of a running
level. Placement turns ordinary creatures and items into live motion
objects. Walls and special floors use markers that later select
playfield artwork. Doors need their neighboring geometry classified;
a dragon needs several cells rather than one.

Setup can also mirror the coordinates. The two mirror bits are
randomly modified during normal level configuration. A vertical door
run remains a connected run after reflection, but its relation to the
entry point and to other passages changes. The next chapter follows
an especially consequential case: reflecting a door spiral does not
reflect the opening routine's fixed turning rule.

Other differences leave the layout's coordinates alone. Consider the
same stored maze 13 configured at level six and at level twelve.
This is a controlled comparison of documented setup paths, not two
recorded visits. The record contains one dragon and seven authored
food objects, five of one food type and two of the other.

At level six, normal placement suppresses the authored dragon.
At level twelve, that dragon survives the level gate. Above level
six, setup also chooses one eligible authored food and changes it to
adaptive food. The record has not acquired a new dragon byte or had
its food table rewritten: different consumers have treated the same
data differently.

For comparison, hold the mirror orientation equal. The corridors can
then be familiar while the fight and one food's value differ.
Allow the mirror draw to differ and the geometry changes too.
Random pickup adjustment comes later again, using party composition,
difficulty, and accumulated game state as well as the maze's base
food count. “The same maze” promises none of those inputs are equal.

At greater depths, level-dependent flag rules can add further
conditions. For example, at level 104 an ordinary rotation maze
gains both wrap axes unless its local-trap flag prevents that
addition. This is a rule applied to the visit,
not an instruction hidden in every corridor cell.

## Arriving is a sequence

The new-level path puts these operations in a useful order. It resets
per-level visitor state, selects the data bank, and builds the maze.
It then scans authored player-start markers, chooses a start, and
centers the view there. A start marker is a setup instruction; the
chosen one becomes floor rather than remaining an obstacle under a
hero. The scan processes the unused markers too: normally they become
floor, while the fake-exit flag selects a marker-bit path instead.
The saved start position remains useful after its original marker has
gone. Later arrivals find room near the party rather than consuming
another authored start.

Another scan collects transporter and exit positions and establishes
the random-wall scan bounds. Exit-selection rules can choose among
those recorded positions. Trap setup can rotate trigger identities
or remove selected wall families. Thus a transporter does not have
to rediscover all its possible pads every time someone touches it:
the level has already prepared a table.

The party is placed before the final random-pickup pass. That pass can
add or remove food, supply a due hidden potion, and restore loot carried
away by a thief or mugger. The level presentation tells players about
applicable special conditions. Only after this preparation does the
ordinary frame loop inherit the new world.

We have followed a level number into a persistent selection, through a
protected ROM window, into compressed rows and upward-written columns,
and finally through live setup. Each stage explains a different kind
of familiarity or surprise. The next room is neither a fixed function
of its displayed number nor a newly invented random labyrinth.

And entering it does not freeze it. The tables are ready, the doors
have their geometry, and the walls have their assignments. As soon as
somebody moves, those preparations become rules for changing the route.

### Source notes

- [Maze catalog](../doc/06_maze_catalog.md), §§1–3 and 8: record ranges,
  selection, persistence, treasure scheduling, and record structure.
  Selection arithmetic follows `player_exit_sequence`
  (`0x52DB2–0x52E56`) and `maze_checknum` (`0x52ECA`).
- Maze-zero bytes were checked in `row10.bin` at `0x01E0`; the first-row
  tokens occupy record offsets `0x0B–0x12`, the upward door instructions
  `0x2B` and `0x32`, and the wall instruction `0x54`.
  Maze 13 occupies offsets `0x0B48–0x0C9F`.
- [Game subsystems](../doc/04_game_subsystems.md), §5, and
  [data reference](../doc/05_data_reference.md), §§3.19–3.20:
  decoder and setup contracts. Byte meanings and upward writes were
  checked against `maze_decode` (`0x4C1BC`) and `maze_tile_write_at`
  (`0x4631C`); the readable
  [offline decoder](../python-gex/src/gex/mazedecode.py) supplied a
  cross-check of completed contents, not independent historical evidence.
- [Hardware reference](../doc/01_hardware.md), §11; ROM helpers
  `0x56E58`/`0x56E6E`, lookup `0x40C78`, and bitwise selection
  `0x43826`: the actual access sequences and bank window.

[Previous: What a quarter buys](08_what_a_quarter_buys.md) |
[Contents](README.md) |
[Next: The living maze](10_the_living_maze.md)
