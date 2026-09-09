# 10. The living maze

Imagine planning a route from a key to a transporter, across a forcefield,
and around a wall to an exit. You have enough health for the walk, provided
the dangerous crossing is brief. A friend follows behind. The important
complication is that the map can change while the plan is being carried out.

This illustrative route combines documented mechanics; it is not
one stored maze:

```text
P -- K -- DD -- pad A          pad B -- beam -- junction -- exit
                 |               |               |
                 +-- transport --+          alternate route
```

*Route diagram, not a scale map. P is the player, K a key, and DD a
short straight door barrier. The beam is passable but potentially
damaging; the door is a movement obstacle.*

The dungeon is not a background picture with collision painted over it.
Its cells hold live object state. Sometimes a change removes both an
obstacle and its picture. Sometimes the picture changes without making a
passage. Sometimes the picture deliberately survives after its interaction
has disappeared. A useful route needs all three distinctions.

## What one key opens

At the door, the key check turns a carried resource into shared space.
The game starts up to two opening fronts, each with a stored position
and direction. The touched section disappears, and subsequent door
updates advance the fronts through compatible neighboring sections.

On a straight run, this looks like a connected barrier unzipping.
One key can open several cells, and the friend behind you does not
need another key for the space already cleared. Monsters inherit the
opening too. Nothing in the operation reserves the new passage for
the person who paid.

But “connected” is not the algorithm. The game does not begin at the
touched cell and flood outward through every adjoining door. Each
front probes just one next cell per invocation. A vertical front
accepts vertical door pictures; a horizontal one accepts horizontal
pictures. Both accept junction pictures, with a peculiar consequence:
at a junction the front always turns left.

Consider one front travelling rightward into this illustrative junction:

```text
Before:                     After that front finishes:

          D                             .
          D                             .
front ->  J D D               cleared -> . D D

D = closed door section; J = junction; . = exposed floor
```

The front removes the junction and turns upward, its left. It can
continue along the two northern sections, but it does not create
another front to remove the eastern branch. If there is no compatible
section to the north, it stops instead of looking for a better turn.
The stored opening direction, not our interpretation of the drawn
shape, chooses the next probe.

Maze 39 makes this more than a small corner case. Its spiral contains
167 door cells. Original-ROM routine execution, starting with downward
contact from the central start, gives these results:

| Layout orientation | Door cells removed by the first key | Remaining |
|--------------------|-------------------------------------|-----------|
| Unmirrored | 52 | 115 |
| Horizontally mirrored | 31 | 136 |
| Vertically mirrored | 12 | 155 |
| Both mirrors | 67 | 100 |

These are documented executions of the door setup and opening routines,
not four claimed recordings of complete games. They isolate what the
geometry changes. Reflection moves the turns of the spiral; it does
not change “turn left” into “turn right.”

Opening removes records directly rather than reclassifying every
surviving junction after each disappearance. The program follows
small moving instructions, not the entire remaining door network.

For our short straight barrier the outcome is simpler:

```text
Before touch:   world = door, door     artwork = door sprites over floor
After opening:  world = clear, clear   artwork = the existing floor
Player:        one fewer key
```

Doors are motion objects. Removing their records exposes floor already
drawn below them. That differs from opening a wall, where changing
the logical tile can also require restamping the playfield and its
neighbors. In either case the next movement check sees an altered world.

## The pad is not the landing

At pad A, transport begins with a flash and a saved copy of the hero's
picture. The relocation phase does more than exchange two coordinates.
It works with the pad positions collected during level setup, then
looks for a usable neighboring landing cell at the destination.

The live joystick direction participates in this search. The routine
rotates through an eight-direction table, testing alternatives, rather
than assuming the first proposed position must remain available.
Somebody may have moved since the transport began.

Suppose the neighborhood of pad B contains these candidates:

| Proposed landing | Result relevant to this example |
|------------------|---------------------------------|
| Solid wall marker | Rejected |
| Another hero | Rejected |
| Closed door, after we spent our only key | Rejected |
| Clear floor | Can be accepted |

This is a list of tests, not their search priority. The destination
checker also excludes a dragon, locked treasure, and the transporter
object itself. Arrival beside a pad is not permission to replace the pad.

Occupancy alone is not the test. The checker accepts ordinary empty
floor, and some occupied destinations are deliberately usable. For an
accepted monster or item, the relocation path removes the old player
record, resolves the destination interaction, clears a surviving
ordinary occupant where required, and recreates the hero at the landing.
Another player's body is protected in a way an ordinary monster is not.

If another player opened the door beside pad B before our arrival,
the same coordinate may now be clear. The transporter depends on the
live maze, not just its stored layout.

Transportability, the temporary power, adds corner-squeeze routes of
its own. That path can clear many wall markers at a selected landing
before the final destination check; it preserves forcefield hubs and
has its own boundary restrictions. It should not be confused with
ordinary pad travel or generalized into permission to teleport anywhere.

Once relocation succeeds, the arrival effect moves to the destination
and the hero's picture is restored as the transition completes.
If this hero is the thief's selected victim, the game also records
transport-route information. Crossing space discontinuously need not
break a pursuer's trail. We will follow that consequence next chapter.

## A crossing paid for by the frame

Beyond pad B the forcefield flashes. It does not stop movement like
a locked door. Its danger comes from a separate contact check, beginning
with the live field-color word. Zero means the field is dark, and
the damage branch is skipped.

While lit, each qualifying frame of contact charges health:

| Character | Health per contact frame | With extra armor |
|-----------|--------------------------|------------------|
| Warrior | 2 | 1 |
| Valkyrie | 2 | 1 |
| Wizard | 6 | 5 |
| Elf | 4 | 3 |

For an illustrative six-frame exposure, a Wizard loses 36 health, or
30 with extra armor. A Valkyrie loses 12, or 6 with extra armor.
This calculation isolates forcefield damage: six successful contact
checks while lit, sufficient starting health, and no other damage
or exceptional state. The forcefield branch also skips players with
an active acid timer.

Armor does not change a Wizard's six into the Valkyrie's two.
It selects the second half of a character-indexed table, reducing
each entry by one. Character, crossing duration, and phase all matter.

The hurt flash is not an invulnerability interval that makes continued
contact free. Each damaging update reloads its feedback state. Remaining
in the beam keeps charging health while the checks qualify.

Darkness is therefore tactical information, not merely decorative
flicker. The field's phase program alternates lit and dark steps, with
each duration formed from a table value plus a random zero through
seven. You can wait for a safe phase without assuming every previous
interval predicts the next exactly.

Our diagram now has two different kinds of change:

```text
After the door:      DD -> ..       collision obstacle removed
After transport:    P near A -> P near B; pads remain
Field darkens:      lit -> dark    damage disabled; route was already passable
```

Waiting costs ordinary health over time and may invite monsters closer.
Rushing through a lit field spends health faster. Each choice has a price.

## The junction closes behind us

Suppose the direct route beyond the field belongs to a cyclic-wall
group. While we make the crossing, the groups advance:

```text
Before the cycle:                After the cycle:

beam -- . -- exit               beam -- W -- exit
        |                              |
        W -- alternate path            . -- alternate path

W = wall; . = clear participating cell
```

*Illustrative phase change, assuming the incoming wall's cell is empty.*

Cyclic walls carry one of three group assignments. On an update,
the outgoing group's existing walls disappear, while the incoming
group's cells receive walls only where the live picture is empty.
The assignment survives the open interval so the cell can participate
again later.

The rhythm is roughly two seconds. More precisely, the routine reloads
its countdown to 120 but tests the value from before decrementing:
consecutive updates are 121 eligible calls apart. Its level flag
must be enabled and at least one player must have a nonzero motion-object
slot. This is scheduled world work, not an independent wall clock.

The empty-cell test gives the diagram an important qualification.
If a hero or another object occupies the incoming cell, the routine
does not overwrite that record with a wall. A learned phase schedule
predicts what the game will attempt, while occupancy determines which
placements it can complete.

A floor trigger changes the maze by a different rule. Stepping on it
replaces the trigger with floor and removes the corresponding wall
family. This can open sections far from the triggering cell. The
local-trap flag restricts the conversion to the applicable near-screen
region; without that restriction the scan reaches matching cells
throughout the maze.

Some setup flags remove one or two such families before play, and
randomized trap setup rotates the trigger identities by a common
offset. These operations work on related group labels, but they are
not the recurring cyclic-wall clock.

Random walls offer a third behavior. Each participating cell gets a
bounded draw from zero through thirty-one; values above fifteen toggle
its wall picture. Each test thus has a one-half chance of changing
that cell. The scan has its own countdown and cursor. There is no
three-group itinerary to memorize.

Finally, invisible-wall flags hide artwork without removing the
underlying obstruction. Watch what changes: group membership, current
occupancy, or only visibility. An apparent opening may be no opening at all.

## Make a passage, or uncover a risk

Some walls respond directly to the player. Pushing a movable wall
requires a usable destination for the wall, not merely a desire to
occupy its current position. A successful push relocates the obstacle;
it can open one passage while blocking another.

Shooting offers a slower alternative. Each player hit adds one count
to the movable wall's state. At twenty-five hits it dissolves. The
ROM adds `0x0400` per hit and compares against `0x6400`, twenty-five
such increments. This is a hit count, not the ordinary monster's
character-dependent damage calculation.

That reconnects terrain to Chapter 2's shot reservation. Twenty-five
required collisions can take very different amounts of time depending
on flight distance and interruptions. The wall does not become easier
to remove merely because a stronger ordinary projectile hits it.

Destructible walls instead use the crumble routine and shot damage.
Their remaining state is reflected in changing playfield descriptors
or palette-related stages, depending on the wall artwork family.
A wall can visibly weaken while remaining a collision obstacle.
Strong projectile and reflecting-shot paths also distinguish removing
the obstruction from letting the shot continue or bounce: a surviving
shot still occupies its player's reservation.

A secret wall conceals a different transaction. Shooting it open
reveals the cell, then draws a possible occupant. In normal play the
draw is zero through fifteen, accepted only below
`2 × active players + 2`.

| Draw, if accepted | What appears |
|-------------------|--------------|
| 0–1 | Death |
| 2–3 | Treasure bag |
| 4 or 8 | Shot-resistant potion |
| 5 or 7 | Shot-resistant food |
| 6 or 9 | Hidden potion upgrade |

With one player, only draws zero through three qualify. The wall
produces Death in two of sixteen cases, a treasure bag in two, and
nothing in twelve. With four players, zero through nine qualify:
Death still occupies two cases, useful objects eight, and nothing six.

The larger party improves the chance of a useful discovery from
one-eighth to one-half without removing the one-eighth chance of Death.
The wall is a route change with a possible new occupant, not a guaranteed reward.

## Which exit are we reaching?

Return to our planned exit. It may no longer be there. A moving exit
travels among the exit positions collected during setup rather than
being planted on arbitrary random floor.

The position count selects a step from a ROM table. With five recorded
positions, the step is three. Starting at table index zero, the index
arithmetic gives `0, 3, 1, 4, 2, 0`, reducing each addition modulo
five. These are illustrative table indices, not coordinates in one
particular maze, and live destination handling still matters.

The old and new cells run complementary eight-step artwork sequences.
The exit rests for 300 frames between relocations, and a sound marks
the movement. Remembering the candidate sites is useful in a way that
memorizing one current exit coordinate is not.

Choose-one-exit setup is different again. It selects a genuine exit
from the recorded possibilities; with the fake-exit rule, the losing
sites can retain indistinguishable exit artwork.

Touching a fake does not begin the player's departure. The game
removes its interaction marker and can deliver its warning, but does
not redraw the underlying playfield:

```text
                    Before touch              After touch
Genuine exit:       live exit + exit art       player starts leaving
Fake exit:          fake marker + exit art     marker gone + SAME exit art
```

One more glance does not undo the deception.

A genuine exit plays that player's exit sound, creates the departure
animation, and changes the player's state. The whole level does not
vanish while a friend remains inside. Our route is an escape for one
hero before it is a transition for the party.

Wraparound offers another way to revise the route. On a horizontally
wrapping maze with clear seam cells, row 12, column 31 can lead
across to column 0 and onward to column 1. In packed cell numbers,
that is 415 to 384 to 385, not 415 to the next row's 416.
This is an illustrative horizontal route, deliberately away from
the reserved top row.

The seam joins neighborhoods; it does not exempt the landing cell
from collision or abolish the shared camera's constraints. If the
cell across it contains a closed door, the wrap has brought us to
another door, not carried us through one.

## When the game opens a way

Two timers can eventually alter a stalled maze, but neither simply
asks how long the joystick has been untouched.

Both advance in the post-player-loop block only when at least one
player reached the normal-game input-processing path that frame.
The counter enabling that block is incremented when normal input
is read, regardless of whether its direction is neutral. Demo input
does not increment it. A player still in a transport phase does not
reach it; if no other player qualifies, both timers stand still.
An instructional pause that skips world processing also supplies no
such update.

The door timer counts upward while nonnegative. The current sum of
keys carried by players processed through the relevant loop selects
its threshold:

| Keys in that sum | Open when timer is | First opening count from zero |
|------------------|--------------------|-------------------------------|
| None | Greater than 1,200 | 1,201 eligible updates |
| One or more | Greater than 2,700 | 2,701 eligible updates |

Those are approximately twenty and forty-five seconds at sixty
updates per second, provided intervening events do not reset the
timer. The comparison is strictly greater, and the key condition is
read again rather than chosen permanently on level entry.

When it fires, the sweep removes the live horizontal and vertical
door types throughout the maze. It does not follow the two-front,
left-turn procedure used by a key. A stubborn remainder of a spiral
can therefore disappear in this sweep.

The timer then becomes `0xFFFF`, or minus one as a signed word,
disabling further increments. Ordinary positive-timer resets do not
rearm that sentinel. The common level-start tail clears it for the
next level; first-player placement also has a clearing path.

The separate escape timer reaches its threshold at 21,000 eligible
updates: 350 seconds, or five minutes fifty seconds at the nominal
rate. It is not a “since last injury” stopwatch. Tile interactions
and combat have explicit reset sites: collecting supplies, relevant
trap interactions, successful melee work, generator damage, and
various destruction paths can interrupt the accumulation. The two
timers do not have identical reset sets.

Walking over empty floor does not itself reset them. Nor is merely
holding Fire the post-loop test. “Idle” is a convenient name for
state whose exact meaning comes from the events that clear it.

At the escape threshold, the game converts eligible wall markers
and movable-wall pictures into exits, excluding forcefield hubs.
It clears the escape counter and disables cyclic walls and moving
exits so those systems do not immediately rearrange the result.
These are newly installed exit objects, not secret exits that were
always present in the compressed map.

Our original route may now be unnecessary. We spent a key to remove
an obstacle, accepted a checked transport destination, priced a
forcefield crossing, and adapted to changing walls. The final escape
mechanism can change the objective's location itself. The maze is
a live collection of agreements about movement, damage, and
interaction—and the game can revise each agreement separately.

### Source notes

- [Game subsystems](../doc/04_game_subsystems.md), §§4.6, 7, 12,
  18–19, 23.4, and 26: terrain, transport, exits, and wall interactions.
  Maze-39 counts are the documented original-ROM door-routine results,
  not new full-game captures.
- Direct instruction checks: `tport_check_dest` (`0x50ADE–0x50B86`)
  rejects picture `0x8000` and picture `0x0001`, not ordinary zero
  pictures; object types `0x2F`, `0x3C`, and `0x3E` are locked
  treasure, dragon, and transporter. Doors require a key.
- Forcefield contact (`0x4AA42–0x4AB06`) and its eight longwords at
  `0x5813C`: color gate, acid gate, character/armor indexing, and costs.
  Movable-wall counting is at `0x4B448–0x4B496`; secret-wall selection
  at `0x4B560–0x4B5FC`; `wall_crumble` starts at `0x5303A`.
- Exit movement reads `exit_rotation_offset_by_count` at `0x5B7FC`;
  its count-five entry is three.
  [Data reference](../doc/05_data_reference.md) describes this table
  and the persistent per-level fields.
- Exact timer ownership follows `0x4A8B4` and `0x4ACD4–0x4AD3C`,
  `open_timed_doors` (`0x47FAC`), level rearming (`0x4836A`), and
  first-player placement (`0x48A88–0x48AA0`). The escape threshold is
  the ROM's `0x5208`; `maze_convert_walls_to_exits`
  (`0x5E80C`) supplies its eligibility rules.

[Previous: The next maze](09_mazes_and_slapstic.md) |
[Contents](README.md) |
[Next: The thief's trail](11_the_thiefs_trail.md)
