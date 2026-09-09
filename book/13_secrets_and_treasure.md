# 13. Secrets and treasure

The Blue Elf is near the exit with six treasures. Across the room, the
Red Warrior has eight and can see a ninth. There are only a few seconds
left. Should the Elf wait? Should the Warrior turn back?

The treasure-room instructions have already given the important part of
the answer: `YOU MUST EXIT TO RECEIVE BONUS POINTS`. Picking things up and
getting paid for the room are separate accomplishments. The countdown
makes the distance between them matter.

This is an illustrative visit, not a replay of a recorded game. It puts
two players on opposite sides of a rule that is easy to overlook when the
floor is covered with rewards. Gauntlet II occasionally borrows the party
from its ordinary journey and asks it to play under different terms.
Treasure rooms make those terms public. Secret rooms require another
achievement before they even disclose the challenge.

## The last treasure can cost the whole bonus

Treasure visits have their own schedule. A level countdown brings one
into the ordinary journey, then reloads to three, four, or five levels.
The eleven stored rooms also have their own persistent rotation, separate
from the ordinary mazes described in [the next maze](09_mazes_and_slapstic.md).
The game saves where the ordinary journey should resume before taking
this detour.

The time allowance depends on the participating players:

| Players counted at entry | Nominal allowance |
|--------------------------|-------------------|
| 1 | 20 seconds |
| 2 | 24 seconds |
| 3 | 25 seconds |
| 4 | 26 seconds |

These come from four ROM words containing 1,200, 1,440, 1,500, and 1,560
frames. Setup adds one when installing the countdown. The displayed
seconds describe the room's allowance at the nominal sixty-frame rate,
not an independent wall clock.

More people receive more time, but not proportionally more. Four players
do not get eighty seconds. They have to collect simultaneously, sharing
passages and the scrolling view. A room with several plausible routes
can therefore be a coordination problem even without a crowd of ordinary
monsters. Thief scheduling can still operate here; “treasure room” does
not mean every other source of trouble has been switched off.

![A stored treasure-room layout rendered from ROM data](img/ch13_treasure_room.png)

*A ROM-derived layout illustration, not the two-player visit described
here. It shows the whole stored room rather than the gameplay camera's
window; the exit labels and edge arrows are explanatory annotations.*

Our Elf takes the exit. The Warrior stays for the ninth treasure and is
still inside when the timer reaches zero. The tally screen follows, but
the two players do not arrive there with equivalent records.

Exiting first puts a player into the exit animation state, numbered 8.
After that animation, status 2 means alive and waiting for the next
level. The treasure award accepts either state. Status 1, alive in the
current room, does not qualify. Timeout calls the tally routine; it does
not first promote everybody still inside to an exited state.

The award has four factors:

```text
exit bonus = 100 × counted players × player's recorded coins
                 × player's treasure-room collection count
```

For this example, give the Elf three recorded coins and the Warrior two.
At the tally, both still belong to the count: the Elf is waiting beyond
the exit and the Warrior is alive inside. The factor is therefore two,
not one merely because only one hero escaped.

| Player | Treasures | Recorded coins | Exit condition | Added room bonus |
|--------|-----------|----------------|----------------|------------------|
| Blue Elf | 6 | 3 | Exited | 100 × 2 × 3 × 6 = **3,600** |
| Red Warrior | 9 | 2 | Timed out inside | **0** |

The Warrior's arithmetic would have produced 3,600 too, had the Warrior
exited. The ninth treasure has not rescued the result. Nor would turning
eight into nine have helped if reaching the exit remained impossible.

The count is taken by the tally routine, rather than being an immutable
copy of the entry party size. Its accepted states include selecting,
alive here, exiting, and alive next. A changed party can change the
factor. The coins are the player's game-side recorded coin count, not
coins found on the treasure-room floor, raw sound-board coin reports,
or the OS's priced credit units. The collected objects supply the other
factor. This is separate from the ordinary score-multiplier competition
in [what a quarter buys](08_what_a_quarter_buys.md).

Consequently, the useful route is not necessarily the one passing the
most treasure. It is the one whose collection can still be converted
into an eligible exit. Once somebody leaves, the remaining player has
not inherited permission to ignore the deadline.

## When the voice lies about the clock

The room replaces the usual level heading with `TIME:` and updates the
large number once per second. The voice ordinarily counts down the last
ten seconds. These are two presentations of the timer, but they need not
say the same thing.

Above level thirty, the ten-second point has a one-in-sixteen gate for a
false spoken countdown. One of four stored sequences supplies five
numbers while the visible clock passes from ten through six. The game
then adds `JUST KIDDING` or `FOOLED YOU`. It has changed the speech
selection, not accelerated the countdown or moved the deadline.

That joke works because the voice is normally useful. A player trying to
watch a corridor can listen for the remaining time instead of repeatedly
looking at the panel. Here the game briefly makes that habit unreliable.
The large number remains the better reference.

Even without the joke, six seconds can trigger a warning phrase instead
of an ordinary number, with a short suppression interval for subsequent
spoken counts. The music, the number, and the warning all contribute to
urgency, but only the timer determines when the room ends.

## A task hidden inside an ordinary maze

Secret-room entry reverses the order of instruction and achievement.
First you perform something in an ordinary maze. Only then does the game
identify you as the person who earned a separate trial.

There are seventeen ordinary objectives and fourteen secret-room
challenges. They are not two names for the same table. An ordinary
objective belongs to a stored maze header; a challenge is selected after
entry has been earned.

Consider an illustrative visit to stored maze 6, whose actual header
contains objective `0x0D`, “Go On a Diet.” This is maze number 6, not a
claim that the sixth level always uses it. For the example, the
availability countdown has reached zero before this maze is set up.

That last condition is essential. Setup clears the live objective and
the winner, checks the countdown, and only then copies an eligible
header objective into the live task byte. A nonzero countdown leaves the
task unarmed. The same route, with the same restraint, can earn nothing
on a visit when that copy never happens.

The countdown and its reload value both begin at twenty. They measure
levels rather than seconds. Availability is sampled at setup, not
continually reconsidered while the players walk around. Some objectives
have additional gates: the friend-dependent final three are cancelled
for a solo player, and the dragon-related ninth objective has an early
level restriction.

For our armed dietary task, each player's progress byte starts clear.
The ordinary wholesome-food pickup path checks for task `0x0D` and
increments the eater's byte. The adaptive-food path does the same.
These are event hooks: small pieces of an otherwise ordinary pickup
operation that also notify the hidden task.

Let the Warrior eat one ordinary food while the Elf eats none. The
Warrior's byte becomes one; the Elf's remains zero. Food does not set
one party-wide “everybody failed” flag. When the Warrior exits, the
dietary check rejects that one. When the Elf exits, it accepts zero and
records the Elf as the secret-room winner.

The literal exit test deserves a closer look:

```text
for the dietary objective:
    qualify if (this player's recorded progress AND 3) == 0
```

That tests the lowest two bits, not whether the complete byte equals
zero. Four recorded pickups also pass. Moreover, the separate poisoned-food
branch bypasses the dietary increment. “Go On a Diet” is a clue, not a
complete specification of these shipped operations. Avoiding food gives
our Elf a straightforward successful path; it does not prove that every
successful path involved eating nothing.

This distinction matters elsewhere too. Four transport objectives share
`TRY TRANSPORTABILITY`, but their hooks recognize different events.
Two objectives share `WATCH WHAT YOU SHOOT`, distinguishing two food
shots from two secret-wall shots. A phrase can direct experimentation
without uniquely describing what the program counts.

The dragon task is particularly misleading if reduced to “kill the
dragon without getting hit.” It uses the same low-two-bit exit test.
Dragon fire increments the byte, while the killing shot writes two
unless it was already one. A clean killer with value two therefore
does not pass that predicate. Likewise, “Don't Hurt Friends” records a
player-shot contact before the damage and stun gates; even a harmless
contact or reflected self-hit can spoil it. The hidden rules concern
particular events and values, not an English judgment of good behavior.

## From the exit to the invitation

Recording a winner is not yet entering the challenge. The Elf still goes
through the ordinary exit sequence, first status 8 and then status 2.
The level-start routine requires both a valid winner number and that
winner's waiting-next-level status before substituting a secret layout.
The other player's failed dietary attempt has not supplied either
condition on the Elf's behalf.

The transition also changes future pacing. A valid winner increases the
reload interval by fifteen, capped at forty. Starting from twenty, our
success makes the next reload thirty-five. An armed opportunity with no
winner instead subtracts two, down to a minimum of four. The adjustment
concerns earning the invitation; it is not postponed until the entrant
wins the challenge.

There is a separate route to receiving a hint. Opening a secret wall or
making the dragon drop its hidden reward sets a discovery latch. A later
level splash consumes it to print `TO ENTER SECRET ROOM:` and a clue.
Depending on availability and the level gate, that clue can describe the
upcoming task or be selected randomly. Finding a hidden wall has thus
earned information, not automatically a secret-room visit.

For the Elf, the invitation is much less ambiguous. It names the winner
by color and character and announces `YOU HAVE PERFORMED A SECRET TRICK`.
The introductory delay is 600 frames, about ten seconds, separate from
the challenge's own allowance. The game saves the original objective,
then replaces the live task with a random code from `0x50` through `0x5D`.
The next question is no longer whether the Elf avoided food.

Suppose that draw selects `0x50`: `AFTER COLLECTING 6 TREASURES`.
Its base duration is 1,200 frames, plus a random zero through five
seconds. A draw of three supplies 1,380 frames, or twenty-three seconds.
That is a worked selection from the actual tables, not a fixed duration
for every visit.

Task `0x50` uses stored maze 115. The upper seven challenge codes use
maze 116. Neither stored layout contains an exit ready to use. Setup
reads a challenge-specific generator type, converts matching generators
into exits, and removes the other generators in the range being
transformed. For `0x50`, the chosen type is `0x2C`. Another substitution
turns selected ordinary objects into hidden potions.

The challenge therefore consists of a layout *and* a set of setup
transformations. Looking only at the compressed room would miss the
very objects that let the entrant finish.

The Elf's progress is cleared for the trial. Each relevant treasure
pickup now increments it under task `0x50`, rather than recording a
dietary violation. Six pickups produce six. At the result check, this
challenge requires exactly six, and the award separately requires exit
status 2 or 8. Leaving with five fails the qualifier; collecting six
and timing out inside fails the exit requirement.

With six and an exit, the Elf earns `5,000 × recorded coins`: 15,000
points for our three-coin player. There is no party-size or treasure-count
multiplier in that award. The six treasures establish qualification,
not a factor of six in the payout.

## Six symbols to take home

If the operator's contest option is enabled, successful completion opens
name entry. Otherwise the result returns toward ordinary play without
the contest editor. The screen asks for last name followed by first name.
The joystick changes characters, and Fire or Magic commits one; the
buffer allows twenty-nine characters, with unused positions filled by
spaces when entry times out.

For a worked example, let the Elf enter the invented name `SMITH ADA`.
Keep the saved ordinary maze at 6, original objective at `0x0D`, and
challenge at `0x50`. The resulting display is:

```text
7TP-0J6
```

The hyphen separates two visual groups, but the three symbols on either
side are not independent halves. The game interleaves name-derived
symbols with state-derived symbols.

First it skips spaces in the name and computes a sixteen-bit CRC, a
checksum built by repeatedly combining each character with a running
value. With an initial value of zero and polynomial `0x1021`, `SMITHADA`
produces `0xD21E`. The encoder exchanges the checksum bytes and retains
fifteen bits for display. Here that yields `0x1ED2`.

Split those fifteen bits into three five-bit numbers:

| Name-derived group | Numeric value | Printed symbol |
|--------------------|---------------|----------------|
| High five bits | 7 | `7` |
| Middle five bits | 22 | `P` |
| Low five bits | 18 | `J` |

The symbol table is a thirty-two-character alphabet:

```text
0123456789ABCDEFGHJKMNPQRSTUWXYZ
```

The other three symbols describe the saved state. Seven bits hold the
maze number, four hold the challenge's low nibble, and four hold the
original objective's low nibble. A nibble is simply four bits.

```text
packed state = (13 << 11) | (0 << 7) | 6
             = 0x6806

five-bit groups = 26, 0, 6
symbols         =  T, 0, 6
```

The challenge contributes zero because only the low nibble of `0x50`
is stored. Combining the groups gives:

```text
name[0] state[0] name[1] - state[1] name[2] state[2]
   7       T       P    -    0       J       6
```

Decoding reverses that arrangement. Read `T`, `0`, and `6` as 26, zero,
and six; assemble `(26 << 10) | (0 << 5) | 6` to recover `0x6806`.
Its low seven bits are maze 6. The next four are zero, identifying
challenge `0x50` within the challenge family. The upper four are thirteen,
the dietary objective. Separately recompute the submitted name's
symbols and compare them with `7`, `P`, and `J`.

This example was checked against the actual encoder instructions as
well as independently calculated checksum arithmetic. It is not a code
copied from a historical winning run.

The result page asks for an entry to Atari Games and prints
`CONTEST ENDS 12/19/86`. That is the historical deadline in this ROM,
not a current offer. The encoder alone cannot establish the complete
mailing, judging, or prize procedures.

Nor is the code cryptographic proof that somebody played the game.
Fifteen name bits cannot uniquely identify every name; spaces are
ignored, and collisions are inevitable. The state omits the player's
actions and most of the session. It even discards the original
objective's bit above the low nibble: seventeen leaves only one in that field.
Someone who knows the construction can calculate a matching code.

What the game provides is a compact, name-bound statement after its
success gates, short enough to copy from a screen. The much larger story
behind our example is absent: the Warrior's meal, the Elf's restraint,
the invitation, six treasures, and an exit reached in time. Those are
what made the six symbols an achievement for the player.

### Source notes

- Treasure scheduling and stored layouts: [maze catalog](../doc/06_maze_catalog.md),
  §3.4; durations at `0x57358`. The payout's party count, exit-state tests,
  and arithmetic are at `0x4D516–0x4D5AA`; the timeout caller is described
  in [game subsystems](../doc/04_game_subsystems.md), §16.
- Secret tasks and transitions: [game subsystems](../doc/04_game_subsystems.md),
  §10.6, and [data reference](../doc/05_data_reference.md), §3.17.
  The example follows maze 6's raw header at normalized `row10.bin`
  offset `0x0555`, setup at `0x43922–0x43958`, food branches
  `0x51B86–0x51D06`, and exit predicate `0x52BE0–0x52BFC`.
  Challenge setup and reward are at `0x44DD6`, `0x43C20`, `0x4D1A4`,
  and `0x4D720`. Hint names are not substitutes for these predicates.
- The worked code uses `secret_code_build`, `0x54BE0–0x54CA4`, the
  alphabet at `0x54CA6`, and CRC table at `0x54CC6`. Direct execution of
  those encoder instructions in a 68000-family instruction emulator
  agrees with a separate bitwise CRC calculation; this checks the
  encoder, not an entire gameplay run. Contest text survives at
  `0x5D9E8–0x5DA97`.

[Previous: Fighting the dragon](12_fighting_the_dragon.md) |
[Contents](README.md) |
[Next: A machine that speaks](14_a_machine_that_speaks.md)
