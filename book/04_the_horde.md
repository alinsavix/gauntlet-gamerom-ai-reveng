# 4. A room full of monsters

Shoot the first grunt in a crowded corridor and another takes its place.
Shoot that one and the opening closes again. From a distance, the party
seems to be making progress: monsters disappear, scores rise, arrows keep
flying. The generator at the far end remains untouched.

In the previous chapter, four people had to negotiate one shared space.
The monsters negotiate it too, with much simpler decisions and many more
bodies. Their apparent coordination comes partly from repeated local
choices, partly from occupancy, and partly from the steady possibility
of replacements.

Let us follow an illustrative room with two generators and a narrow
entrance. The four heroes have just reached it. The particular arrangement,
random draws, and frame numbers below are invented examples of the rules,
not a captured play session.

## A generator gets a turn, not a guarantee

A generator is not a monster with an unusually large health supply. Its
most important action is making another creature. Before that can
happen, several different gates must open.

First the generator must be in the active region around the camera. The
monster pass limits its detailed work to a window slightly larger than
the visible play area: 255 pixels horizontally and 263 vertically in its
native coordinate tests. The window wraps with the maze. A generator
elsewhere in the stored level does not keep receiving the same ordinary
opportunities as one beside the party.

Next comes scheduling. Generators do not all roll on every frame. In
ordinary, non-slow-motion play, each gets a turn once in sixteen frames,
with its phase derived from its cell number.

The exact test has a small wrinkle worth retaining in a worked example.
The game doubles both the cell number and its normal working frame
counter, forces bit 1 of the doubled cell number on, then compares under
mask `0x1E`. Written in ordinary frame and cell numbers, the condition is:

```text
(frame & 15) == ((generator_cell | 1) & 15)
```

This is the normal-path scheduling condition, not the full generator
routine. Neighboring cell numbers can share a turn; the purpose served
by the calculation is distributing opportunities, not guaranteeing that
every generator owns a unique moment.

Our example generators occupy cells 100 and 102. Their phases are five
and seven. They can try on frames 5 and 7, then 21 and 23, and so on,
provided the other gates allow it.

The probability comes from the operator's difficulty setting and the
number of active players. At the lowest setting the four entries are:

| Active players | Base probability numerator, out of 32 |
|----------------|---------------------------------------|
| One | 4 |
| Two | 11 |
| Three | 15 |
| Four | 18 |

These numbers are not population limits. Eighteen does not mean that a
four-player room is allowed eighteen monsters. It means eighteen
successful random outcomes out of thirty-two, before adjustments.

The game adds an accumulated signed bonus to the table entry. Except on
level one, it then caps the result at twice the level number. Suppose
our four players are on level four, at the lowest difficulty, with a
bonus of two. The sum is twenty, but the level cap makes the usable
value eight. A roll from zero through seven succeeds; eight through
thirty-one fails.

That is one chance in four *on an eligible generator turn*. It is not
one monster every four frames.

## Why an empty floor matters twice

Even a successful roll cannot put a creature anywhere it likes. The
generator chooses a random starting cardinal direction and examines up
to eight neighboring cells through padded direction tables. Each
candidate must pass the placement test. In particular, it must be empty,
and nearby object geometry must permit the new body to fit.

Use the eight-out-of-thirty-two probability from our example:

| Frame | Generator | Illustrative roll | Placement result |
|-------|-----------|-------------------|------------------|
| 5 | Cell 100 | 19: fails | No placement search |
| 7 | Cell 102 | 3: succeeds | All eight candidates fail |
| 21 | Cell 100 | 6: succeeds | First candidates blocked; a later one fits |
| 23 | Cell 102 | 12: fails | No placement search |

At frame 7 the second generator won its roll but produced nothing.
At frame 21 the first creates one monster at the first suitable
candidate, not one monster in every suitable neighbor. The new record's
type and strength come from the generator's current type.

Imagine that a grunt standing beside the generator moves toward the
entrance between those opportunities. It opens a candidate cell.
Destroying another grunt farther down the corridor opens room for that
movement. The player's successful shot can therefore enable a chain of
advances that ultimately makes a new birth possible.

This is why shooting from a safe distance can look like operating a
conveyor belt. The immediate kill is real. It also releases space through
which the source can replenish the line.

There is a time-pressure gate too. If the main loop has detected an
overlong frame, it forces the generator probability to zero. Existing
monsters are not deleted. New generation is suppressed while that
condition applies. The game's clock will get its own chapter; the
immediate consequence here is that an overloaded room can temporarily
stop adding bodies without having reached a programmed population cap.

The signed bonus connects this room to longer-term play. Score-per-coin
accounting can add to the stored bonus; it is accumulated feedback, not
a fresh count of living monsters. Adding a coin can decrement a positive
bonus. When a cap is binding, that change may not alter the effective
chance yet: twenty and nineteen both become eight in our level-four
example. On a later level without that binding cap, reducing twenty to
nineteen removes one successful outcome out of thirty-two.

Joining has its own initialization. A solo Warrior starts this bonus at
three, a solo Wizard at four, Valkyrie and Elf at zero; a later join
clears it. Party size simultaneously selects a different probability
column. Thus “another player means more monsters” describes a useful
tendency, not the whole calculation. The next economic chapter will
follow the score and coin producers. The generator simply consumes the
value they leave behind.

## A crowd without a route planner

The newly generated grunt must decide where to go. Ordinary target
selection compares summed absolute horizontal and vertical separation:

```text
distance = abs(player_x - monster_x) + abs(player_y - monster_y)
```

The actual calculation uses quantized, wrapping coordinate differences.
Away from a seam, this simplified expression explains the choice. It
measures how far a player is across the two axes, not the length of an
available route through the maze.

Suppose the Warrior is sixty-four pixels away horizontally and sixteen
vertically: eighty in this measure. The Elf is forty-eight away on both
axes: ninety-six. The Warrior wins, even if a wall makes the route to him
less convenient. The routine has not searched the corridors to compare
complete journeys.

IT can replace that contest. An eligible IT holder is selected ahead of
the ordinary nearest-player scan. Invisibility can exclude a player
from targeting, while repulsion can reverse the resulting pursuit
direction for relevant creatures. The crowd is responding to state,
not reading which human looks most vulnerable.

Most creatures share one behavior body with moving, attacking, and idle
states. Idle target decisions are staggered by the object's slot and
the working frame. Between decisions, the creature can continue along
its current direction. Animation counters and family-specific rules
decide when it changes phase.

The movement attempt is local. It tests the route immediately ahead and
the destination's occupancy. A clear destination allows the monster's
record to move into another cell. A player there invokes the contact
handler. A blocking body or wall prevents the simple advance.

At our doorway, three monsters can all want the Warrior without all
being able to occupy the place beside him. The leading creature reaches
contact; the following ones accumulate behind it. Remove the leader and
the next can advance. The doorway organizes the attack without any
creature needing to know that it belongs to a queue.

Level rules can change the pace. A fast family receives a two-pixel
movement value on the relevant alternate normal frames instead of the
one-pixel base, producing roughly a one-and-a-half-times speed setting
rather than a universal doubling. Other flags change directional
behavior. Slow motion skips the entire monster pass on even frames,
instead of modifying each creature's private health or turning the
player into a slower character.

None of those choices creates a long-range plan. They alter how often,
how quickly, or in which direction a local rule tries again.

## The color of the next body

At the entrance, an Elf arrow strikes a strongest grunt. The grunt
survives and changes color.

![One grunt drawn at three strengths with palettes numbered 2, 3, and 4](img/ch11_tier_palettes.png)

*ROM-derived renderings of the same artwork, weakest at left and
strongest at right. These are not photographs of successive hits.*

The three living strength values for this family are palette numbers
two, three, and four. A palette is the color table used to turn the
picture's numbered pixels into visible colors. The grunt's low position
word bits contain this selection as well as its combat strength.

A one-point hit changes four to three. Another changes three to two.
A third would leave the valid range, so the game removes the monster.
Combat has changed the same field that the display reads to select
colors; a second health-to-color translation is unnecessary.

The range belongs to the family. Demons use six through eight, while
lobbers and ordinary sorcerers use nine through eleven. A palette
number is not a universal health total across the bestiary.

Now let the Warrior's two-point shot reach a strongest generator. It
becomes the weakest generator of that family. This superficially similar
wounding uses a different representation: the game changes object type
and picture rather than subtracting ordinary monster palette strength.

Future output follows the changed generator type. Existing monsters do
not all weaken with it. Our room can contain strong survivors made
earlier, weaker new arrivals, and a damaged source that still needs one
more hit. The tactical reward for reaching the source begins before
its final destruction.

## When the doorway stops being safe

A ghost and a grunt can reach the same hero through the same gap but
leave different situations behind. The ghost spends itself on contact:
it damages the hero and disappears. The grunt remains to fight.

Against ghosts, holding the entrance can turn health into cleared floor
even without a successful shot. That is not free clearance. An intact
generator can keep supplying creatures to make the same exchange.
Against grunts, contact does not even promise to open the occupied cell.
The Warrior's hand fighting must do the work while the party manages
the cost.

A demon changes what “behind the front line” means. It can create a
projectile along one of eight compass directions, subject to aim and
range conditions and an available shared enemy-shot reservation.
The demon's firing check examines the cell immediately beside its
muzzle; it does not trace an unobstructed line all the way to the hero.

Put a potion directly beside the demon and that muzzle check prevents
creation. Put it two cells away, with the muzzle cell clear, and the
demon can fire. The later projectile collision may break a destructible
potion, but it does not release the player's potion magic.

Our party cannot assume that every fireball has a clear journey merely
because it was launched. Equally, hiding behind something shootable can
consume the thing they intended to collect. The front rank and its
missiles obey different occupancy rules.

The lobber goes further: a wall between attacker and hero need not stop
the rock at all.

## A rock aimed at where you are going

A lobber does not simply use the demon's compass-direction shot. It
first requires a middle-distance target. Its coarse coordinate deltas
must have at least one axis at or above twenty, with both below
forty-four. Those units represent two-pixel coordinate steps: roughly
forty pixels or more on one axis, but less than eighty-eight on each.
Too close makes it reverse direction instead of throwing; too far fails
the throw.

Once a target qualifies, the lobber adds a movement lead. This is where
the distinction between facing and achieved movement becomes dangerous.
The selected player's movement word says which axes actually moved.
Holding Right against a wall produces a stationary value and no
rightward prediction. Walking right into clear floor produces a
rightward lead.

The class and extra-speed state select these lead scalars:

| Target | Ordinary | Extra speed |
|--------|----------|-------------|
| Warrior | 96 | 128 |
| Valkyrie | 112 | 128 |
| Wizard | 96 | 128 |
| Elf | 128 | 160 |

They are not collision-box widths. The direction table supplies components
zero, plus two, or minus two. Multiplying them by the scalar produces the
lead contribution in the rock's native velocity arithmetic.

For a right-moving ordinary Elf, the horizontal contribution is
`128 × 2 = 256` native units. For the same Elf blocked against a wall it
is zero. There are 128 native units per pixel, so these otherwise equal
throws differ by two pixels of horizontal travel per projectile update.
That is a worked comparison of the lead term, not the complete launch
velocity: the game also adds four times the coarse target separation,
includes an anchor adjustment, and subtracts the direction-specific
muzzle contribution.

Once thrown, the rock retains the computed velocity vector: its pair of
horizontal and vertical increments. It does not home in on subsequent
turns. Each update adds those increments to separate horizontal
and vertical accumulators. Fractional parts remain in those accumulators
even though only whole-pixel position bits reach the visible object.
A velocity of 192 native units therefore advances one and a half pixels
per update on average, rather than being rounded permanently to one
or two.

The rest of the trick is collision timing. The lobber channel skips
ordinary collision testing while its lifetime counter is negative or
at least six. Testing is enabled only in the late values zero through
five. The counter advances on staggered alternate frames, independently
of the position additions. The rock can therefore cross a wall during
the early part of its flight and become dangerous near its predicted
landing region.

Imagine our Elf running right as the throw begins, then stopping and
moving back. The rock continues toward the led position. That reversal
can matter more than merely pointing the hero another way. Conversely,
pressing into a wall and expecting the lobber to aim far to the right
does not provide a feint: no achieved rightward movement was available
to predict.

The doorway remains useful against approaching bodies. It no longer
guarantees shelter from everything on the other side.

## Targets that change the terms of a hit

An ordinary sorcerer complicates the party's reading of movement.
It can relocate while reusing idle artwork because its moving-animation
pointer is empty. A picture that does not perform an obvious walking
cycle is not proof that the actor stayed in place.

Its phase matters to damage too. While the hidden phase flag is set,
ordinary shots do not reduce its strength; a supershot can hit through
that protection. Waiting for a vulnerable phase and occupying a good
firing line are separate problems. The line can fill with another
monster while the party waits.

The Super Sorcerer creates a more explicit attack on safe positioning.
It has a relocation search behind players, rather than merely a faster
version of ordinary walking. Starting with one player and trying the
others cyclically, the search tests straight behind the hero's facing,
then the two adjacent rear directions. Those probes require clear runs
of four, three, and three cells.

A destination must be visible, in valid maze rows, and empty apart from
the relocating creature's own allowed slot. A further nearby-object
test prevents placing it too close to another body. If the search
exhausts its candidates, it fails. The existing Super Sorcerer is being
relocated, not multiplied.

Facing really does matter to this search. A wall that blocks the Elf's
movement can defeat a lobber feint while the Elf's chosen facing still
changes which directions the Super Sorcerer considers “behind.”

A potion against a phasing Super Sorcerer reveals it, clears its phase
state, and skips its remaining action on that potion pass. This is not
an indefinite immobilization. Later idle updates advance its state and
can lead to firing. A party that treats the reveal as permanent safety
can be surprised from behind.

Acid is slower and less purposeful. Its idle decision rolls a direction
rather than picking a hero to chase, and its special phase uses a slow
rate mask. Initial contact can impose a 32-frame player stun. A puddle
need not pursue efficiently to obstruct a route on which fast movement
was essential.

Magic against idle Acid first puts it into its special active phase;
other eligible Acid states reach the destructive table entry. As with
the Super Sorcerer, checking state precedes interpreting the all-zero
magic row. “Zero means destroyed” applies to a target that reaches the
lookup, not every creature with that type under every condition.

## Death keeps a different account

At the back of our room waits Death. Ordinary shooting will not work
through three palette colors and finish it. A potion is the direct
answer, provided the target is within the affected region. Spending the
Wizard's last potion on generators earlier has therefore changed this
encounter before the party arrives.

Death also has a threshold mechanism, but the counter belongs to the
player, not to the individual Death record. Resolved contact adds four
normally, or three with the armor-power selection. A supershot adds
twenty-five. When that player's accumulated amount becomes **greater
than 200**, the game clears the counter and dismisses the Death involved.

Starting from zero, eight supershots total exactly 200 and are
insufficient. The ninth crosses the threshold. For contact alone, the
unarmored contribution crosses it on the fifty-first addition; the
armored contribution on the sixty-seventh. These are accepted additions,
not a guaranteed number of elapsed frames or a recommendation to pay
for an encounter by standing still.

Since the counter is player-owned, contributions can span encounters
with different Death creatures within the level. They do not combine
into a party-wide attack total. Successful player placement resets the
counter on normal level entry or a new join.

There is also a separate global Death-hit counter. Every player shot
against Death increments it, including ordinary shots that add nothing
to the dismissal accumulator. The magic scoring path uses its low
three bits to choose a score and popup variant. Counting ordinary
impacts and accumulating threshold damage are different operations.

Finally, IT cannot be cleared by ordinary potion magic. Its greatest
effect may occur after the original creature has disappeared on
contact: the tagged player changes the crowd's target selection until
the condition changes again. Passing IT at the doorway can redirect
many later local decisions without moving a single monster immediately.

The room's threats now form one connected problem. Ghosts trade
themselves for health; grunts hold space; demons test the firing lane;
lobbers challenge cover and continued movement. Sorcerer phases alter
when a shot counts, a Super Sorcerer contests the rear, and Acid makes
timing a passage harder. Death changes which resource can end the
encounter, while IT changes who is asked to bear it.

Behind them, a damaged generator receives another turn. Whether it adds
one more body depends on a roll, a signed adjustment, the game's timing,
and a suitable piece of floor. A crowd does not need a collective mind
to become overwhelming. It needs repeated chances to occupy the space
the players are trying to win.

## Source notes

- [Game subsystems](../doc/04_game_subsystems.md), §§3.1–3.7, 4.6.1,
  and 26: the shared behavior body, culling, generator gates, targeting,
  specialist states, magic, and damage. Relevant routines include
  `monsters_everything` (`0x40E6A`), `handle_generate` (`0x492C0`),
  and `monster_find_and_shoot` (`0x41750`).
- The worked schedule follows direct disassembly at `0x40EAA–0x40EEC`
  and `0x41026–0x41036`, including the doubled normal frame and the
  slot's `OR 2`. The probability comparison at `0x49300–0x4930E`
  requires the numerator to be strictly greater than the random result.
  Placement tables are at
  `0x57B50/0x57B68/0x57B80`; the candidate checker is `0x48F12`.
- [Data reference](../doc/05_data_reference.md), §§1.1 and 5:
  `monster_spawn_probability_table` (`0x40E46`), the signed bonus,
  class-dependent solo initialization, and the distinct Death counters.
  The complete accounting belongs in
  [What a quarter buys](08_what_a_quarter_buys.md).
- Lobber range and prediction were checked at `0x41750–0x41A22`.
  High-byte position differences have two-pixel granularity; the
  direction components at `0x580D8/0x580EA` are zero or ±2.
  The lead calculation reads the target's achieved-movement word at
  `0x41986` and selects its direction vector at `0x41994–0x419B0`.
  Collision gating is at `0x4755C–0x47584`; fractional flight at
  `0x479C2–0x47A58`.
- Acid's special rate gate uses the *working* frame byte at
  `0x413FA`, not an unqualified display-frame count. Initial contact's
  32-frame stun is written at `0x49990–0x49996`. Super Sorcerer
  relocation is `0x5FDE0`; potion reveal and subsequent idle behavior
  are separate paths at `0x415AC` and `0x4112C`.
- The [tier illustration](img/ch11_tier_palettes.png) is rendered from
  graphics-ROM data. All worked scenarios are illustrative.
  [The monster reconstruction](../gauntpy/src/gauntpy/subsystems/monsters.py)
  can help readers follow the code, but agreement with it is not
  independent original-ROM evidence.

[Previous: Three friends, one screen](03_four_players.md) |
[Contents](README.md) |
[Next: Painting the dungeon](05_painting_the_dungeon.md)
