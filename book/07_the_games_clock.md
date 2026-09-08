# 7. The game's clock

In a busy room, a player moves, an arrow strikes, the camera glides, a
generator produces a monster, and a warning comes from the speaker.
These appear simultaneous. On the main CPU they are ordered work.
What does that order mean for the person holding the joystick?

The game repeats a frame body containing twenty-eight calls, with one
initializer executed before the repetition begins. The calls are not
twenty-eight equal slices of time. Some finish almost immediately;
others inspect a crowd or handle four players. Together they are the
sequence through which one game update becomes the next.

## Where does a frame begin?

A CRT monitor draws the image as horizontal scanlines. After the visible
field, the beam returns for the next one during **vertical blanking**,
or VBLANK. The video hardware generates an interrupt at this cadence, briefly
handing control to a special routine.

The game's VBLANK handler publishes display-related changes and sets a
flag in working memory. The main loop waits for that flag, increments
its frame counter, clears the flag, and performs its work. Normally this
happens about sixty times a second. A countdown stored as sixty frames
then lasts about a second, without consulting a clock measured in seconds.

VBLANK is not a magical instant in which every monster moves together.
It supplies the rhythm. The main loop supplies the ordered changes.

## Which action gets there first?

Before the world update, the game services logo colors, samples controls,
and checks coins. The controls are electrical switch readings: a pressed
switch reads zero. It preserves those raw inputs while also shifting the
Fire and Magic button samples into short histories. Those histories let
button-sensitive routines distinguish a settled press or new edge from
unreliable contact changes.

When gameplay is allowed, the order starts with transporter and forcefield
cycling, then potions, doors, existing shots, and players. Camera movement
follows the players; ordinary monsters follow the camera. Dragon, thief,
health, treasure timing, Death/forcefield sounds, exit motion, and moving
walls occupy the rest of this sixteen-call group.

Consider a stunned hero pressing Magic while holding a potion. Potion
handling runs before player movement and does not check the movement-stun
timer. The potion can therefore work while the hero remains unable to
walk. Later, the monster pass recognizes the potion event and processes
its effects instead of doing ordinary monster movement. Surviving targets
do not also get a normal move on that potion frame.

The camera order matters too. It considers positions after player movement,
and the following monster work uses the updated viewing window. “What is
happening nearby?” is answered at a particular point in the sequence, not
from an imaginary simultaneous snapshot.

## Why does a message stop monsters but not coins?

Between the first three calls and the sixteen gameplay calls is one test:
is the dialog timer active? If so, the loop skips the entire gameplay
group. Shots hang, players stop, monsters stop, and the ordinary health
countdown does not run.

```text
VBLANK flag
    |
colors -> controls -> coins
    |
dialog active? --- yes --------------------.
    | no                                  |
sixteen gameplay calls                    |
    |                                     |
    '-------------------------------------'
    |
message timer -> selection/join -> scores -> attract -> persistence/sound
    |
check whether another VBLANK arrived
```

*The bypass rejoins before the message timer. That timer can remove the
very dialog which kept the world from advancing; coins and sound lie
outside the frozen group.*

The message itself continues counting down, new money can be recognized,
and speech can continue through the separate sound computer. When the
timer reaches zero, the next pass can admit gameplay again. The gate is
tested once before the group, so a dialog opened during gameplay does
not rewind work already done in that frame.

The same main loop also serves the title, scores, and demonstration.
Individual routines inspect the current mode before doing their own
work. Being called does not necessarily mean moving something.

## What if there is too much to do?

At the end, the loop examines the VBLANK flag again. If it is already set,
another field arrived before the work finished. The game records an
overflow signal. Successful later frames repeatedly halve that signal
until it disappears.

While it remains nonzero, generator probability is forced to zero.
Outgoing sound-queue dispatch also defers work under overflow. These
responses reduce additional load; they do not guarantee that a crowded
frame will fit or turn missed time into completed simulation.

The display hardware continues its own rhythm, while the game can
temporarily advance more slowly. A newly empty square and an available
generator turn are therefore not the whole story behind the next
monster's arrival. The game must also have caught up with its clock.

## For the full chapter

Trace a single Fire press through the shot and player calls on successive
frames, then contrast a dialog opened before the gameplay gate with one
opened inside it. Expand the diagram into a numbered twenty-eight-call
strip without letting it replace the narrative. Show one missed VBLANK
and the overflow decay alongside generator attempts and sound dispatch.

## Source notes

- [Game ROM structure](../doc/03_game_rom_structure.md), §§2.1–2.4:
  initializer, exact twenty-eight-call frame order, dialog gate, and
  overflow test in `g2mainloop` at `0x42A66`.
- [Game subsystems](../doc/04_game_subsystems.md), §§4.6.1, 11.2, 15,
  and 21: potion timing, sound deferral, button histories, and the
  Death/forcefield sound service.
- [Python main loop](../gauntpy/src/gauntpy/mainloop.py) presents the
  reconstructed sequence as readable calls. It is explanatory
  implementation evidence; the ROM-backed call sequence supplies the
  arcade ordering.

[Previous: A world in ten bytes](06_a_world_in_ten_bytes.md) |
[Contents](README.md) |
[Next: What a quarter buys](08_what_a_quarter_buys.md)
