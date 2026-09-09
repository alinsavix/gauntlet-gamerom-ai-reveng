# 6. A world in ten bytes

An arrow enters a crowd. The game must find what it hit, reduce that
creature's strength, and perhaps remove it while leaving its neighbors
alone. Drawing a roomful of ghosts is only half the problem. How does the
machine know which ghost is which?

For ordinary maze objects, its answer starts with the floor. The logical
maze is thirty-two cells across. Number each cell by multiplying its row
by thirty-two and adding its column, counting both from zero. Row twelve,
column twenty is therefore cell `12 × 32 + 20 = 404`.

The number is a **packed slot**: its low five bits hold the column and
its next five hold the row. Five bits can represent the thirty-two
possibilities on either axis.

A dynamic object occupying that cell uses object slot 404. The cell does
not contain a pointer to some separately numbered ghost; the cell number
already selects the ghost's record. Asking “what is in this cell?” can
begin with a direct memory lookup rather than a search through every
monster in the room.

That is economical, but it immediately raises another question. If a
ghost's number is where it lives, what happens when it moves?

## Five shelves, one record

An object's record consists of five sixteen-bit **words**, each two bytes.
They are not stored as ten consecutive bytes. Instead, the game has five
parallel arrays: one run of picture words, another of horizontal words,
and so on. Entry 404 on each of those five shelves belongs to slot 404.

```text
                         slot 403       slot 404       slot 405
picture array               ...       [picture]           ...
horizontal array            ...       [X / color]         ...
vertical array              ...       [V / size]          ...
forward-link array          ...       [type / next]       ...
state/back-link array       ...       [state / previous]  ...
```

*A schematic of actual record organization, not a contiguous structure.
Selecting one column gathers the five words of an object.*

Because entries are words, entry 404 is 808 bytes from the start of each
array. Entry 405 is two bytes farther along on every shelf. The same
small offset calculation reaches all the parts of the object.

| Word | Information packed into it |
|---|---|
| Picture | Starting graphics tile; high bit available to software |
| Horizontal | Nine-bit X position; three software flags; four-bit palette |
| Vertical | Nine-bit upward V position; size fields and one spare bit |
| Forward link | Six-bit object type; ten-bit next-slot number |
| State/back-link | Six-bit type-specific state; ten-bit previous-slot number |

The first four arrays are the hardware's motion-object description. The
fifth is software-only. Even inside a hardware word, the display ignores
fields it does not need. Ten bits suffice to link any of 1,024 slots, so
the game can use the remaining six bits of the forward-link word for the
object type.

Those two fields answer different questions. “Which object comes next?”
helps traverse the display chain. “What kind of object is this?” decides
whether touching it means eating food, attacking a monster, or trying to
open a door.

The upper state bits are equally economical. An ordinary monster uses
them for animation and direction. A player body uses them to identify its
player position. A movable wall can use them to accumulate hits. The type
tells the software how to interpret the available state.

Ten bytes is thus the common object representation, not the whole memory
budget of a hero. Health, score, inventory, and timers live in separate
player-indexed storage. A body can move without relocating a player's
entire life in the game.

## A cell is not a pixel

Cell 404 identifies a neighborhood sixteen pixels wide, not one exact
position. The live H and V words say where the object currently lies
within and around that neighborhood.

For an initially cell-aligned object at row 12, column 20, the unadjusted
horizontal coordinate is `20 × 16 = 320` pixels. The vertical coordinate
is `(31 − 12) × 16 = 304` pixels, measured upward from the bottom of the
512-pixel playfield. Its cell's downward-positive top edge is therefore
`496 − 304 = 192`.

The sprite's top edge is a different number. The video system draws
upward from the stored bottom-edge anchor. For a twenty-four-pixel-tall
hero, its top is `512 − 304 − 24 = 184`. The artwork starts eight pixels
above the sixteen-pixel cell.

The constructor also applies a four-pixel horizontal correction for
ordinary three-by-three heroes and monsters. Their initial drawing begins
at X=316, four pixels left of the cell's X=320 edge. A weapon or shoulder
can therefore overhang a neighboring cell while the object still belongs
to slot 404.

Position occupies the upper nine bits of each word. Moving one pixel
changes that field by `0x80`, or 128, because the lower seven bits carry
other information. The horizontal low bits include the palette; the
vertical low bits include dimensions. A movement update must retain them,
or walking could inadvertently recolor or resize the hero.

These are playfield coordinates, not monitor coordinates. Scrolling
changes where the body appears on screen without changing its occupied
slot. Conversely, walking while the camera follows can change the slot
while the hero appears to stay near the center of the display.

## Follow two pixels across the boundary

Let us make the migration concrete using the Blue Elf, whose continuity
we can follow through the separate player reference. The same
cell-ownership principle applies to an ordinary ghost.

This is an illustrative state assembled in the game's actual record
format, not a captured move. Assume clear space, no camera restriction
preventing motion, and a successful two-pixel step to the right. The Elf
has already moved within cell 404: its live drawing X is 322 and its
upward V is still 304.

Blue is player index 1 and uses MOB palette 13. A three-by-three sprite
has size bits `0x12`: two for width-minus-one, two for height-minus-one.
The relevant words are:

| Quantity | Before the step | Proposed after the step |
|---|---|---|
| Drawing X, pixels | 322 | 324 |
| Upward V, pixels | 304 | 304 |
| H word, including palette 13 | `0xA10D` | `0xA20D` |
| V word, including 3×3 size | `0x9812` | `0x9812` |

The change is `0x100`, exactly two pixels in the position field. It leaves
the palette unchanged.

Which cell owns the proposed position? The movement tail does not simply
divide the drawing's top-left corner by sixteen. It uses biased anchors
to account for the sprite's relationship to the grid. Away from seams,
the column calculation is equivalent here to dividing `X + 12` by
sixteen and discarding the fraction.

Before the step, `(322 + 12) / 16` gives column 20. After it,
`(324 + 12) / 16` gives column 21. The upward-coordinate calculation adds
eight pixels, selects and inverts the row bits, and still gives row 12.
Thus the proposed record belongs to `12 × 32 + 21 = 405`.

Notice when ownership changes. The corrected cell anchor has reached
X=328, halfway through the old cell, not its far edge at X=336. Ownership
is a rule for assigning a smoothly moving body to a lookup slot. It is
not a claim that every painted pixel has crossed a square's border.

If the result had remained 404, the tail could write only the H and V
words. In our example it first checks the destination. Slot 405 is empty,
so the accepted position words go into the source record and the Blue
player's current-slot entry changes from 404 to 405. The migration helper
then transfers the body into its new home.

If the destination instead held an item, the player's tile-interaction
path would get a chance to handle it before migration. A rejected
interaction can abandon the move without publishing the proposed
position. A usable destination is a consequence of the interaction rules,
not merely of a floor-colored pixel being visible there.

## Move the links as well as the body

The five words participate in another structure besides occupancy.
Their next and previous fields join rendered objects into one ordered
chain. A link is just a slot number: following it means using that number
to read the next object's fields.

Suppose our illustrative chain has this local fragment:

```text
1. Before migration

   ... <--> 370 <--> 404 <--> 438 <--> ...
                    Elf
   Blue player's current slot = 404
   destination 405 is empty
```

The neighbors in this diagram are neighbors in traversal order, not
necessarily adjoining maze cells. Slot 370 is row 11, column 18; slot 438
is row 13, column 22. Empty cells need no rendered entry between them.

The helper first inserts the destination into the ordering, then copies
the source's picture and accepted H/V words. It transfers the upper type
and state fields while preserving the destination's newly installed
links. In this example, with no intervening records, the structural
intermediate is:

```text
2. Destination inserted, source not yet retired

   ... <--> 370 <--> 404 <--> 405 <--> 438 <--> ...
                    old      new
   Blue player's current slot = 405
```

This is an internal update sequence, not two Elves deliberately presented
as successive gameplay frames. Copying all ten bytes blindly would be
wrong: the old record's neighbor numbers describe the old chain position,
not the newly inserted one.

The helper finishes by unlinking and clearing the source. Slot 370's
forward link now names 405; slot 405's back-link names 370. Slot 438's
back-link already names 405 from insertion.

```text
3. Migration complete

   ... <--> 370 <--> 405 <--> 438 <--> ...
                    Elf
   Blue player's current slot = 405
   all five words at 404 = 0
```

At the end, the destination's picture is the same selected tile T; H is
`0xA20D`; V is `0x9812`. Its forward word combines the unchanged object
type with next-slot 438. Its state/back-link combines player index 1
with previous-slot 370: `(1 << 10) | 370 = 0x0572`.

The next animation update can change T without changing that identity.
The next collision can find the hero through cell 405. The score display
still uses Blue's separate player data. The record has moved; the person
has not become a different player.

## One chain, many places to enter it

A video raster is a sequence of horizontal scanlines. The display can
usefully ask which motion objects matter near the scanlines it is about
to draw, rather than beginning with every possible slot.

Gauntlet II supplies sixty-four **SLIPs**, starting link points, one for
each eight-scanline band of the 512-pixel playfield. Each entry is a slot
number that enters the shared chain. “Band” here means a horizontal strip
selected by vertical position, not a lane in the dungeon.

```text
earlier-band entry ----> 370 <--> 405 <--> 438 <--> ...
                                  ^        ^
another-band entry ---------------'        |
later-band entry --------------------------'
```

*Schematic entry points into the completed example's one chain. Exact
band assignments are omitted; an entry need not identify an object whose
entire drawing fits inside those eight scanlines.*

There are not sixty-four independently owned lists. Several entries may
name the same object, and following a next link continues through the
shared ordering. The entries are cumulative starting positions.
Insertion and removal must maintain them along with the neighboring
links. Where an affected entry named retiring slot 404 in our example,
the removal updates it to the successor, 405; unrelated entries need not
change.

The bands belong to the playfield, not the monitor. Scrolling changes
which bands are visible, not which world strip a stationary monster
occupies. A tall picture can contribute to several strips without being
copied into several independent object records.

The ordering also accommodates reserved effects through explicit
depth-placement keys. Those keys let an object whose slot number says
nothing about its location appear among the appropriate maze objects.
Monster processing uses the chain and its band entry points too.

This explains why “find nearby things” is not one universal operation.
Following the chain is useful for ordered traversal of a region.
Looking up cell 405 directly is useful for asking whether that location
is occupied. Neither is a substitute for the other.

## Why your arrow does not evict the monster

An arrow can enter an occupied cell while the game tests whether it hits
the occupant. If every visible object had to own that cell's only slot,
the arrow would have nowhere to go.

The low-numbered reservations solve that problem. Slot zero is the null
link, and slots 1–29 are assigned to shots and effects. Dynamic maze
records use slots 30–1023. The four player projectiles use slots 1–4;
enemy projectile families use 5–12. Later reservations supply impact
effects, floating scores, exit animations, and transporter animations.

The Blue player's arrow stays in slot 2 throughout its flight. Its live
coordinates change and its depth placement can change, but it does not
migrate through cells 404, 405, and 406. The Blue hero does migrate.
“Fixed slot” fixes an allocation, not a screen position.

There can consequently be an arrow, a ghost, and a fading score picture
over the same stretch of floor without any of them having to overwrite
the others' descriptions. They occupy different roles in the allocation.
The reserved row-zero numbers also mean that the logical map is not an
unrestricted 1,024-cell creature arena; border and placement rules keep
ordinary movement out of the reserved space.

Follow the arrow's collision inquiry rather than its drawing order.
The shot-collision routine probes its candidate cell, then, if needed,
a bounded sequence of neighboring candidates selected through the shot's
direction table. Each probe reads that cell's own record. It rejects
unsuitable candidates and compares live position fields using the shot's
collision limits. It does not walk the SLIP chain searching for a matching
colored pixel.

Once it accepts a target, it passes the target slot to hit resolution.
The upper type bits select the response. For an ordinary monster, damage
changes the palette-related strength field or removes the object. The
arrow's separate reservation can then be cleared or remain live under
the collision's rules. This is the allocation underneath the firing
cycle we followed in Chapter 2.

## A visible shoulder is not a collision boundary

The CPU need not read the ghost's graphics to decide that the arrow hit
it. Collision uses selected candidates, coordinates, object types, and
geometric tests. Transparent pixels and shadow pixels belong to the
picture, not a pixel-by-pixel collision mask.

For a concrete comparison, an ordinary movement-candidate test requires
the corrected anchors to be strictly less than `0x7C0` position units
apart on both axes. That is fifteen and a half pixels. Assuming an
otherwise qualifying blocker, a sixteen-pixel horizontal separation
fails this particular blocking test; a fifteen-pixel separation with the
same vertical anchor passes it.

Two twenty-four-pixel-wide pictures can visibly overlap in either case.
Their art boxes are larger than the separation the test measures. A
shoulder appearing to enter neighboring artwork is therefore not enough
to establish that movement violated the game's geometry. This example
explains a movement gate, not a universal hitbox for every projectile or
special monster.

The distinction goes further than sprite edges. An exit can have picture
word `0x8001` as a software marker and remain outside the rendered MOB
chain. Its floor graphic comes from the playfield; its occupied-cell
record gives interaction code something to recognize. Removing every
unlinked record would remove game information, not merely invisible
clutter.

An invisible wall offers the converse lesson. A rule can leave a wall's
collision marker in place while its playfield descriptors show floor.
The apparently open route remains blocked because the collision inquiry
does not ask the monitor what color it displayed.

The room thus has several overlapping descriptions: cell ownership for
finding occupants, live coordinates for movement, a chain for traversal
and display, and tiles and palettes for appearance. They share compact
records without becoming identical. That is how one arrow can find one
ghost in a crowded picture—and why understanding the fight sometimes
requires looking past the picture itself.

## Source notes

- [Game subsystems](../doc/04_game_subsystems.md), §§1, 2.1, 4.2,
  23, and 24: parallel words, type-dependent state, anchor conversion,
  migration, markers, and the single chain with cumulative entry points.
  The two-pixel move and numbered chain are illustrative, not ROM
  gameplay captures.
- Migration arithmetic and ordering were checked against the ROM at
  `0x424CA–0x42520`, `moblist_insert` at `0x5DCBC`, and
  `move_mob_slot`/clear at `0x5DE0A–0x5DED2`. In particular, migration
  copies upper type/state fields without overwriting new link indices.
  [MOB-list contracts](../doc/generated/mob_list_contracts.csv) locate
  the callable and register-entry boundaries.
- Projectile candidate lookup follows `shot_mob_collision` at `0x40906`
  and `shot_collision_candidate_core` at `0x40A78`, checked against their
  ROM operations and
  [combat contracts](../doc/generated/monster_combat_contracts.csv).
  The ordinary movement threshold is documented separately in subsystem
  §4.2; it is not presented as the shot routine's universal threshold.
- [Hardware reference](../doc/01_hardware.md), §§7–8, covers hardware
  fields and SLIPs. Use subsystem §24's shared-chain account rather than
  reading hardware §8.4's “each band's list” as independent lists.
  No first-forward-element claim is made for the software variable named
  `mob_depth_list_head`; the ROM's endpoint bookkeeping is more specific
  than that name suggests.
- [Data reference](../doc/05_data_reference.md), §§1.7, 3.8, 3.12,
  and 3.14: current player slots, reservations, invisible-wall flags,
  and object types. Hidden route-grid contents are developed with their
  consumers in [The thief's trail](11_the_thiefs_trail.md), rather than
  treated here as another universal occupancy map.

[Previous: Painting the dungeon](05_painting_the_dungeon.md) |
[Contents](README.md) |
[Next: The game's clock](07_the_games_clock.md)
