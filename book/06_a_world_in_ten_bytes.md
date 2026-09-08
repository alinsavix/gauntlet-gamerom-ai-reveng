# 6. A world in ten bytes

An arrow enters a crowd. The game must find what it hit, reduce that
creature's strength, and perhaps remove it while leaving its neighbors
alone. Drawing a roomful of ghosts is only half the problem. How does the
machine know which ghost is which?

For ordinary maze objects, its answer starts with the floor. The logical
maze is thirty-two cells across. Number each cell by multiplying its row
by thirty-two and adding its column. An object occupying row twelve,
column twenty therefore occupies cell 404. Its object slot is also 404.

That equivalence turns a spatial question into a direct lookup. Asking
“what is in this cell?” does not require searching a list of every monster.
The cell number already tells the code where to look.

## Five shelves, one record

A slot selects one entry in each of five parallel arrays. An array is
simply a numbered run of entries; parallel means that entry 404 in every
array belongs to the same slot. Each entry here is a sixteen-bit **word**,
or two bytes. Together the five words occupy ten bytes.

| Word | What it carries |
|---|---|
| Picture | Starting tile number and a software flag |
| Horizontal | Position, palette, and behavior flags |
| Vertical | Position and the sprite's width and height |
| Forward link | Object type and the next slot in drawing order |
| State/back-link | Type-specific state and the previous slot |

The video hardware reads the first four arrays. The fifth is maintained
for the software. Even among the first four, the hardware uses only the
fields it needs. The game keeps an object's type in bits above the forward
link because the display only needs the link itself.

The extra state changes meaning with the type. A monster uses it for
animation and direction; a player record uses it to identify the player
position. Doors and movable walls have other uses. Ten bytes is therefore
the common object record, not the complete memory budget of a hero, who
also needs separate health, score, inventory, and timers.

## What happens when the ghost moves?

The cell number is an address, not a permanent personal identity. While
the ghost moves within its current cell, its live position words change.
When it enters a different cell, the game relocates the record to the
new slot and clears the old one. A ghost moving from cell 404 into the
cell immediately right becomes slot 405.

Players obey the same rule. A separate per-player entry remembers the
hero's current slot, so “Blue Elf” can remain the same player while the
body's slot changes many times. The system preserves personal continuity
where it matters without giving every ordinary monster an independent,
lasting identifier.

Nor is the slot number a sufficient substitute for live coordinates.
The monster can be partway across a cell. Its artwork can extend beyond
that cell: a common twenty-four-pixel creature reaches four pixels left
and eight pixels above the sixteen-pixel cell on which it is initially
anchored. The stored vertical coordinate counts upward from the bottom
of the playfield, while screen rows count downward.

Collision consequently consults the live position words and the relevant
anchor adjustments. The edge of a painted shoulder is neither a cell
boundary nor a complete collision rule. The playfield tiles beneath a
creature describe appearance; they do not replace its occupied-cell record.

## How are those scattered slots drawn in order?

Cell numbers arrange space for lookup, but drawing needs another order.
The forward and backward links thread active MOB records into one ordered
chain. Each link is just another slot number. To remove an object, the
game reconnects its neighbors; to insert one, it repairs those links in
the other direction.

```text
global head --> slot A <--> slot B <--> slot C --> 0
                              ^           ^
vertical-band entry ----------'           |
later band entry -------------------------'
```

*Letters stand for arbitrary slot numbers, not adjacent cells. Each
double arrow combines a forward link and a software back-link. Both
band entries join the same chain; zero marks its end.*

There are sixty-four of these vertical-band entry points, one per eight
playfield scanlines. Atari called them **SLIPs**, starting link points.
They let the display enter the useful part of the chain rather than
beginning with every possible object. Monster processing also uses the
chain and its band entries. Movement probes, by contrast, can read
neighboring cell slots directly.

The low-numbered slots are exceptions to cell ownership. They are reserved
for projectiles and short-lived effects: four player shots, shared enemy
shots, impact sparkles, floating scores, and exit or transporter
animations. Those pictures must sometimes overlap an occupied cell, so
they cannot replace its resident object.

One room therefore has several useful orders at once: cells for finding
occupants, coordinates for motion, and a chain for drawing and traversal.
The economy lies in letting the same compact records participate in all
three rather than maintaining three separate worlds.

## For the full chapter

Animate the 404-to-405 migration in three diagrams, showing the five
words, repaired links, and the player's slot reference in the equivalent
hero example. Add one worked upward-coordinate conversion and show why
a floor marker can exist outside the rendered MOB chain. Introduce the
hidden direction grid only alongside its consumers, especially the thief,
rather than treating all unused-looking memory as a catalog.

## Source notes

- [Game subsystems](../doc/04_game_subsystems.md), §§1, 2.1, 4.2, 23,
  and 24: five-word layout, player record migration, coordinates, and the
  single chain with cumulative band heads.
- [Hardware reference](../doc/01_hardware.md), §§7–8: playfield tiles,
  hardware MOB fields, fixed slots, and the original-hardware SLIP context.
  The software-chain detail is documented more precisely in subsystem §24.
- [Data reference](../doc/05_data_reference.md), §§1 and 3.8:
  per-player references and fixed-object assignments.

[Previous: Painting the dungeon](05_painting_the_dungeon.md) |
[Contents](README.md) |
[Next: The game's clock](07_the_games_clock.md)
