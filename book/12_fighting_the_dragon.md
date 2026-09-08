# 12. Fighting the dragon

A shot reaches the dragon and disappears in an impact. Another shot, aimed
at nearly the same place, produces the distinctive hit response. If both
looked accurate, why did only one count?

The encounter joins two moving targets: the head's position and its moment
of vulnerability. Hitting a large red shape is not enough. A successful
shot must find the head during a firing phase, while the dragon is neither
turning nor in its sleep/wake transition.

## A body in four pieces

The maze places the dragon as one authored object, but setup builds it from
four cooperating motion objects: a head and three body sections occupying a
two-by-two footprint. Ordinary monsters mostly fit the shared creature
machinery. The dragon keeps private state to coordinate these pieces.

![The dragon's four motion-object pieces](img/ch12_dragon_segments.png)

The separate head matters because its visible position can extend away from
the body. Tables choose its picture and offset from the current facing and
animation state. Mouth-open and mouth-closed pictures are distinct entries,
with different offsets. The damage check consequently uses separately
tracked head coordinates, rather than treating every body section as an
equally good target.

A sleeping dragon wakes when a movement or interaction event enters its
surrounding proximity region. The wake transition takes 49 frames. Merely
remaining in the region does not continually restart that entrance event.
Once active, it chooses among five small head programs.

## The attack is a program, not just a picture

Each program contains sixteen bytes. A byte specifies a head pose and
whether that phase requests fire. The program normally advances one byte
every eight frames, completing a pass in a little over two seconds.

One program provides a clear example. Its head moves through poses zero,
one, two, three without firing, then returns through three, two, one, zero
with the fire flag set. That figure occurs twice in the sixteen-byte
sequence. The visible sweep and the opportunities to attack are related
because the same program supplies both.

A fire flag requests a shot; it does not guarantee one. The dragon needs a
selected target, an expired cooldown, and a free projectile channel.
Successful firing reloads an eight-frame cooldown. The four available
channels are shared with ordinary demon fireballs, so other enemies can
occupy capacity the dragon would otherwise use.

Distance changes the attack. With a selected target within three cells
ahead, the dragon uses the larger close-range flame instead of a distant
fireball. Sustaining that flame adds another condition: the muzzle must
line up with the target within roughly a sprite's width. The locked firing
state then holds a fire phase rather than simply letting the head sweep on.

Nearby is therefore not the same as locked on. Target selection also checks
the leading cells of the dragon's footprint; a solid wall there can reject
the candidate before its distance and direction become the target state.
Close range, usable direction, alignment, cooldown, and shared shot capacity
all contribute to the attack the player actually faces.

## Nine accepted hits

Now return to the two apparently accurate shots. The first can hit during
a closed-mouth phase and vanish without advancing the dragon's hit count.
The second can overlap the moving head during an active fire phase and
count. The fire phase remains the vulnerability test even if a shot request
is blocked by cooldown or occupied channels.

Nine accepted hits defeat the dragon. Each earlier accepted hit also changes
its program. That could make the head snap to an unrelated pose, but the
routine searches forward through the newly selected program for the pose
already being displayed. That pose is preserved while the future
attack rhythm changes. A player cannot assume that landing a hit leaves
the remainder of the old sweep intact.

The dragon's palette also changes in bands as hits accumulate, providing
visible progress before the final removal. On the ninth hit all four pieces
dissolve, and the cleared footprint receives a treasure bag and a randomly
selected hidden potion. The bag's base value becomes 2,000; its eventual
award goes through the collector's scoring rules.

Potion magic buys a different opening. If a dragon piece lies in the wider
near-screen region, a potion can stun the active dragon at its current pose.
A second clears the stun and sends it toward sleep; magic during a sleep/wake
transition can start or reverse waking. This is a separate dragon response,
not ordinary potion damage.

Most importantly, the stun is not permission to fire nine unanswered shots.
The shot path performs the proximity check before damage, and that event
clears stun. Magic can interrupt the encounter, but attacking resumes its
danger. The useful question is not “Is the dragon disabled?” but “What
state will my next action make it enter?”

### For the full chapter

- Pair one full head-program strip with its vulnerability and cooldown
  timeline, including an occupied shared projectile channel.
- Diagram two close-range positions: one aligned for sustained flame and
  one rejected by the leading-wall test.
- Show an accepted hit's pose-preserving program change and a potion/shot
  sequence through stun, wake, and renewed attack.

### Source notes

- [Game subsystems](../doc/04_game_subsystems.md), §§8.1–8.4: four-part
  state, targeting, five programs, independent head tables, shared shots,
  close flame, and accepted-hit rules.
- [Game subsystems](../doc/04_game_subsystems.md), §4.6.1: potion-specific
  stun and sleep/wake transitions, including the shot's proximity check.
- [Data reference](../doc/05_data_reference.md), dragon tables
  `0x5D428–0x5D5C7`; reward path `0x54418` is described in
  [game subsystems](../doc/04_game_subsystems.md), §4.6.

[Previous: The thief's trail](11_the_thiefs_trail.md) |
[Contents](README.md) |
[Next: Secrets and treasure](13_secrets_and_treasure.md)
