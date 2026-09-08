# 4. A room full of monsters

Consider a corridor with a generator at its far end. You clear the nearest
monster, then another steps into the gap. Shooting seems to produce movement
rather than progress. The generator is not merely a tough enemy behind the
others: it is the source of replacements, and leaving it intact lets an
initially manageable room become a queue of bodies.

How does the machine keep that queue moving without giving every creature
an elaborate plan?

## Many creatures, small decisions

Most monsters share one movement-and-combat routine. Their type selects
animation and behavior data, while a few state bits distinguish moving,
attacking, and idle phases. On its decision turn a creature can select a
target, choose a direction, and attempt a move. The destination and nearby
bodies determine whether that attempt succeeds.

Ordinary targeting compares the sum of horizontal and vertical distance to
each player; IT biases the choice toward the cursed hero. This is not a
fresh search for the best route through the maze. Local attempts, obstruction,
and repeated decisions account for much of the crowd's behavior. A narrow
entrance makes even numerous monsters approach in a restricted stream.

Nor does every creature reconsider everything on every frame. Idle decisions
are staggered, and the expensive monster work is limited to a window around
the camera. Creatures in view remain individual actors, but individuality
does not require a private strategy.

## Why does a wounded grunt change color?

![One grunt drawn at three strengths with palettes numbered 2, 3, and 4](img/ch11_tier_palettes.png)

*These ROM-derived renderings use the same artwork. The palette changes:
a palette is the color table used to turn the picture's numbered pixels
into visible colors.*

A grunt's strength is stored in the same small field that selects its
palette. Three consecutive values represent its three surviving tiers.
A one-point hit on the strongest grunt lowers that value one step. The
combat routine now sees a weaker creature, and the video hardware sees a
different color table. No separate instruction has to repaint the wound.

Continue subtracting until the value leaves that family's valid three-tier
range and the monster is removed. Other ordinary families use different
palette ranges, so the colors need not mean the same thing across species.
Generators have their own tiered types: a surviving hit can replace a strong
generator with a weaker generator, changing what it subsequently produces.

## When does a generator get another monster?

Within the active window, each generator's turn falls once per sixteen
frames. Which turn depends on its cell number, spreading the attempts instead of making every
generator act together. A turn is an opportunity, not a promise.

The game computes a probability out of thirty-two from the operator's
difficulty setting and the number of active players. At the lowest setting,
the base entries are four for one player and eighteen for four. Those are
chances before adjustments, not permitted population sizes. A signed bonus
modifies the value; except on level one, the result is capped at twice the
level number. Score-and-coin accounting also affects the bonus.

Suppose an adjusted value is eight. A successful comparison with a random
number supplies a one-in-four chance on that generator's turn. It must then
find room: starting in a randomly chosen direction, the routine examines up
to eight neighboring cells for traversable, empty space. Surrounding a
generator can prevent a birth even after the random gate succeeds.

There is one more gate. If the main loop has detected an overlong frame, it
forces this probability to zero. Existing monsters do not disappear, but
generators temporarily stop adding work. The filling corridor is governed
by time, chance, and available floor, not simply by a maximum monster count.

## Similar bodies, different threats

A ghost spends itself on contact: it damages the hero and disappears.
A grunt remains an obstacle to fight. A demon can fire along a compass
direction, subject to an available shared projectile slot and a check of
its immediate muzzle cell. That check does not trace a clear line through
the whole corridor.

The lobber demands a different response. Its rock passes over intervening
walls because collision is deferred until the last part of the rock's
lifetime. Its aim includes a prediction based on the target's class,
speed power, and **movement actually achieved**. A hero holding Right
against a wall contributes no rightward lead. A hero running right does.
Turning the joystick is not itself a feint; changing the resulting movement
changes the prediction.

Sorcerers can move while reusing their idle artwork, and their hidden phase
resists ordinary shots. Super Sorcerers instead have a special relocation
search behind players. Acid creeps on a much slower update cadence and
affects movement on contact. Death ignores ordinary shot damage; a potion
is the direct remedy. IT changes whom the crowd wants.

The room's pressure comes from these differences meeting the same geometry.
A safe choke point against ghosts is not necessarily safe against a
lobber, and concentrating on the nearest bodies leaves their replacement
source untouched.

## For the full chapter

Add a time-strip showing staggered generator turns, failed rolls, blocked
births, and a successful spawn. Trace one grunt through its color tiers and
one lobbed rock through takeoff, predicted landing, and collision activation.
Expand Death's per-player damage accumulator, sorcerer phases, fast-family
cadences, and the score/coin bonus without turning the roster into a catalog.

## Source notes

- [Game subsystems](../doc/04_game_subsystems.md), §§3.1–3.7 and 26:
  shared behavior, spawn gates, target selection, lobber leading, and damage.
  §3.5 identifies the lobber input as achieved movement, not stored facing.
- [Data reference](../doc/05_data_reference.md), §§1.1 and 5:
  `monster_spawn_probability_table` at `0x40E46`, the signed bonus, and
  class-dependent solo-join initialization.
- The [tier illustration](img/ch11_tier_palettes.png)
  is a rendering from the graphics ROMs, not a photograph of a play session.

[Previous: Three friends, one screen](03_four_players.md) |
[Contents](README.md) |
[Next: Painting the dungeon](05_painting_the_dungeon.md)
