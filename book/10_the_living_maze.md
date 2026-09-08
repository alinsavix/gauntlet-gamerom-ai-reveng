# 10. The living maze

Imagine planning a route from a key to a transporter, across a forcefield,
and around a wall to an exit. The route below combines documented mechanics
to explain them; it is not a claim that one stored maze contains this exact
journey. The important complication is that the map can change while the
plan is being carried out.

The dungeon is not a background picture with collision painted over it.
Its cells hold live object state. Opening a passage changes that state;
redrawing shows the consequence. Sometimes the picture deliberately tells
you less than the collision rules know.

## Getting through is a transaction

At the first door, a key buys more than the deletion of the single cell
your hero touches. It starts up to two opening fronts, each advancing one
cell per update. A straight section continues the front along its axis.
At a junction, however, the program always turns the front left. It does
not inspect the remaining branches to choose a way around the corner. If
the next cell is not a compatible door picture, that front stops.

This makes a winding door more surprising than a connected line on a map.
Maze 39 contains a long spiral, but opening it by walking down from the
center does not remove every adjoining section. In its vertically mirrored
orientation, that first key removes only twelve of the maze's 167 door
cells. With both mirror axes applied, it removes sixty-seven. The geometry
has been reflected; the program's fixed left-turn rule has not.

The disappearance is still a real change to the shared world. The program
removes each door's motion-object record, exposing the floor already below
it; it does not temporarily allow a player to ignore a closed barrier.

That matters to the next person behind you. They inherit the opening without
paying another key for the sections already removed. It matters to creatures
too: a route that did not exist now does. Keys alter the shared world.

The transporter offers a different kind of passage. It selects among pads
recorded during setup, but a candidate must be usable. Occupancy, reserved
wall types, and adjacent-door conditions can rule one out. The flash is
therefore the visible part of a checked relocation, not a promise that
every pad always leads to one fixed destination.

If you are the thief's selected victim, transport also records route
information for the pursuer. The discontinuity that gets you across the
maze need not break its pursuit. A shortcut for the hero can become a
shortcut for the thief.

Across the destination corridor, the forcefield flickers. It does not block
movement like the door. While lit, its contact check subtracts health each
frame; while dark, that damaging branch is skipped. Character and armor
affect the cost of a bad crossing. The changing color is thus information
about a real gate in the rules. Waiting for darkness can save health,
although the phase durations include randomness and are not a perfectly
repeating metronome.

## The return route may be gone

Past the beam, suppose the direct corridor closes. Cyclic walls move among
three groups on a two-second rhythm: an outgoing group disappears and an
incoming group appears where cells remain empty. They do not simply draw
solid wall over every occupied location. Learning the rhythm helps, but
the new wall still has to fit the live world.

A floor trigger offers another way through. On trap-wall levels it removes
the matching wall family, making a distributed change rather than opening
only the neighboring tile. Some setup rules remove a family before anyone
arrives. Some hide walls instead, leaving collision where the picture offers
no warning.

Not every changing passage has a learnable cycle. Random walls periodically
make a separate coin-flip decision for each participating cell. The opening
you used earlier may close without following the cyclic groups. Route memory
remains useful, but it is a record of what was possible, not a guarantee.

Then there are walls you can negotiate with directly. Pushing a movable wall
requires space for its destination; shooting it repeatedly can eventually
remove it. Destructible walls crumble under fire. A secret wall instead
conceals a draw from a prize table when shot open. Food, potions, and treasure
are possibilities, but so is Death. More players change the odds of finding
something. Exploring the suspicious wall is consequently a decision about
risk and access, not just an obligation to collect a hidden reward.

## Reaching the exit is not always reaching safety

The exit at the end of our imagined route might have moved. Moving exits
travel among exit positions collected from the maze, using a table-driven
step; they are not dropped on arbitrary random floor. Animation and a sound
mark the relocation.

Alternatively, setup may have selected just one real exit from several.
The others can become fake exits with identical artwork. Touching a fake
does not start departure. Its interaction marker is removed, but its exit
picture remains. Looking again does not necessarily expose the deception.

Wraparound adds one more reason not to mistake the screen boundary for the
world boundary: on enabled axes, a route can continue across the maze seam.
Even a correct map needs the current geometry rules.

Finally, the game has mechanisms for stalled play. A conditional idle timer
can open doors without keys. A separate no-progress timer, reset by relevant
interactions and combat events, eventually converts eligible walls into
exits at 21,000 gameplay frames—about five minutes fifty seconds. Standing
somewhere for that much wall-clock time is not sufficient if events keep
resetting it. The escape is a consequence of accumulated inactivity, not an
exit the maze record had hidden all along.

### For the full chapter

- Draw a sequence of the illustrative route, marking changes to shared
  collision separately from changes to visible artwork.
- Explain transporter destination rejection and one usable cross-seam route.
- Compare cyclic, random, and triggered wall changes, then give the precise
  activity gates for the two late-opening timers.

### Source notes

- [Game subsystems](../doc/04_game_subsystems.md), §§4.6, 7, 12 and 18–19:
  doors and floor interactions, transporters, forcefields, moving/fake exits,
  cyclic walls, and random walls.
- [Data reference](../doc/05_data_reference.md), `idle_timer` and
  `exit_rotation_offset_by_count`: timed-door state and exit movement's
  stored-position traversal.
- `door_open_start` (`0x51E80`) and `main_open_doors` (`0x45C00`),
  [game subsystems](../doc/04_game_subsystems.md), §23.4: the fixed corner rule
  and original-ROM execution results for all four maze-39 mirror orientations.
- ROM entry points underlying the wall interactions are
  `resolve_shot_hit` (`0x4AF50`), `wall_crumble` (`0x5303A`), and
  `maze_convert_walls_to_exits` (`0x5E80C`), documented in
  [game subsystems](../doc/04_game_subsystems.md), §§18 and 26.

[Previous: The next maze](09_mazes_and_slapstic.md) |
[Contents](README.md) |
[Next: The thief's trail](11_the_thiefs_trail.md)
