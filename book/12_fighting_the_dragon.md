# 12. Fighting the dragon

A shot reaches the dragon and disappears in an impact. Another shot, aimed
at nearly the same place, produces the distinctive hit response. If both
looked accurate, why did only one count?

The encounter joins two moving targets: the head's position and its moment
of vulnerability. Hitting a large red shape is not enough. A successful
shot must find the head during a firing phase, while the dragon is neither
turning nor in its sleep/wake transition.

That creates an uncomfortable bargain. The head is exposed during the
part of the attack when the dragon wants to shoot back. You can learn
the sweep, aim where the head is going, and still lose the opportunity
because your projectile arrives too late. Or the head can be vulnerable
without producing a projectile at all. Its attack program and its ability
to carry out that program are separate pieces of state.

## A body in four pieces

The maze places the dragon as one authored object, but setup builds it from
four cooperating motion objects: a head and three body sections occupying
a two-by-two footprint. A motion object is the hardware's independently
positioned picture, described by a record rather than painted by the main
processor pixel by pixel.

![Dragon artwork divided into four sections](img/ch12_dragon_segments.png)

*A ROM-derived sleeping-dragon stamp with an explanatory two-by-two overlay.
The labels illustrate the four-piece construction; this is not a capture
of a moving dragon or a diagram of every head collision position.*

Most creatures can use the ordinary monster machinery with a different
picture, speed, and strength. The dragon needs additional coordination.
Its four records must agree on facing and phase, while its head has a
separately tracked position used by the shot collision test.

That last distinction matters when you aim. Opening the mouth changes
both the head artwork and the offsets used to locate it. The active target
is not simply whichever body cell a projectile first overlaps. The game
performs an additional head-overlap check and marks the collision result
when that check succeeds.

Imagine aiming at the middle of the body because it is the largest and
easiest shape to hit. The shot can collide with a dragon segment and still
fail the marked-head requirement. Now imagine shifting that aim toward
the head but firing during a closed-mouth phase. The geometry can be right
while the damage gate remains shut.

Ordinary monster strength tables do not explain either outcome. We need
to follow the dragon's own animation.

## Sixteen bytes of choreography

The active dragon selects among five programs, each sixteen bytes long.
They are small sequences of pose-and-fire instructions. A byte's lowest
bit requests fire; the remaining value, shifted right once, selects one
of four head poses.

Thus `0x04` means pose two with the mouth closed, while `0x05` means
pose two with the fire flag set. Similarly, six and seven describe the
closed and open versions of pose three. These are paired states, not
eight unrelated positions.

Here is the complete second program, numbered one by the game's
zero-based indexing:

```text
Phase index:  0  1  2  3  4  5  6  7   8  9 10 11 12 13 14 15
ROM byte:    00 02 04 06 07 05 03 01  00 02 04 06 07 05 03 01
Head pose:    0  1  2  3  3  2  1  0   0  1  2  3  3  2  1  0
Fire flag:    -  -  -  -  F  F  F  F   -  -  -  -  F  F  F  F
Counter:      0  8 16 24 32 40 48 56  64 72 80 88 96 104 112 120
```

*Bytes transcribed from the game ROM at `0x5D588–0x5D597`. The decoded
rows are an explanatory strip, not an observed playback trace.*

Normally the animation counter advances once per active update. Dividing
it by eight selects the phase, and it wraps after 128 counts. An
uninterrupted pass therefore takes about 2.13 seconds at sixty frames
per second. This program contains two identical halves, so its visible
figure repeats after sixty-four counts.

The first four phases sweep through poses zero to three without fire.
The next four return through three to zero with fire requested. The
change from phase three to four opens the mouth while retaining pose
three. The change from seven to eight closes it while retaining pose
zero. Even a repeated pose can therefore change the tactical situation.

We can give the strip a physical meaning using the upward-facing head
tables. Relative to the primary segment's position, their tracked offsets
are:

| Pose | Horizontal offset | Closed-mouth vertical offset | Open-mouth vertical offset |
|------|-------------------|------------------------------|----------------------------|
| 0 | +20 pixels | +8 pixels | +18 pixels |
| 1 | +12 pixels | +8 pixels | +18 pixels |
| 2 | +4 pixels | +8 pixels | +18 pixels |
| 3 | −4 pixels | +8 pixels | +18 pixels |

Here positive vertical values point *up*, following the ROM's coordinate
convention. These are reference-position offsets, not measurements of
the visible tip of every drawing. They show a twenty-four-pixel sideways
sweep and a ten-pixel outward extension when the mouth opens.

The tables use two related indices. The pose-related body and muzzle
lookups use `pose + facing × 2`. The head lookups use
`byte + facing × 4`, retaining the open-mouth bit. Facing takes the
cardinal values zero, two, four, and six. Keeping that extra bit gives
every pose a distinct closed/open pair of head pictures and offsets.

The result is more expressive than moving one large rectangle. The body
can remain a useful landmark while the point you must hit sweeps across
it and extends toward you.

## A fire phase does not reserve a fireball

The dragon has no private stock of projectile records. It shares four
channels with ordinary demon fireballs: motion-object slots five through
eight. Lobber projectiles use different reservations and do not fill
these four.

At a firing opportunity, the dragon needs an eligible selected player,
a zero fire cooldown, and a free shared channel. The allocator searches
slots eight down through five. Only a successful allocation followed by
projectile setup reloads the cooldown to eight.

Suppose three channels already contain demon fireballs and slot eight
is free. The dragon can put its shot there. Suppose all four are occupied
instead. The fire request produces nothing, although the path byte still
has its fire flag.

The vulnerable-head test reads that flag, not the allocator's success.
A head in the right phase can accept a hit while outgoing fire is blocked
by the crowd's existing projectiles. You should not need to see a newly
created flame to know that a shot can count.

The ordinary sweep offers firing work at eight-count phase boundaries,
not on every intervening update. Advancing the unlocked path also clears
the cooldown. Its regular rhythm therefore comes mainly from the phase
cadence; it is not an eight-frame cooldown stacked on top of each
eight-frame phase.

For example, imagine reaching counter 40, an open phase, while all four
channels are occupied. The attempt fails. If a channel becomes free two
updates later, the ordinary sweep does not immediately fire into it:
counter 42 is not a phase boundary. The next opportunity in this program
is counter 48. Meanwhile the fire flag remains set.

At close range, the dragon can stop advancing at an open phase. That
changes the cooldown's job. Now it has to space repeated firing attempts
while the head remains in place.

## Close is not the same as aligned

Target selection records a player's identity, a cardinal direction, and
distance along that direction in sixteen-pixel cells. A selected player
within three cells ahead selects the large breath branch rather than
the distant fireball.

The larger projectile occupies three-by-three graphics tiles, compared
with the fireball's two-by-two. Its state also selects the strongest
monster-shot tier, the large collision box, its own animation sequence,
and movement on even frames. The danger is not just a fireball drawn
larger.

Sustaining it requires another test. The dragon must face the selected
direction, and its calculated muzzle must line up across the other axis.
For an upward- or downward-facing dragon, the signed horizontal error
must be strictly greater than −17 and less than +18 pixels. For a
left- or right-facing dragon, the vertical error must lie strictly
between −17 and +17.

Consider these invented local arrangements for a right-facing dragon.
The two cells immediately ahead of its footprint are L1 and L2. The
player's selected forward distance is two cells; the drawings omit the
remaining floor.

```text
OPEN APPROACH                         BLOCKED APPROACH

[ body ][ head ] L1 . player           [ body ][ head ] WALL . player
[ body ][ body ] L2 . .                [ body ][ body ] L2   . .

L1 and L2 usable;                     The leading wall rejects this
player aligned with muzzle.           player as a target candidate.
```

*Schematic footprints and relationships, not literal sprite coordinates.
“Aligned” means a zero cross-axis muzzle error in this example.*

With a published target, clear leading cells, and zero error, the close
lock can hold an open phase and sustain flame. Move the player to a
vertical error of twenty-four pixels, while keeping an otherwise legal
nearby target, and the alignment test fails. Close distance can still
select a large breath when a shot is created; it does not by itself
hold the head there indefinitely.

In the second drawing, the solid leading-wall marker is rejected earlier.
The target chooser probes both cells and skips the candidate if either
contains the wall picture `0x8000`. It does this before publishing that
player's direction and distance. If no other player qualifies, there is
no selected target for the firing gate.

This is not a complete ray cast proving that every cell between dragon
and player is clear. It is a specific test of the leading footprint.
Its consequence is nevertheless stronger than merely preventing the body
from moving: it can prevent a nearby, apparently aligned hero from
activating the close-range attack state.

## Holding the mouth open

The locked state lets a fire byte at a phase boundary retain its counter
instead of advancing. The cooldown decreases during subsequent eligible
dragon updates, and a new shot becomes possible when it reaches zero.

Here is a constructed timeline at program one's phase four, byte seven.
Assume a stable close aligned target, no turning, no incoming hits, and
the channel availability stated in the table. Update zero is a firing
boundary, not the beginning of the whole encounter.

| Relative update | Head state | Cooldown when fire is checked | Shared channels and result |
|-----------------|------------|------------------------------|----------------------------|
| 0 | Pose 3, open; counter 32 held | 0 | Slot 8 free: fire, reload to 8 |
| 1–7 | Same open pose | 7 down to 1 | No allocation attempt |
| 8 | Same open pose | 0 | All four occupied: no new shot |
| 9 | Same open pose | 0 | Slot 6 now free: fire, reload to 8 |
| 10–16 | Same open pose | 7 down to 1 | No allocation attempt |
| 17 | Same open pose | 0 | A free channel permits another shot |

*A conditional timeline derived from the update order, not a captured
sequence. Channel lifetimes depend on the projectiles' actual collisions
and animation.*

At update eight, the failed allocation does not restart the cooldown.
At nine, the held phase can try again. That is different from the
unlocked counter-42 example, which had to wait for another boundary.

Every row retains the fire flag and therefore the phase component of
vulnerability. That does not guarantee a player's shot hits the head;
it means the dragon's own missing shot is not an immunity period.
Stepping out of alignment can release the lock, allowing the sweep and
its closed phases to continue.

## Landing a hit changes the future

Now follow one accepted player shot. First the collision machinery
recognizes overlap with the separately tracked head and marks the
candidate. The damage handler requires that marked result, rejects
sleeping/waking or turning state, and checks the current program byte's
fire bit.

Passing those gates plays the distinctive dragon-hit sound and increments
the hit count by one. The ordinary distinction between one-point and
two-point player weapons does not turn an accepted dragon hit into two.
This encounter requires nine accepted hits.

Before the ninth, each hit also selects a program with a random draw
from zero through four. The program can happen to be the same one.
Starting a different sequence at its first byte, however, could abruptly
close the mouth or shift the head across the body.

Instead the routine searches for the *same complete byte*, not merely
the same pose number. It preserves the fire bit as well as the pose.
It begins at phase zero of the selected program and advances eight
counter units at a time until it finds the match. If necessary it
continues into the next program.

Take an accepted hit at program one's phase five: byte `05`, pose two
with the mouth open. Suppose the random selection chooses program zero.
Its complete sequence is:

```text
00 01 00 02 04 06 07 06 04 02 03 02 04 05 04 02
```

The first `05` is at index thirteen. The new animation counter becomes
`13 × 8 = 104`. The head retains pose two and its open-mouth offset, but
the next phase is now `04`, the closed version of that pose. Had the old
program continued, its next byte would have been `03`, open pose one.

A hit has therefore changed the coming opportunity without making the
current head jump. If close lock is still holding the phase, advancement
waits for that lock to release; the matching operation itself does not
promise an immediate move to the next byte.

The visible color changes provide a slower measure of progress:

| Accepted hits so far | Palette selected after the hit |
|----------------------|--------------------------------|
| 1–2 | 8 |
| 3–5 | 7 |
| 6–8 | 6 |
| 9 | Dragon removed; rewards created |

For the surviving hits, the rule is
`5 + floor((11 - hits) / 3)`. The three palette bands darken the dragon
as damage accumulates. They are not three ordinary monster strength
tiers: the private hit count still determines the ninth-hit finish.

## A potion is an interruption, not nine free shots

The sleeping dragon reacts to entry into a surrounding ten-by-ten-cell
region. Movement supplies previous and current cells, allowing the game
to distinguish entering from merely remaining nearby. A new entrance
starts a forty-nine-frame wake transition. Staying inside does not keep
restarting it.

Potion magic has a separate dragon branch. It checks all four pieces
against the wider near-screen region. An eligible active dragon gains
a stun flag, freezing its active path, pose, and firing work. This is
not ordinary potion damage and does not subtract from the nine-hit
requirement.

Suppose you stun it at the open pose used in our timeline. The freeze
has no automatic stun countdown. That sounds like an invitation to
stand still and fire nine times, but the next shot changes the state
before damage is considered.

The dragon-shot collision path calls the proximity routine first.
Shot and interaction events supply a zero previous position, allowing
them to act as new entries rather than inheriting the player's earlier
presence. The event clears stun. Only then does the hit handler test
head overlap, transition state, and the fire flag.

The first shot can count if those conditions hold, but the dragon is
no longer stunned. If you froze a closed phase, the shot still clears
stun without making that phase vulnerable. Magic has interrupted the
attack, not created a promise about the next nine projectiles.

A second potion while it is stunned produces another result: it clears
stun, sets the sleep/wake state, and starts a counter at −49. The counter
moves toward zero as the dragon settles into sleep. Once zero is reached,
it stays asleep until another eligible event starts waking.

Magic or a proximity event during the negative transition can reverse
it by negating the remaining count. For example, reversing at −20 starts
a positive twenty-count return toward activity, not a fresh forty-nine
counts. Magic applied to the fully sleeping zero state starts the
full positive forty-nine.

A shot arriving during that transition can thus help wake the dragon
while still being rejected by the transition's damage gate. The order
matters: disturbing it and hurting it are separate operations. Potions
can buy room to reposition or leave; attacking is a decision to resume
the encounter.

## The space it leaves behind

The ninth accepted hit removes all four pieces and starts the dissolve
effect. The released footprint receives a score bag and one randomized
hidden potion.

Placement follows the facing, using two successive offsets. For a
right-facing dragon, the first offset puts the bag sixteen pixels to
the right of the primary segment's original reference position. The
second moves sixteen pixels back left from there for the hidden potion.
It is cumulative, leaving the two prizes at neighboring positions inside
the cleared footprint rather than throwing the second prize outside it.

The bag's base value becomes 2,000. Its collector's current multiplier
determines the score addition: multiplier three makes it 6,000. The
hidden potion selects one of six permanent powers. If its collector
already owns that power, the usual duplicate-pickup rules apply, including
conversion to a carried potion when there is inventory room.

Finishing the fight therefore does not decide who benefits from both
prizes. The final shooter's contribution, the player closest to the bag,
and the player who needs the power can belong to three different people.
Removing a large obstruction turns the encounter back into the familiar
problem of reaching shared resources.

Until then, watch the head rather than merely the body, and distinguish
an open phase from a successfully launched flame. The program supplies
the opportunity. Alignment, shared channels, incoming shots, and magic
decide what happens during it.

### Source notes

- [Game subsystems](../doc/04_game_subsystems.md), §§8.1–8.4, and
  [data reference](../doc/05_data_reference.md): dragon state, target
  selection, head tables, shared projectiles, and damage.
- The full programs and upward-facing offsets above were read from the
  game ROM: programs `0x5D578–0x5D5C7`, head horizontal/vertical tables
  `0x5D438/0x5D478`. Phase stepping, cooldown clearing, and held-phase
  firing follow `0x545AA–0x5473C`; free-channel scanning is `0x540E8`.
- Exact alignment comparisons are at `0x53E0E–0x53E38`; the close-range
  caller gates are `0x546F8–0x5473A`, and the leading-wall rejection is
  `0x53FE0–0x5400C`. These are specific local probes, not a claim of
  full line-of-sight searching.
- `dragon_shot_hit` (`0x54112`) compares the entire old path byte while
  searching the new program (`0x541AA–0x541E8`). The palette arithmetic
  follows at `0x541E8–0x5422A`; reward offsets are `0x5D408–0x5D427`,
  consumed by the death path ending at `0x5444A`.
- Potion transitions and shot-before-hit proximity ordering:
  [Game subsystems](../doc/04_game_subsystems.md), §4.6.1;
  potion branch `0x470D2–0x47128`, proximity routine `0x549EA`.
  [`dragon.py`](../gauntpy/src/gauntpy/game/subsystems/dragon.py) is a readable
  reconstruction, not independent evidence. The examples above are
  conditional calculations and diagrams, not new original-ROM captures.

[Previous: The thief's trail](11_the_thiefs_trail.md) |
[Contents](README.md) |
[Next: Secrets and treasure](13_secrets_and_treasure.md)
