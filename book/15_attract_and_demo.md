# 15. When nobody is playing

Watch Gauntlet II from a few steps away. A hero explores a maze and
a message explains what happened. Pictures introduce creatures and
items. The game is inviting you to join while making
an unfamiliar dungeon more legible.

Scores hold for roughly ten seconds, the title for twenty-five, and
the demo for up to about two minutes. Three ten-second legend pages
complete the cycle. A mode word and countdown determine the current
presentation and when to build the next.

The four class score ladders use [score per coin](08_what_a_quarter_buys.md).
The title combines a stored background with a separately assembled
logo. Long and short motion programs give it different entrances; the
long entrance can carry the theme when attract sound is enabled.

## Is the game playing a recording?

Yes—but not a recording of pictures.

![The stored maze used by the demo](img/ch15_demo_maze.png)

*Maze 102 supplies a fixed stage containing movable walls, keys,
transporters, hazards, and other things the demonstration can encounter.*

The demo loads the maze, clears first-encounter message flags, and
joins a blue Elf. Stored control inputs replace a person's joystick
and buttons. Movement, shots, potions, collision, enemies, and the
camera still run through the engine.

A normal recording entry is only two bytes: how long to hold an input,
then which switches to hold. The switches are active low, just like
the cabinet inputs, so a cleared bit means pressed. For example,
`08 B3` means Down for eight script frames. Special records display
a caption or make another player join.

Those joins are part of what makes the demonstration interesting.
The blue Elf is later accompanied by a red Wizard and a green Warrior.
They enter through `player_join`, the same underlying operation used
for a real arrival. “Have friends join in any time” is accompanied
by a working example rather than merely printed over unrelated footage.

![The three input streams of the recorded demo](img/ch15_demo_script.png)

*This is the script clock. A span of held input measures updates to
the recording, not necessarily uninterrupted wall-clock time.*

## Why does a caption change the walk?

The caption uses the game's message-box system. While that box is
up, [the dialog gate](07_the_games_clock.md) skips the gameplay block,
including the routine that advances demo input records. The monsters
stop and the recorded stick stops counting down with them. Other work,
including the message's own countdown, continues.

Ordinary encounters can produce pauses too. The transporter advice
appears through the usual first-encounter path, while its transition
animation can continue outside the paused block. The remaining movement
in the current input record is still there when the box closes.
Text is therefore part of the demonstration's timing, not decoration
that can be removed without consequence.

A final zero-duration record parks a stream rather than rewinding it.
The attract timer remains an outside limit. If the recorded party
finishes its exit sequence first, the demo-specific handoff also ends
the screen and advances to the legend instead of loading another
playable level.

## Does it happen exactly the same way every time?

The maze, initial class and position, recordings, and captions provide
substantial repeatability. Building the demo also resets the frame
counter. But identical inputs are not enough to guarantee identical
outcomes when the surrounding state differs.

The demo shares the game's random-number stream. Level setup can
reroll hazard flags, and activity during the demonstration draws more
random values. The stream's position depends on earlier activity;
the demo setup does not establish a complete independent snapshot
of every possible influence. A recorded turn can therefore meet a
different obstruction. This is real engine execution on a prepared
stage, not a promise of frame-perfect replay from arbitrary game
history.

## What does the legend add?

The legend slows the introduction down. Its item page pairs names
with terrain and pickups. Its monster page gives a Fight/Shoot/Magic
comparison, including cases where an attack stuns rather than kills.
The final page names the people credited for the game.

Maze 103 supplies scenery, but opaque text cells hide most of it
behind the legend's black reading area. Selected transparent windows
reveal illustrations. The following score screen leaves scenery
visible between its opaque score boxes. The same display layers that
build the dungeon can build a readable explanation of it.

After a short opening interval, joystick and button inputs select
attract presentations without taking over the demo heroes. Coin entry,
or the free-play start path, instead leaves the show for character
selection. The demonstration ends where participation begins.

### For the full chapter

Follow the opening wall push, one caption, and the transporter pause
on parallel script and display timelines. Add the monster legend's
combat matrix and a small guide to the four-position attract shortcuts.

### Source notes

- Screen setup, recordings, joins, and interruption:
  [game subsystems](../doc/04_game_subsystems.md), §6;
  [ROM structure](../doc/03_game_rom_structure.md), §2.5.
- Stream records and message tables: [data reference](../doc/05_data_reference.md),
  §5.8. Dialog timing: [main-loop structure](../doc/03_game_rom_structure.md),
  §2.1. Level-flag randomization: [subsystems](../doc/04_game_subsystems.md), §5.5.

[Previous: A machine that speaks](14_a_machine_that_speaks.md) |
[Contents](README.md) |
[Next: Waking the cabinet](16_waking_the_cabinet.md)
