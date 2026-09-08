# 3. Three friends, one screen

Imagine four friends reaching a doorway together. The Elf wants to run ahead.
The Warrior is still hitting the creature in the entrance. The Wizard has a
potion, but another player wants it saved for Death. Behind them lies food that
only one hero can collect. Nobody has to select a competitive mode for these
interests to diverge.

Gauntlet II gives each player separate health, equipment, and controls, then
makes those players share space. Even the view belongs to the party. What
looks like a social problem at the cabinet often begins as a small, exact rule
inside the machine.

## What does choosing a class change?

The four heroes use the same player routines. A character number chooses
different entries in tables for walking speed, hand fighting, projectile
damage, incoming damage, and magic. Choosing a Wizard changes the numbers
those routines read, not the rules of movement or the ownership of a corridor.
Player color identifies the cabinet position; several people can choose the
same class.

The Warrior's ordinary shot deals two strength points where the Elf's deals
one. The Elf walks faster and its arrows travel faster. The Valkyrie takes less
damage from monster shots than the Wizard. These are separate advantages:
extra shot speed changes a projectile's velocity, while extra shot power
changes its damage. Neither turns the hero into another class.

Magic makes the distinction especially tangible. Consider an ordinary carried
potion used near a strong ghost generator. A Warrior's or Valkyrie's basic
magic leaves that generator unchanged. The Elf's reduces the strongest version
to its weakest tier. The Wizard's destroys it. Against ordinary ghosts, by
contrast, the Elf's basic magic destroys outright just as the Wizard's does.
“Good at magic” is therefore a collection of outcomes, not one blast-radius
number.

The game obtains those outcomes from a table selected by target type, class,
extra magic power, and whether the potion was carried or shot on the floor.
The latter uses different, generally weaker entries. Giving the next potion
to the Wizard can change what the party can remove, not merely whose inventory
icon lights up.

## Can a friend join anywhere?

A credited player can choose a class while the others continue playing.
Committing the choice asks the game to place a body. For the first hero, it
uses the starting cell remembered during maze setup. For a newcomer, it tries
the cells immediately left, right, above, and below existing heroes, accepting
an empty candidate on screen.

If everybody is boxed in, the search can fail. The game announces that it
cannot place the newcomer rather than conjuring a hero inside a monster.
Only successful placement completes the join and welcome. Clearing a little
floor can consequently be an act of hospitality. Each player position also
has its own lifecycle: a friend choosing a hero need not interrupt somebody
else fighting or entering initials.

## Why does a narrow doorway feel forgiving?

Movement is a proposal followed by a collision check. The game tries the
horizontal part first, keeping or rejecting the whole step, then tries the
vertical part from the resulting position. A diagonal request can therefore
slide along a wall when only one axis succeeds.

The hero artwork is wider than a maze cell. Collision compares the positions
of nearby objects, with adjustments for their anchors—the reference points
used to position their pictures—rather than asking whether colored pixels
touch. In tight entrances, special responses can retry with a one-pixel move
and nudge the hero away from the blocking flank. Holding toward a passage
can bring the hero onto its entry line without demanding perfect manual
alignment. That assistance does not make occupied cells empty: a friend
can still obstruct the route.

## Who owns the camera?

The camera considers the spread of eligible heroes, including its current
center in the calculation, and steers toward the middle of that extent.
It does not simply follow the fastest player. Movement toward a distant target
is limited to two pixels per axis per frame, producing a glide rather than a
succession of jumps.

Usually a hero's proposed movement must also remain inside the shared viewing
window. Run far enough ahead and the screen boundary becomes another wall.
The exact camera calculation accommodates wrapping levels and adjusts extreme
outliers, but it never supplies four independent views. The Elf's greater
speed cannot settle an argument about which way the party goes.

IT turns that spatial negotiation openly hostile. Touching the IT creature
assigns a player the curse; monster targeting gives that player priority.
The current holder can transfer it by moving into another hero, also stunning
the recipient briefly. Merely running into the holder does not perform the
reverse transfer. A doorway that was a cooperative bottleneck becomes a place
to tag somebody who has little room to dodge.

The machine tracks ownership, occupancy, and targeting. The friends must decide
whether the next collision means “let me through” or something less friendly.

## For the full chapter

Expand the doorway into a worked four-player scene with separate panels for
requested movement, accepted movement, and camera position. Add the shared
twelve-item key/potion capacity, armor and temporary powers, and the
level-dependent friendly-fire rules. A camera diagram should show the current
center participating in the extent calculation, not just a midpoint between
heroes; include a wrapped-edge example.

## Source notes

- [Game subsystems](../doc/04_game_subsystems.md), §§4.2, 4.4–4.6, 17, and 22:
  collision response, joining, IT, magic, camera, and selection.
- [Data reference](../doc/05_data_reference.md), §§5 and 8: character tables
  and `potion_effect_matrix` at `0x5DA98`. The generator example uses normal,
  carried magic, without the extra-magic upgrade.
- [Player implementation](../gauntpy/src/gauntpy/subsystems/players.py):
  a readable reconstruction of the ROM routines, useful for following movement
  and placement; the arcade claims above rest on the ROM-backed references.

[Previous: One arrow in the air](02_one_arrow.md) |
[Contents](README.md) |
[Next: A room full of monsters](04_the_horde.md)
