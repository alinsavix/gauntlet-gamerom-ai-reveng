# 13. Secrets and treasure

The treasure-room instruction contains the part a hurried player can miss:
you must exit to receive the bonus. Treasure on the floor creates a
temptation to keep collecting, while the countdown makes every extra
detour compete with getting out.

This is one kind of interruption to the ordinary dungeon. Secret rooms
offer another, but their invitation must first be earned somewhere that
looks like an ordinary level. The two diversions borrow the session, set
different terms, then return it to the continuing maze rotation.

## A room priced in seconds

Treasure visits are scheduled by a level countdown, reloaded to three
through five levels. The eleven stored rooms have their own persistent
rotation. On entry, normal progression is saved and the room receives a
time allowance based on player count: twenty seconds for one player,
twenty-four for two, twenty-five for three, and twenty-six for four.

![A stored treasure-room layout](img/ch13_treasure_room.png)

The opponent here is principally the clock, although treasure rooms are
not exempt from thief scheduling. Each player's take is counted, and the
post-room screen awards qualifying exiters 100 points multiplied by the
player-count factor, their recorded coins, and their collected treasures.
For example, with a two-player factor, three recorded coins, and six
treasures, the bonus is 3,600. It is its own calculation, not the ordinary
treasure-multiplier contest.

If time expires, the room still ends and the tally screen still appears.
That does not make a player who stayed inside eligible for the exit bonus.
The apparent choice between one last treasure and the exit has a real
penalty; the transition screen is not proof that everyone was paid.

The voice can complicate the decision. Above level thirty, a one-in-sixteen
gate at ten seconds can select a deliberately scrambled spoken countdown.
It follows the false sequence with `JUST KIDDING` or `FOOLED YOU`. The
displayed time remains the useful reference: the joke changes the speech,
not the room's deadline.

## Earning an invitation without seeing the checklist

Normal rotation mazes store one of seventeen hidden objectives. Having an
objective in the record does not mean it is active on every visit. Setup
samples a level-based pacing counter and arms an eligible objective only
when the counter permits it. Multiplayer-dependent objectives are also
cancelled in solo play.

When armed, the task listens to ordinary play. A no-food objective records
eating; shooting objectives count relevant impacts; a transport trick can
name a winner at the movement that completes it. Progress and violations
belong to individual players, so one hero's restraint need not be spoiled
by somebody else's meal.

Imagine a player avoiding every food pickup while fighting toward the exit.
That can satisfy the armed no-food task, but doing the same thing in a maze
where availability was not armed earns no invitation. The action alone is
not a universal password.

The hints are less specific than the rules. Several transport
objectives share `TRY TRANSPORTABILITY`; two different shooting objectives
share `WATCH WHAT YOU SHOOT`. Discovering a secret wall or defeating the
dragon sets a hint latch for a later transition screen, rather than
automatically awarding a room. Successful invitations push the next
opportunity farther away; missed armed opportunities shorten the interval.

The room itself adds a second task. Fourteen challenge codes select between
two stored layouts, supply time limits, and sometimes demand a qualifier
such as collecting six treasures or using five distinct transporters.
Setup turns selected generators into exits: the stored layouts alone
contain no way out. The winning entrant must satisfy the selected
condition and reach an exit to earn the 5,000-points-per-coin reward.

## A message meant to leave the arcade

With the operator's contest option enabled, successful completion opens
name entry and produces a six-character code displayed as `XXX-XXX`.
The result page asks for a contest entry to Atari Games and explicitly
says `CONTEST ENDS 12/19/86`. That is the historical deadline printed in
this ROM, not a present-day offer.

The code joins two kinds of information. Three symbols come from a
space-insensitive checksum of the entered name. Three encode the saved
maze, challenge, and low four bits of the original objective. Interleaving
them produces the short printable result.

An adjudicator with a name and code could check that the name-derived
symbols agree and decode the embedded game state. The game issues the
code after its success gates, but the code is not a cryptographic record
of the entire run. It does not preserve every action, uniquely identify a
person, or even retain every bit of the objective number. What leaves the
arcade is a compact name-bound claim about a particular secret-room
achievement—small enough to copy from a screen and send by post.

### For the full chapter

- Follow two treasure-room players to different outcomes: one exits and
  receives a tally, while one times out holding more treasure.
- Trace one armed objective through its progress writes, exit check, and
  challenge qualifier; explain clue/predicate differences with care.
- Decode one six-symbol example alongside the ROM's contest page, separating
  encoded state, name consistency, and claims the code cannot establish.

### Source notes

- [Game subsystems](../doc/04_game_subsystems.md), §§10.5–10.6 and 16:
  exit-gated payouts, secret availability and qualification, treasure timer,
  and false spoken countdowns. Treasure durations are at `0x57358`;
  tally eligibility and arithmetic at `0x4D552–0x4D5AA`.
- [Maze catalog](../doc/06_maze_catalog.md), §§3 and 7: stored treasure
  and secret layouts and normal-maze objectives. The fourteen challenges
  are distinct from the seventeen invitation objectives.
- [Data reference](../doc/05_data_reference.md), `secretcode_text_recs`
  (`0x5D9E8–0x5DA97`): the ROM's contest address and deadline text;
  `secret_code_alphabet` and CRC table (`0x54CA6`, `0x54CC6`), together
  with `secret_code_build` (`0x54BE0`), document the code's construction.

[Previous: Fighting the dragon](12_fighting_the_dragon.md) |
[Contents](README.md) |
[Next: A machine that speaks](14_a_machine_that_speaks.md)
