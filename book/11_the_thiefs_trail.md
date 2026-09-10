# 11. The thief's trail

The warning arrives after the important decision. Before a thief appears,
the game has selected a victim, remembered where that player stood, and
begun recording where they went next. The little figure entering behind
the party is not surveying the dungeon and deciding which route looks best.
It is reading a route that a player has been writing.

Imagine leaving a room, turning down a corridor, and taking a transporter.
You have put walls and a considerable distance between yourself and the
place where you started. A visitor arriving there later nevertheless follows
you. When it catches you, it turns around and leaves with something valuable.
The apparent intelligence includes both finding you and knowing how to get
away.

Those journeys have different authors. You supply directions for the
pursuit; the pursuer supplies directions for its escape. The game packs
both into the same bytes.

## Who is worth robbing?

The thief's idea of wealth is not the number on the score display. Its
target calculation adds up carried advantages:

| Possession | Contribution to target wealth |
|------------|-------------------------------|
| Extra shot power | 1,000 |
| Extra speed | 700 |
| Extra shot speed | 500 |
| Extra magic power | 300 |
| Extra armor | 200 |
| Extra fight power | 100 |
| Each potion | 3 |
| Each key | 2 |
| Current score multiplier | Its numerical value |

The first six entries are present-or-absent powers. Extra speed contributes
700 once, not 700 for each frame it helps you move. A multiplier of three
contributes three, including the ordinary baseline of one.

Consider this invented party, with all three heroes active:

| Player | Carried possessions | Wealth |
|--------|---------------------|--------|
| Red | Speed, three potions, two keys, multiplier 3 | 700 + 9 + 4 + 3 = **716** |
| Blue | Shot power, one potion, no keys, multiplier 2 | 1,000 + 3 + 2 = **1,005** |
| Yellow | Speed, armor, two potions, four keys, multiplier 1 | 700 + 200 + 6 + 8 + 1 = **915** |

Blue is the target. Red could have the highest score and Yellow the most
health without changing that result. Health matters to whether someone is
an eligible living player, but its amount is not another term in this
valuation. Character class is not a term either.

The large separation between powers and supplies has a practical effect.
A handful of extra keys cannot compensate for the difference between
having shot power and having no upgrade. The inventory that makes Blue
effective against strong monsters also makes Blue interesting to the thief.

Selection fixes a player number and an old location. It does not continually
transfer the pursuit to whoever happens to become richest while the visitor
is on its way. The game can now watch one person's movement and build one
useful trail.

## The delay is time to leave a trail

First the level has to qualify for a visit. The scheduling roll compares
the level number divided by eight, discarding the fraction, against a random
integer from zero through seven. Levels six and seven cannot win; levels
eight through fifteen win one time in eight; sixteen through twenty-three
win two times in eight. From level sixty-four, the roll always succeeds.
Treasure rooms are eligible. Secret challenge rooms are not.

Winning this roll does not put the thief beside you immediately. The game
saves the target's cell, then calculates an arrival delay using the target's
score and coin count. This is a second meaning of wealth, distinct from
the inventory sum that chose Blue.

For an ordinary maze, the calculation can be written as:

```text
W = min(15, (score >> 13) / recorded_coins)
D = 50 - (min(level - 6, 100) >> 1)
arrival frames = (20 - W + random_integer_below(W + 10 + D)) * 60
```

*Explanatory notation for the ROM's integer arithmetic. Division discards
the remainder; shifting right by thirteen divides by 8,192.*

Give our Blue player a score of 196,608, earned on three recorded coins,
at level 38. The score first becomes 24, then the division by three gives
`W = 8`. Depth contributes `D = 50 - 16 = 34`. The random bound is therefore
`8 + 10 + 34 = 52`, allowing values zero through 51.

Suppose the draw is 17. The resulting delay is
`(20 - 8 + 17) × 60 = 1,740` frames, about 29 seconds at the nominal frame
rate. Across all possible draws, this example ranges from 720 to 3,780
frames: about twelve to sixty-three seconds. These are calculated examples,
not timings from a captured game.

At level 106, the depth term reaches zero. With the same score and coins,
the range narrows to twelve through twenty-nine seconds. Depth removes
some possible waiting time; it does not remove the base wait. A player
whose scaled score is zero still has a twenty-second minimum on an ordinary
maze.

Treasure rooms use a shorter branch: the score term is capped at five,
the base is ten, and both the depth term and random range are smaller.
The visitor can be part of a hurried collection run rather than something
that invariably arrives after it is over.

Throughout the countdown, the victim is already writing directions.
Deployment uses the saved *old* cell, not the player's current cell.
An arrival effect then accompanies a further sixty-frame entrance pause.
By the time pursuit starts moving, it has a journey to read.

## Two drawings of the same corridor

Here is a small invented route. It is a schematic, not a stored maze or
an original-game capture. Rows increase downward; A is the saved start.
P and Q are transporter pads. D is the clear landing cell to the right
of Q, and the victim finishes at E.

```text
PLAYER-WRITTEN PURSUIT

      A → B                 Q → D
          ↓                     ↓
          C → P                 E

      Transporter link: P ==> Q

VISITOR-WRITTEN ESCAPE

      A ← B                 Q ← D
          ↑                     ↑
          C ← P                 E

      Transporter link: Q ==> P
```

*The two patches of floor are spatially separate. Ordinary arrows belong
to cell routes. Transporter
connections and landing directions also need separate pad records.*

When the player leaves A for B, the movement handoff writes “east” at A.
Leaving B for C writes “south” at B. Leaving C for P writes “east” at C.
These instructions live at the places being left. They answer the
pursuer's question on arrival: which way did the victim go from here?

Now let the thief follow. When it reaches B from A, it records “west”
at B in the escape route. When it reaches C from B, it records “north”
at C. These instructions live at the places being reached. They answer
the later question: which way takes me back?

Neither write has to destroy the other. A byte contains eight bits,
and half a byte—a *nibble*—is enough for one of eight directions plus
an empty marker. The pursuit occupies the low nibble. Escape occupies
the high nibble.

The direction numbers go clockwise: north is zero, east two, south four,
west six, with diagonals between them. Storage adds one, reserving zero
for an unwritten entry. Once the thief has followed our player through
B and C, their bytes can look like this:

| Cell | High nibble: escape | Low nibble: pursuit | Packed byte |
|------|---------------------|---------------------|-------------|
| B | West: 6 + 1 = 7 | South: 4 + 1 = 5 | `0x75` |
| C | North: 0 + 1 = 1 | East: 2 + 1 = 3 | `0x13` |

Reading B during pursuit selects the five, subtracts one, and obtains
south. Reading exactly the same byte during escape selects the seven
and obtains west. Changing a mode bit changes which route is visible to
the movement code. It does not launch a search for an exit.

The two writers also have different overwrite rules. A player's later
departure replaces the low nibble. The visitor fills the high nibble
only if it is empty and it is not already escaping. Revisiting a junction
can therefore change the pursuit instruction without erasing the earlier
way back. This is local memory, not a chronological recording of every
step everyone has taken.

## Directions in the invisible columns

Where would you put those two maps? The game uses memory belonging to the
text display.

The text layer has storage for sixty-four character columns, but only
forty-two are visible. Each character descriptor is a two-byte word.
The remaining twenty-two words provide forty-four bytes per row that can
hold information without printing it over the maze.

The route starts in those hidden columns. Twenty-four rows supply 1,056
bytes, enough for a byte for each of the world's 1,024 packed cell numbers.
The storage rows are forty-four route bytes wide even though the maze is
thirty-two cells wide. These are two different arrangements of the same
numbered entries, not a forty-four-column dungeon.

For example, assign B above the maze coordinates row four, column five.
Its packed cell number is `4 × 32 + 5 = 133`. Divide 133 by 44: the quotient
is three and the remainder one. Its route byte is thus in storage row
three, one byte after that row's hidden-column start. Adjacent maze cells
usually occupy adjacent bytes, but crossing a storage-row boundary has
no visible significance in the dungeon.

The display's level-show and level-hide operations clear the hidden words.
That also clears both route nibbles. A new maze does not inherit directions
through walls that belonged to its predecessor.

The memory reuse is compact, but the stronger economy is in the work being
done. Player movement already knows the old and new cells. Recording one
direction there is cheap. Pursuit later reads one direction instead of
reconstructing how those cells were connected.

An absent instruction does not cause the thief to search the maze.
The route reader keeps its previous direction when an entry is empty or
invalid. A useful pursuit therefore depends on the earlier scheduling
and trail-writing sequence. Its apparent knowledge was accumulated before
the warning, not invented when an obstacle appeared.

## Carrying the route through a transporter

An ordinary arrow cannot describe the jump from P to Q. Pointing northeast
would merely send the thief into whatever lies between them.

When the victim transports, the game records the destination pad's identity
and the direction from that pad to the landing cell. In our example, the
forward link says P leads to Q, and the landing information says to step
east from Q into D. The pursuit byte at D then supplies the next ordinary
move, south toward E.

The thief checks the learned connection when it reaches P. A valid pad
link and usable landing space let it enter the shared transporter animation.
This is still movement through the actual world: a remembered destination
is not permission to overlap an obstructing occupant.

Its approach supplies another piece of information. The thief came to P
from C, so the return-side step-off points west from P. On escape it can
reach Q from D, use the reverse pad connection to P, and emerge toward C.
The high-nibble arrows then take it north to B and west to A.

That division explains why there are both cell directions and pad records.
The cell map tells a walker what to do next on continuous floor. The pad
record tells the transporter which discontinuity belongs to the journey
and which adjacent cell continues it. Together they connect a route that
neither representation could express alone.

Reaching the recorded start on the return journey provides the normal
successful getaway. The visitor disappears with a transporter-style
effect. It need not find the exit the players are using.

## Fast does not mean unstoppable

![Thief and mugger artwork side by side](img/ch12_thief_mugger.png)

*ROM-derived downward-facing artwork, rendered side by side for comparison.
This is an illustration of the variants, not a captured encounter.*

The ordinary thief's speed is `0x200` in the game's position units; the
mugger's is `0x180`. There are 128 such units per pixel:

| Walker | Straight-line request before movement restrictions |
|--------|----------------------------------------------------|
| Ordinary Warrior or Wizard | 1, 2, 1, 2 pixels over four updates |
| Ordinary Valkyrie | 1, 2, 2, 2 pixels over four updates |
| Ordinary Elf | 2 pixels per update |
| Mugger | 3 pixels per update |
| Thief | 4 pixels per update |

The heroes alternate whole-pixel steps as described in
[Chapter 3](03_four_players.md). The visitor's movement can shorten its
nominal step to reach a cell-centering position rather than overshooting.
These requests exclude speed powers, pauses, collisions, and diagonal
components; they are not measured average speeds through a maze.

Even so, simply running away along a straight passage is not much of a
plan. In an idealized constant-speed comparison, ignoring centering and
other restrictions, a thief gains two pixels per update on an ordinary
Elf. A 32-pixel gap would close in sixteen updates. The mugger's nominal
one-pixel gain would take thirty-two.

Those calculations isolate the speed advantage, not guaranteed contact
times. Actual steps can be shortened; the route may turn; the bodies may
meet before their reference positions coincide; an obstacle may consume
updates. Being slower than the thief does not make the mugger's nominal
step slower than an unenhanced hero's.

An ordinary monster or generator blocking the visitor can start a short
fight. A shared animation counter advances, and after it passes fifteen
the contact path removes the blocker. A crowded corridor can delay the
thief without reliably imprisoning it.

Shooting brings a different response. The dodge check looks for an active
player aligned on one of the eight directional rays whose shot direction
opposes the thief's direction. It is not a simulation of every projectile's
future path. Finding that particular threat starts a dodge and temporarily
switches which route the visitor follows; the routine remembers the
shooter and direction so it can end the dodge when the direction changes.

The escape information is therefore useful even before a successful
theft. It gives the visitor somewhere to retreat from an aligned attack.
An arrow down the corridor remains dangerous, but the target need not
continue obligingly toward it.

## What the loot actually contains

Contact turns pursuit into escape and chooses the loss. Permanent powers
take priority, in the same descending order used by their wealth weights.
Our Blue player loses extra shot power.

The carried reward is important: stealing a power gives the thief an
ordinary potion pickup, not a hidden potion encoding that particular
upgrade. Killing it does not automatically restore Blue's shot power.
The loss and the recoverable object are different things.

Without a permanent power, the thief compares three times the potion
count, twice the key count, and the current multiplier. A strictly largest
category wins. If those comparisons leave a tie, it prefers potions when
any are present, then the multiplier, then keys. It takes one potion or
one key, not the entire inventory of the winning category.

For example, two potions, one key, and multiplier three produce weights
six, two, and three. One potion is stolen; the multiplier stays three.
With no potions, one key, and multiplier three, the multiplier wins
instead. It becomes one, and the carried object becomes a score bag with
a base value of `3 × 500 = 1,500`.

That bag is compensation in points, not a multiplier-restoring power.
Someone collecting it with multiplier two receives 3,000 points through
the ordinary score-addition rule. A different hero can collect it.

Kill the visitor and its carried object drops at the death location.
The killer also receives a separate base 500-point bounty through their
current multiplier. If the visitor escapes, the game saves the loot for
placement on the next eligible level instead. It chooses a candidate
cell and steps through alternatives until it finds empty, non-reserved
space; secret rooms are excluded. The returned potion, key, food, or bag
is a floor object that still has to be reached.

The mugger makes the distinction especially plain. It removes 100 health,
clamping the victim at zero, and carries wholesome food. Someone else
can eat that food. Even successful recovery does not rewind time, undo
intervening damage, or reserve the meal for its original victim.

Each variant has one successful-theft allowance per level. The allowance
is spent when it steals, not when it finishes escaping. Killing a thief
after the loss prevents that getaway but does not undo the used allowance.
Killing one before theft leaves the allowance unused and permits another
scheduled visit. Once both thief and mugger have stolen, scheduling stops.

The trail, the loss, and the reward thus belong to different stages of
the encounter. You can interrupt one stage without reversing the others.
The useful question on hearing the warning is not just where the thief
is now. It is what route you have already supplied, what it stands to
take, and where you might intercept its return.

### Source notes

- [Game subsystems](../doc/04_game_subsystems.md), §§4.7 and 9:
  wealth, scheduling, trail ownership, movement, dodge, and returned loot.
  Numerical checks here follow `thief_target_calc` (`0x4DFF6`),
  `thief_timer_set` (`0x4E4D8`), and `thief_steal_from_player` (`0x4E1FE`)
  in the game ROM. The theft priority masks are at `0x5B62E`.
- [Game subsystems](../doc/04_game_subsystems.md), §23.4, and
  [data reference](../doc/05_data_reference.md), §1.16: nibble storage,
  saved positions, and carried-item fields. The setters/readers at
  `0x50FD2–0x51078` divide cell numbers by 44; transporter route writers
  are at `0x4E684` and `0x4E73A`.
- The ROM theft arms store pickup `0x34` for a stolen upgrade or potion,
  `0x35` for a key, and `multiplier × 500 × 64 + 0x30` for a score bag.
  Speed and allowance checks are at `0x4E516–0x4E566`; movement consumes
  the speed at `0x4EA36` and clamps centering steps at `0x4EB28–0x4EB68`.
  Escaped-loot
  placement is at `0x44166–0x441A6`.
- [`thief.py`](../gauntpy/src/gauntpy/game/subsystems/thief.py) provides a
  readable reconstruction of these mechanisms, not independent
  confirmation of them. Diagrams and numerical situations above are
  illustrative; no new execution capture is implied.

[Previous: The living maze](10_the_living_maze.md) |
[Contents](README.md) |
[Next: Fighting the dragon](12_fighting_the_dragon.md)
