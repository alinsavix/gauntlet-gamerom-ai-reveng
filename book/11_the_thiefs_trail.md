# 11. The thief's trail

The warning arrives after the important decision. Before a thief appears,
the game has already selected a victim, remembered where that player stood,
and begun recording where they went next. The little figure entering behind
the party is not surveying the dungeon and deciding which route looks best.
It is reading a route that a player has been writing.

This explains an otherwise curious combination: the thief can follow a
complicated journey, yet its movement is not a general-purpose maze solver.
Most of its apparent knowledge belongs to the trail.

## Who is worth robbing?

“Richest” does not mean highest score. The target calculation values carried
advantages. Extra shot power contributes 1,000; speed contributes 700;
shot speed 500; magic power 300; armor 200; fight power 100. Potions,
keys, and multiplier steps contribute much smaller amounts.

Imagine one hero with a large score but almost empty pockets, and another
with extra shot power and two keys. The second can be the chosen victim
despite having fewer points. Health and character class do not enter this
wealth comparison.

The visit itself is conditional. Levels six and seven have no successful
scheduling roll; levels eight through fifteen have a one-in-eight chance,
and the chance rises in steps until it is certain from level sixty-four.
Treasure rooms qualify, while secret challenge rooms do not.

After choosing the victim, the game computes a delay using a different
measure: their scaled score per coin, together with level depth and a random
component. This is not the inventory wealth calculation repeated. It tends
to make efficient play and deeper levels bring earlier visits; treasure
rooms have a tighter delay. Selection and arrival are separate events,
which gives the route time to grow before anything visibly pursues it.

## You write the pursuit; the thief writes the escape

Suppose the selected player leaves cell A for B, then turns into C. Each
departure records a direction toward the next cell. The thief eventually
appears at the saved starting cell A, pauses for its entrance animation,
then reads that trail: toward B, then toward C.

Each route byte has room for two direction codes. The victim writes the
first. As the thief reaches cells during pursuit, it writes the reverse
direction into the second where one has not already been recorded. At B,
that reverse instruction points back toward A. At C, it points toward B.
The escape route is being built by the pursuer's actual travel, not
calculated from scratch after the theft.

Transporters extend this arrangement with pad links and step-off information.
When the victim uses one, the route learns the discontinuity. The thief can
follow it and retain the reverse connection needed to leave again. Pursuit
and escape therefore need not be continuous walks through neighboring cells.

This machinery remembers local directions, not a complete chronological
record of every visit. Nor does it launch an emergency search when a trail
entry is absent: the route reader retains its previous direction. Scheduling
the visitor behind a tracked player is what normally supplies useful
instructions.

The route is not its only behavior. An ordinary monster in the way can delay
it through a short fighting animation and then be removed. An aligned
shooter facing against its direction can trigger a dodge. That check reads
player and shot alignment; it is not an ability to predict every future
projectile. A straight corridor shot is nevertheless less automatic than
the thief's small size might suggest.

## What leaves with it—and what comes back

On contact, the thief takes the most valuable permanent upgrade the victim
owns. Without one, it compares weighted potions, keys, and multiplier and
takes the winning category. Only when it steals the multiplier does it reset
that value to one. The loss then affects later scoring as well as the
immediate encounter.

Kill the thief before it gets away and it drops its carried loot where it
dies, with a base 500-point kill award passed through the killer's
multiplier. Let it complete the escape and the stolen item is remembered
for placement on the next eligible level. Its return is a new floor pickup,
not an invisible restoration to the victim's inventory. Someone still has
to find it.

![The thief and mugger variants](img/ch12_thief_mugger.png)

The mugger follows the same route machinery but moves more slowly and takes
100 health rather than an inventory item. It carries food as the recoverable
loot. The distinction turns recovery into another shared-resource question:
the injured hero needs that meal, but the floor pickup does not belong to
them merely because the injury did.

Successful thefts are limited by variant: one thief and one mugger can each
complete a theft on a level. Deployments are not capped at two. Killing a
visitor before it steals leaves that variant's allowance unused, so another
visit can be scheduled. Winning the encounter does not necessarily finish
the level's argument with the thief.

### For the full chapter

- Animate a short A–B–C pursuit with separate player-written and
  thief-written arrows, then extend it through a transporter.
- Work one target comparison and one correctly scaled arrival-delay example.
- Follow stolen upgrade, multiplier, and mugger food through immediate
  recovery versus next-level placement.

### Source notes

- [Game subsystems](../doc/04_game_subsystems.md), §9: targeting
  (`0x4DFF6`), scheduling (`0x4E432`), delay (`0x4E4D8`), pursuit and
  escape writes, dodge checks, variant limits, and returned loot.
- [Data reference](../doc/05_data_reference.md), §§1.16 and 3.18: stored
  thief state and mode bits. [Game subsystems](../doc/04_game_subsystems.md),
  §§4.7 and 23.4, supply the wealth weights and direction-grid storage.
- The source-linked [thief implementation](../gauntpy/src/gauntpy/subsystems/thief.py)
  is a readable companion to the ROM contracts, not independent evidence
  for its behavioral claims.

[Previous: The living maze](10_the_living_maze.md) |
[Contents](README.md) |
[Next: Fighting the dragon](12_fighting_the_dragon.md)
