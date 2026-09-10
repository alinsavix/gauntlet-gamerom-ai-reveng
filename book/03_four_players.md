# 3. Three friends, one screen

The Warrior is holding a doorway. Behind him, the Valkyrie has found a
key; the Elf can see a generator and wants to reach it before the
corridor fills. A fourth friend supplies credit, chooses Wizard, and
presses Magic to join. There should be room for one more person. There
may not be room for one more hero.

We will follow this invented party through an illustrative stretch of
dungeon. It is not a recording of a particular maze. The situations let us
separate three questions that are easily confused while playing: what a
player requests, what movement the game accepts, and what the shared view
does afterward.

Those questions belong together. A faster character cannot run through a
friend, a new arrival cannot appear inside a monster, and four independent
sets of controls do not buy four independent screens.

## First, find somewhere to stand

The first player in a level has a remembered starting cell. Maze setup
chooses it from the stored start markers and saves its identity; placement
does not depend on finding a marker still visible on the floor.

Our Wizard is joining an existing party, so the game uses another search.
It examines the cells immediately left, right, above, and below an
existing hero, then proceeds around the other heroes if necessary. A
candidate must be empty and on screen. The first suitable candidate wins.
This is a local placement search, not permission to choose any comfortable
corner of the maze.

Suppose the Warrior has walls on two sides, a grunt ahead, and the
Valkyrie behind. Those four cells supply no opening. The search can still
succeed beside the Elf. If every existing hero is similarly boxed in, it
fails and the game announces that it is unable to join the newcomer.
Clearing one cell can make the difference.

Placement comes before the join's final welcome and status updates.
Successful placement creates the hero, establishes its movement and
effect state, and increments the active-player count. Only then does the
join wrapper finalize the arrival, redraw the information panel, and send
the welcome. Credit and character choice alone do not establish a body
inside the level.

This happens without stopping the other three people's lives. While the
fourth player selects a class, the Warrior can be fighting. Later, the Elf
can finish an exit sequence and wait for the next level while the Wizard
remains here. A dying player can move toward removal and initials entry
while somebody else carries on. These are separate player states inside
one continuing game, not a single party-wide switch from “playing” to
“finished.”

Our friends clear space, and the Wizard appears. Now the party has four
projectile reservations, four health totals, and four bodies to get
through the same doorway.

## The Elf's advantage, in pixels

Player color identifies a physical control position, not a class. Any of
the four positions can choose any hero; four Wizards would be legal.
Our varied party is a useful example because shared routines will now
read four different sets of numbers.

Movement speed is more interesting than a single integer per hero. In
ordinary mazes the game combines a base step with a frame-dependent extra
pixel. For an unobstructed axis, the four-frame pattern is:

| Hero | Ordinary step pattern, pixels | With extra speed |
|------|-------------------------------|------------------|
| Warrior | 1, 2, 1, 2 | 2, 2, 2, 2 |
| Valkyrie | 1, 2, 2, 2 | 2, 2, 2, 2 |
| Wizard | 1, 2, 1, 2 | 2, 2, 2, 2 |
| Elf | 2, 2, 2, 2 | 2, 3, 2, 3 |

The table starts at a frame whose low two bits are zero. These are proposed
steps, not guaranteed distances. Over four clear movement opportunities
the ordinary Warrior requests six pixels and the Elf eight. With the
speed upgrade they request eight and ten. Diagonal input asks the movement
routine to resolve both axes; the table is not a measurement of diagonal
distance along the floor.

Holding Fire changes the situation before collision even begins. It
bypasses the ordinary walking call, and the shooting wind-up and close
fight state impose their own restrictions. A speed advantage does not
mean that a hero advances while performing every other action.

Strength is similarly divided. Against ordinary monsters the unpowered
hand-fighting base is two for Warrior and Valkyrie, one for Wizard and
Elf. Extra fight raises those bases to three, three, two, and two.
Generator fighting has a separate table. There is even a position-indexed
random hand-damage term: its nonzero entry belongs to the fourth control
position, rather than to the Elf as a class. “The Elf's damage” is not
enough information to reproduce every close-combat result.

Armor is another independent lookup, not a universal percentage deducted
from all harm. An ordinary demon projectile costs an unpowered Warrior
four health, Valkyrie three, Wizard five, and Elf four. With extra armor
the corresponding entries are three, two, four, and three. In our
doorway, five such accepted hits would cost the unpowered Valkyrie fifteen
health and the Wizard twenty-five. That comparison holds the projectile
class constant; contact and forcefields consult other tables.

The Valkyrie has a reason to offer the Wizard shelter. The game does not
assign her a protective role. It supplies the costs from which the friends
can make that arrangement.

## A request is not a displacement

Now the Elf presses diagonally toward the entrance. The game does not
slide a picture continuously until a painted pixel touches a wall. It
proposes an endpoint and asks its collision routines whether that
endpoint is acceptable.

The primary movement is transactional by axis:

```text
try the complete horizontal step
keep it if accepted; otherwise restore the old horizontal position

try the complete vertical step using the resolved horizontal position
keep it if accepted; otherwise restore the old vertical position

resolve the destination cell and commit the resulting position
```

This is simplified pseudocode; particular collision responses can perform
additional moves. The ordinary step is not automatically divided into
one-pixel pieces.

An illustrative two-pixel diagonal request can therefore have these
results, before special responses:

| Requested motion | Horizontal result | Vertical result | Accepted motion |
|------------------|-------------------|-----------------|-----------------|
| Right and down | Clear | Clear | Two right, two down |
| Right and down | Blocked | Clear from old X | Two down |
| Right and down | Clear | Blocked from new X | Two right |
| Right and down | Blocked | Blocked | None |

That axis order gives walls their sliding behavior. Failure on one axis
does not necessarily cancel success on the other.

The probes themselves are not symmetrical boxes. The player's horizontal
probe examines the adjacent cell; a vertical probe examines the forward
cell and its two horizontal flanks. Finding a record in one of those
cells is only the start of the test. The game compares object anchors,
the reference positions used to locate their artwork, on both axes.
Wall markers have an anchor correction before that comparison.

This matters because a hero's picture is 24 pixels wide, while maze cells
are 16 pixels across. Picture overlap and blocked movement are not
identical. The collision test uses a strict separation threshold of
`0x7C0` in native position units, or 15½ pixels, on both axes. It does
not inspect the outline of the hero's colored pixels.

Suppose the Elf approaches between two walls and is slightly off the
entry line. The forward cell is empty, but a flank fails the anchor test.
Special wall responses can retry the blocked axis at one pixel and nudge
the other axis away from that flank. Continued input toward the passage
can therefore bring the hero into alignment and then admit the next
step. This is explicit corner assistance, not a promise that every
blocked two-pixel proposal will be shortened until something fits.

It also is not permission to squeeze through the Warrior. When another
hero occupies the destination, that occupancy still matters. The movement
tail distinguishes staying within the same cell from entering a new one.
A clear destination lets the hero's record migrate there. A collectible
gets its interaction first; if the interaction cannot handle the occupied
cell, the proposed entry is abandoned. The game does not overwrite the
occupant merely because the moving picture seems close enough.

The Warrior must make room.

There is one more distinction worth keeping for the next chapter. Facing
records where the hero is aiming; achieved movement records which axes
actually succeeded. Facing right against a wall can coexist with zero
rightward displacement. Poison adds another separation: while dizziness
is active, held Up cycles through Up+Right, Up, Up+Left, and Up, without
changing the Fire and Magic bits. A stun instead suppresses ordinary
movement while its timer runs. Those are different reasons for the
controls not producing the straight walk a person expected.

## The camera has a vote, but not a joystick

The Warrior steps aside. The Elf passes through and runs ahead, leaving
the other three near the entrance. Soon the limiting obstacle is no
longer a body. It is the edge of the shared view.

Two separate systems produce this result. The camera calculates where
the view should move. Player movement checks whether a proposed position
is allowed inside the current viewing window. The camera does not directly
drag the Elf backward.

For the horizontal camera calculation, begin with its current register
position plus 104 pixels. That center seeds both ends of an extent: the
minimum and maximum positions the camera is considering. Eligible player
cell anchors and live positions expand the extent. Its midpoint supplies
a target, from which the game subtracts 104 to obtain the new horizontal
scroll target.

Including the current center changes the answer. Here is a simplified,
non-wrapping horizontal calculation for our four friends, with matching
cell and live anchors and no outlier correction. Their zero-based cell
columns are 15, 16, 17, and 18. The camera converts each column to
`column × 16 − 4`, giving the four reachable anchors below; assume their
live positions currently match those anchors.

| Quantity | Pixels |
|----------|--------|
| Current horizontal scroll | 100 |
| Current center used in the extent | 204 |
| Four hero anchors | 236, 252, 268, 284 |
| Extent including the center | 204 through 284 |
| Midpoint | 244 |
| Target scroll, midpoint minus 104 | 140 |
| Scroll after this update | 102 |

The midpoint of the heroes alone would be 260, producing target 156.
That is not this algorithm. The old center gives the moving party a
different target, and smoothing prevents an immediate jump even to 140:
when the target is at least three pixels away, the camera moves only two
pixels per axis. It snaps the remaining distance when that distance is
smaller. Vertical tracking follows corresponding extent arithmetic with
the game's upward-counting coordinate converted for display.

Wrapping mazes require another precaution. Across a 512-pixel seam,
coordinates 508 and 12 can describe neighbors sixteen pixels apart.
A raw midpoint of 260 would send the view toward the wrong part of the
maze. The game folds positions into a 512-pixel interval around the
current camera center before expanding the extent. In a view crossing
that seam, 12 can be treated as 524. The midpoint of those two illustrative
points is then 516, not 260.

Very distant live positions also receive special handling: a separation
greater than 320 pixels invokes a 200-pixel outlier adjustment. That is
neither a universal 200-pixel extent cap nor simply “ignore the distant
player.” Finally, non-wrapping levels clamp the resulting scroll
registers to their allowed bounds.

The Elf's movement check uses different quantities. Unless the level
permits players off screen, the proposed horizontal anchor relative to
the movement origin must pass a `0x7000` native-unit window; vertically
the threshold is `0x7400`. These correspond to 224 and 232 pixels.
They are anchor tests, not instructions to subtract the entire hero
sprite width again. The origins used for those tests are not a promise
that a screenshot's visible crop begins at the same coordinate.

Our Elf can thus reach the permitted edge while the camera is still
gliding, or while the Warrior behind constrains the party's extent.
Another successful walking proposal depends on the others making
progress. Extra speed gets the Elf to the argument sooner; it does not
win it.

## Twelve spaces, and who should carry the potion?

The party reaches the generator room. A potion lies near its entrance.
The Wizard wants it. The Warrior is closer.

There is no shared inventory. Each hero has a combined capacity of twelve
keys and ordinary potions, not twelve of each. A Warrior with nine keys
and three potions is full. Spending a key or using a potion creates room
for either kind. If another active player can still accept the pickup,
a full hero does not simply add it to an invisible thirteenth pocket.

Power upgrades have a different route. The six permanent improvements are
armor, speed, magic, shot power, shot speed, and fight. A newly acquired
power sets its own state rather than consuming an ordinary potion place.
Collecting an already-owned permanent power falls back toward ordinary
potion collection. With full pockets, the duplicate can instead become
100 points in solo play; in multiplayer it can remain for somebody else.
Who already owns the power matters before anyone discusses who needs
another potion.

Temporary effects are separate again. Invisibility changes eligibility
for ordinary monster targeting; repulsion changes pursuit behavior.
Invulnerability is not the armor table, and supershots and reflection
alter projectile interactions rather than permanently improving the
class's ordinary weapon. A brightened or changed hero is not necessarily
carrying a seventh permanent stat upgrade.

For this room, assume nobody has extra magic and that the visible targets
include ordinary ghosts and a strongest-tier ghost generator. Here are
the results of spending a carried potion:

| User | Ordinary ghosts | Strongest ghost generator |
|------|-----------------|--------------------------|
| Warrior | Lose two strength steps | Unchanged |
| Valkyrie | Lose two strength steps | Unchanged |
| Wizard | Destroyed | Destroyed |
| Elf | Destroyed | Becomes the weakest tier |

Two steps kill a weak or middle ghost but leave a strongest one alive.
The Elf's potion clears those ordinary bodies as completely as the
Wizard's, yet leaves a source of replacements. If the party wants a brief
opening, either can supply it. If it wants to stop this generator now,
the Wizard's ordinary magic achieves more.

The game obtains that distinction from a matrix indexed by target type,
user class, extra-magic state, and whether the potion was carried or
triggered by a player's shot. Zero in this table means destruction, not
zero damage. Nonzero monster entries subtract strength; nonzero generator
entries name the replacement type.

Shooting the floor potion selects a different set of columns, generally
weaker than carried use. A monster projectile can break a destructible
potion without activating its magic at all. Letting the Wizard collect
it therefore secures both ownership and the carried-use path.

The friends agree. The Warrior clears the approach, the Wizard takes the
potion, and the group moves far enough for the intended targets to fall
inside the monster scan's active area. Magic is not a blast across the
whole stored maze. Nor does holding the button automatically spend the
whole inventory: ordinary play recognizes a newly pressed Magic action.

## When making room becomes making trouble

Suppose the next encounter leaves the Elf IT. Ordinary target selection
now gives that eligible hero priority. The Elf returns toward the party
with the crowd following.

The curse can be passed by moving into another player. Direction matters:
the mover must already be IT. The Warrior running into the marked Elf
does not take the curse by that act alone. When the Elf tags the Warrior,
the game changes the owner, updates the label and announcement, and gives
the recipient a 64-frame stun. Recursive corner-assistance retries cannot
perform another tag.

That makes the same doorway useful for an entirely different purpose.
Earlier it restricted enemy access. Now it restricts a friend's escape
from the approaching Elf.

Some levels add player-shot stun, damage, or both. A qualifying shot on a
stun-enabled level adds forty frames of stun, capped at ninety. The damage
rule costs two health for an ordinary player shot, ten for a supershot;
it does not simply reuse the Warrior's ordinary monster-damage number.
The victim's acid/invulnerability state can suppress these effects.
The level flags determine whether the interactions are enabled in the
first place.

Stun does not necessarily leave the Wizard helpless. The carried-potion
handler has no movement-stun gate. A stunned hero who still has a potion
can use Magic, while the movement timer continues to hold the body in
place. That is another reason to distinguish losing movement from losing
every possible action.

Our party can cooperate brilliantly or obstruct itself. Either outcome
uses the same placement search, axis checks, cell ownership, camera
extent, and separate inventories. The game need not understand an
agreement to make breaking it consequential.

Beyond the doorway, the monsters are negotiating much of the same space.
They have fewer decisions to make, but there are many more of them.

## Source notes

- [Game subsystems](../doc/04_game_subsystems.md), §§4.1–4.6, 17, 22,
  and 26: joining, transactional movement, corner assistance, inventory,
  camera, Magic, IT, and player-shot effects. Door-helper zero-return
  semantics remain a strong inference in that reference; this chapter
  does not depend on naming that return as an independently observed event.
- Movement patterns were checked against `player_speed_normal` and
  `player_anim_rate`, ROM `0x580A8–0x580C7`, and their consumer at
  `0x4A92C–0x4A95C`. The ordinary-maze qualification excludes the
  maze-number ≥115 speed override. Hand-power bases and the separately
  position-indexed random term are documented in §4.2.1.
- The incoming demon-shot example uses the first two rows at `0x596CE`,
  with ordinary generated-shot strength bits clear. The carried-magic
  comparison uses the ghost row and type-30 generator row of
  `potion_effect_matrix` at `0x5DA98`; see also the
  [data reference](../doc/05_data_reference.md), §§5 and 8.
- Camera pseudocalculations isolate horizontal behavior. Direct
  disassembly of `0x46CAA–0x46F54` confirms that both eligible cell
  anchors and live positions participate, with the current center
  seeding the extrema. The cell-column conversion is at
  `0x46D62–0x46D6E`: mask to five bits, multiply by sixteen, subtract
  four. Movement edge gates are separate branches in `player_try_move_core`.
- All party situations and numerical movement/camera examples here are
  illustrative, not captured original-ROM play. The reconstructed
  [player frame loop](../gauntpy/src/gauntpy/game/subsystems/players.py),
  [join routines](../gauntpy/src/gauntpy/game/subsystems/player_lifecycle.py),
  [movement](../gauntpy/src/gauntpy/game/subsystems/player_movement.py), and
  [camera](../gauntpy/src/gauntpy/game/subsystems/camera.py) are useful
  reading but are not independent confirmation of their sources.

[Previous: One arrow in the air](02_one_arrow.md) |
[Contents](README.md) |
[Next: A room full of monsters](04_the_horde.md)
