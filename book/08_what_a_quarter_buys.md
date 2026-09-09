# 8. What a quarter buys

The Red Valkyrie has enough health to reach the exit, probably. There is
food down a side corridor, but a generator is filling that corridor with
ghosts. The Blue Elf wants to leave. Another coin would remove the
immediate worry without requiring either player to fight for the meal.

Which purchase is cheaper: food bought with time and danger, or health
bought at the coin slot?

This is an illustrative choice, but the game gives it unusually concrete
terms. Money, injury, food, and waiting all change the same health balance.
There is no separate stock of lives protecting that balance from the
cost of simply remaining in the dungeon.

The transaction also reaches beyond health. Another paid unit changes
the denominator used to judge a score, and it can reduce an accumulated
adjustment to future monster generation. We can follow a coin without
leaving the decisions that made somebody insert it.

## What actually arrives from the coin slot

The coin switches connect to the sound board, not to the main processor's
player-control ports. The game learns about them through a status exchange.
During VBLANK service, the main side requests status with sound command
3. A reply from the sound computer arrives through an interrupt and is
saved for comparison with the previous reply.

The reply packs four small counters into one byte, two bits per channel.
Each counter can hold zero through three before wrapping. The OS computes
the change modulo four. A transition from three to zero therefore means
one new event, not that three coins have disappeared:

```text
(current + 4 - previous) & 3
(0       + 4 - 3)        & 3 = 1
```

A difference greater than one is rejected by this decoder. These tiny
counters are part of a repeatedly serviced communication protocol, not
a permanent record of the contents of the coin box.

The next step applies pricing. Operator settings determine how physical
coin events become units of credit, how many units form a chargeable
group, and whether accumulated events earn bonus credit. The OS keeps
ordinary credit balances and pending bonus units separately. A helper
can move enough pending units into a balance to complete a group before
the game attempts to deduct it.

That separates three things that are easy to call simply "coins":

| Stage | What it records |
|-------|-----------------|
| Sound-board report | Recent physical switch events |
| OS credit accounting | Priced units available to spend, including pending bonuses |
| Player's game count | Accepted paid units credited to this run |

The last value is the one later used in score-per-coin calculations.
Under a simple one-coin, one-unit setting these stages line up neatly.
Other pricing and bonus configurations are why they cannot be treated
as the same variable.

For a concrete example, choose valid pricing with one unit per physical
coin, one unit per chargeable group, no bonus, and no existing credit.
The sound report advances. The OS adds one to that player's credit
balance. When the game's coin-check routine sees changed accounting
state, it asks the OS to check and deduct a group. The balance goes
from one to zero, and the successful return tells the game to credit
that player.

If the position has no health, the game initializes a prospective player:
starting health, a zero score, a game coin count of one, and character
selection. The joystick chooses the hero; Magic commits the choice.
Placement and joining are still separate steps, as Chapter 3 explained.
Money being accepted does not itself establish an unoccupied place
in the maze.

If the hero already has health, the same accepted group takes the top-up
path. The game adds health, increments that player's game coin count,
and marks the display for an update. It does not reset the score and
begin an entirely new run.

## Buying a balance, not a duration

The health setting selects one of thirty-two values, from 100 to 2,000.
For a paid start, the selected value initializes health. For a live
top-up, the selected value is added to what remains. These are different
operations even though ordinary paid play uses the same table.

At a setting of 750, an initial paid unit gives 750 health. Suppose the
Valkyrie later has 120 left when another group is accepted. The top-up
produces 870, not a reset to 750. Her score remains; her game coin count
increases by one.

Free play and the attract demo have their own initialization path,
using 2,000 starting health. The game still initializes its internal
coin count to one. That internal accounting baseline is another reason
not to read the field as a literal lifetime tally of metal coins.

Without damage or food, 750 health would pay for roughly 800 seconds
of the ordinary background drain at sixty frames per second. This is
a rate calculation, not a promised play time: `750 × 64 / 60`.
Combat can spend the balance far faster, while a meal can replenish it.
The initial phase of the frame counter also affects the first drain.

As Chapter 7 showed, the health service charges one point at multiples
of sixty-four in the global game frame counter. It does so only when
the routine runs for an active player. A dialog bypasses the routine,
so elapsed time spent reading does not create a backlog of missed
health charges. Armor changes applicable attack damage, not this
background rate.

Return to the side corridor. If reaching ordinary food costs sixty
health in damage and time, its hundred-point refill leaves a gain of
forty. If it costs a hundred and twenty, the expedition has made the
health problem worse. Those are invented costs for comparison, not a
prediction about a particular maze. They show why "food nearby" is not
enough information to choose a route.

The party can also divide the cost unevenly. The Valkyrie may take the
contact damage while the Elf shoots past her, yet whichever hero touches
the food receives its effect. There is no automatic reimbursement for
the person who made the meal reachable.

## The meal has a rule of its own

Ordinary wholesome food adds 100 health. Poisoned food subtracts 50 and
starts the dizzy condition, changing later movement as well as the
immediate balance. Shot resistance is a separate property: food that
survives a projectile is not necessarily worth a different amount,
and collection still removes it.

There is also adaptive food. Beyond level six, for stored mazes below
115, setup can choose an authored food object and replace it with this
variant. Other setup rules adjust the food supply for party size,
difficulty, and live conditions. The food encountered in play is
therefore not just a count copied unchanged from a stored layout.

Adaptive food is particularly worth examining because its result can
look like a judgment about need. The consumption code actually uses
the low sixteen bits of the eater's health, takes the remainder after
division by twenty, and looks that remainder up in a twenty-entry table.
The table contains awards from 25 through 200.

Here are four entries worked with small health balances:

| Health immediately before eating | Remainder after division by 20 | Health added | New health |
|---------------------------------|--------------------------------|--------------|------------|
| 107 | 7 | 200 | 307 |
| 108 | 8 | 25 | 133 |
| 114 | 14 | 25 | 139 |
| 115 | 15 | 200 | 315 |

These are calculations from the ROM rule, not observations of four
recorded meals. They establish something more useful than the vague
claim that the food is variable: less health does not always mean
a larger award, and more health does not always mean a smaller one.
The pattern repeats through the remainders rather than following a
smooth scale of generosity.

Damage and background drain can change the lookup before the hero
arrives. The value is selected at consumption, not reserved for the
player who first spotted the food. In our two-player scene, moving
aside for the needier hero can still be sensible, but the game does
not promise to turn that act into the largest possible total refill.

The floating award uses a parallel table of popup pictures so that
the display can report the selected amount. That visible number is
feedback about the completed transaction, not a label on the meal
that both players could read in advance.

## Treasure changes the next award too

Health is the immediate reason to cooperate. Score gives the players
another reason to compete.

Each player has a bonus multiplier. Ordinary score awards that pass
through the shared scoring helper are multiplied by that value before
being added to the player's total. The multiplier begins at one, but
ordinary treasure in multiplayer play redistributes it.

The collector gains two steps, capped at twice the active-player count.
Other living players lose one step each, stopping at one. Crucially,
this happens before the treasure's own score is awarded.

Let the Valkyrie and Elf each begin at one, and keep both active
through three ordinary 100-point treasure pickups:

| Pickup | Valkyrie's multiplier afterward | Elf's multiplier afterward | Pickup award |
|--------|----------------------------------|----------------------------|--------------|
| Valkyrie takes the first | 3 | 1 | Valkyrie gets 300 |
| Valkyrie takes the second | 4 | 1 | Valkyrie gets 400 |
| Elf takes the third | 3 | 3 | Elf gets 300 |

The second pickup would raise the Valkyrie from three to five, but the
two-player cap is four. On the third, the Elf rises from one to three
while the Valkyrie falls from four to three.

Now suppose each later earns an award with a base value of 100.
Both receive 300. Had the Elf left that third treasure untouched,
the Valkyrie's corresponding award would still have been worth 400
and the Elf's only 100.

This makes an ordinary treasure more than an isolated race for a small
prize. It changes later returns on fighting and collecting. The
redistribution is not a fixed pot of multiplier points: floors,
caps, and the number of other players determine how much the combined
total changes.

Solo collection skips the two-step increase. Treasure rooms also use
a separate collection tally and settlement path rather than this
ordinary-maze redistribution. Their payout conditions belong to
Chapter 13; a treasure-room tally should not be mistaken for the
multiplier shown during ordinary exploration.

The thief can make a high multiplier another form of exposed wealth.
It does not reset the multiplier on every successful theft. Permanent
powers have their own priority; otherwise the resource selection
compares weighted potions, keys, and the multiplier. Only the
multiplier-theft branch converts that value into carried treasure
and resets the victim to one.

For example, a hero with no permanent powers, no keys or potions,
and a multiplier of four offers a clear multiplier target. The
encoded bag value is `4 × 500`, or 2,000. A potion or power stolen
through another branch has a different consequence. The threat is
specific enough to change a decision without requiring the thief
to understand which treasure the player is proudest of collecting.

## Keeping score on the spending

The high-score screen does not simply preserve the biggest total.
The game divides each player's score by that player's recorded coin
count, using integer division, and ranks the result within the
chosen character class.

Compare two illustrative Warrior runs:

| Raw score | Recorded coins | Score per coin |
|-----------|----------------|----------------|
| 96,000 | 8 | 12,000 |
| 45,000 | 3 | 15,000 |

The shorter, lower-scoring run ranks higher. It did more per paid
unit. Comparing both as Warriors matters because there are separate
top-ten tables for the four character classes; one universal ranking
does not erase their different scoring opportunities.

![The game's class-specific score-per-coin tables](img/ch14_score_per_coin.png)

*The separate character tables make the unit of comparison visible:
score per coin within a class, rather than raw score across all heroes.*

Buying survival remains useful. It simply has a visible denominator.
At 30,000 points on two recorded coins, the quotient is 15,000.
Immediately after a third paid unit, with the score unchanged, it
is 10,000. Reaching 45,000 on those three units would restore the
earlier quotient.

Nothing in that arithmetic says the purchase was foolish. It may
allow the player to see a new maze, stay with friends, or recover
from a bad encounter. It means that survival and efficiency are
different objectives, and the ranking chooses the latter.

The final qualification uses the player's class and quotient when
their ending is processed. A qualifying result enters initials entry;
other players can still have their own business in the current game.
One person's high-score opportunity does not require the entire
party to share the same ending state.

## The party's success can return as pressure

There is a second score-per-coin calculation, with a different purpose.
At the relevant level handoff, the game totals the scores and recorded
coins of players with active status. It shifts the total score right
fourteen bits, divides by the total coins, and adds the result to an
existing signed spawn-probability bonus.

For ordinary positive values safely inside the stored ranges, the
calculation can be read as:

```text
scaled_score = total_active_score // 16384
increment = scaled_score // total_active_coins
spawn_bonus = spawn_bonus + increment
```

This is explanatory arithmetic, not a replacement for the ROM's
fixed-width operations and lifecycle preconditions. It shows both
the scaling and the addition.

Suppose the active party totals 196,608 points on six recorded coins.
Shifting removes the low fourteen bits and leaves twelve; twelve
divided by six is two. If the stored bonus was three, it becomes five.
The new value is not simply two. The adjustment accumulates rather
than replacing its history with a freshly computed rating.

A further accepted coin for a living player reduces that bonus by one
if it is positive. In this example five becomes four while the hero
also gains health. At zero or a negative value, the coin path leaves
the bonus alone.

Generators add the signed bonus to their ordinary probability
threshold. As Chapter 4 explained, difficulty, party size, the
level-dependent limit, scheduling, available space, and overload
suppression still matter. Raising the bonus does not guarantee a
birth, and lowering it does not remove a creature already standing
in the doorway.

The effect of the coin is therefore partly immediate and partly
prospective. The health number changes now. A different generation
threshold can influence a later attempt. There is no hidden monster
population cap being raised or lowered at the coin slot.

## What the operator can learn

Players see health, scores, and the next room. The operator can
inspect records about how the game is being used: coin statistics,
active play time, stored rankings, and distributions of session
time per recorded coin.

A **histogram** groups measurements into ranges. Instead of keeping
every player's complete history, it increments a counter for the
range containing that player's result. The OS maintains twenty bins
per player position. On a player's ending, it takes that position's
elapsed-time counter, clears it for the next session, and divides
the measurement according to the game-supplied histogram parameters
and the recorded coin count.

For the shipped game header, the scale is fifteen-second intervals
per coin, with the first two intervals combined into the lowest bin.
The final bin collects the high end. A few ranges are:

| Bin, counted from zero | Nominal seconds per coin |
|------------------------|--------------------------|
| 0 | Below 30 |
| 1 | 30 to below 45 |
| 2 | 45 to below 60 |
| 3 | 60 to below 75 |
| 4 | 75 to below 90 |
| 19 | 300 or more |

The table describes the service display's grouping, not captured
customer statistics. Suppose the elapsed counter represents 180
seconds at the nominal display rate and the player used three
recorded coins. Sixty seconds per coin puts the session in bin
three. If that bin held six, it now holds seven.

This clock is not the health balance in disguise. The OS accounts
elapsed VBLANK time while a player is tracked as active, whereas
the health drain belongs to a gameplay routine that dialogs can
skip. Time divided by coins and health purchased per coin answer
different questions even during the same run.

The bin scale comes from a packed parameter in the game ROM header.
It is not recalculated from the operator's live Game Difficulty
setting. That setting can certainly change the encounters and thus
the time people survive; it does not turn these records into a
difficulty-corrected measure of player skill.

Storage is deliberately bounded. Each bin is a byte. When a bin
would wrap after 255, the statistics code rescales the stored
histograms by halving their counts and gives the triggering bin
128. The shape remains useful, but the bars are no longer exact
lifetime counts of customers. The coin divisor is also capped at
128 for this calculation.

These records do not automatically rewrite the game's pricing or
difficulty. They give a human operator evidence to consider beside
those settings. A distribution concentrated at very short sessions
means something different from the same income earned through
longer sessions, even if both leave the coin box equally full.

## Leaving is another transaction

If the last player dies, a qualifying continue offer can preserve
the current depth. Its conditions include a level beyond the first,
no remaining active players, an enabled display timer, and player
statuses that permit the offer. The visible `PRESS START` wording
uses Magic on the physical control panel; there is no separate
Start button.

A continue is not simply the live top-up path with a different
animation. The dead player goes through initialization and joining
again, while the offer preserves the party's opportunity to resume
at that level. The distinction keeps "buying more health before
death" separate from "starting another player life after death."

For the Valkyrie at the side corridor, the available choices now
have several consequences. Food exchanges risk for a particular
pickup effect. A live coin preserves the run and changes its
accounting. Treasure may improve future score awards while taking
multiplier strength from the friend helping clear the route.
Leaving abandons remaining resources in exchange for progress.

The game keeps another kind of account across those decisions:
where later play should resume in its rotation of mazes. Two visits
to level six need not reveal the same room. The next chapter follows
the stored state that makes the dungeon remember more than one party.

### Sources and further reading

- [OS ROM](../doc/02_os_rom.md), sections 8.7 and 8.10-8.13:
  sound status, pricing, credit deduction, rankings, active-time
  accounting, and operator statistics. The transaction above follows
  `process_coins` (`0x35C4`), `calc_health_per_coin` (`0x3740`),
  `check_and_deduct_coin` (`0x37C2`), and game `coincheck`
  (`0x42B6A`). The game checks four OS credit bytes together as a
  longword; those bytes are distinct from the packed two-bit counters
  in the sound-board reply.
- [Game subsystems](../doc/04_game_subsystems.md), sections 4.3-4.7,
  5.2, 9, and 10: health, pickups, setup, theft, player endings, and
  continue conditions. Paid starting-health assignment at
  `0x48928-0x48946` and live addition at `0x42C12-0x42C2C`
  both use the table at `0x57862`.
- Adaptive-food indexing is at `0x51B90-0x51BE0`; the twenty health
  values and parallel popup indices are at `0x5B74C` and `0x5B774`.
  Treasure redistribution precedes its award at `0x51A16-0x51AC4`.
  Conditional multiplier theft is in `thief_steal_from_player`
  (`0x4E1FE`), particularly `0x4E28E-0x4E3F2`.
- [Data reference](../doc/05_data_reference.md): `player_bonusmult`,
  `player_scorepercoin`, `monster_spawn_probability_bonus`, and the
  generator probability table. The accumulated handoff arithmetic
  is `update_monster_spawn_bonus_from_score_per_coin` (`0x48B58`).
- The histogram example follows OS `record_player_session_histogram`
  (`0x4038`) and `run_statistics_histograms` (`0x4C66`) directly.
  Header byte `0x4006F = 0x2C` selects four rows, factor 15 from
  `0x69A8`, and offset one. For ordinary counts up to 128 its bin is
  `clamp((elapsed_vblanks >> 2) // (15 * 15 * coins) - 1, 0, 19)`.
  The matching display-width table is at `0x6B9A`. These are fixed
  header parameters, distinct from Game Difficulty bits in the
  live settings word.

[Previous: The game's clock](07_the_games_clock.md) |
[Contents](README.md) |
[Next: The next maze](09_mazes_and_slapstic.md)
