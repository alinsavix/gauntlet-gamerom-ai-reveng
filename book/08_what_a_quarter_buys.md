# 8. What a quarter buys

You have enough health to reach the exit, probably. There is food down a side
corridor, but a generator is filling that corridor with ghosts. Another coin
would remove the immediate worry. Which purchase is cheaper: the food, bought
with time and danger, or the health bought at the coin slot?

Gauntlet II makes that comparison possible because money, time, and injury
meet in one number. A coin adds health; enemies subtract it; simply remaining
alive subtracts it too. There is no separate stock of lives insulating you
from those transactions.

## Health is time, but not a stopwatch

The ordinary background drain is one health point every 64 gameplay frames,
roughly once a second. It is the same for every character. Armor can change
what an attack costs without changing this slow underlying expenditure. A
quiet corridor and a packed doorway therefore spend the same background
allowance, but the doorway adds combat losses on top.

The operator chooses the coin's health value from a table ranging from 100
to 2,000. At a setting of 750, another credited coin adds 750 to a living
hero's health. That is not a promise of a particular play duration: damage,
food, and pauses separate the health balance from elapsed wall-clock time.

Food is another conversion, not uniformly a hundred-point refund. Ordinary
wholesome food adds 100 health; poisoned food takes 50 away. Later levels can
replace an authored meal with adaptive food, whose table offers values from
25 through 200. Its selection depends on the eater's current health, so the
same-looking opportunity need not have the same value to everyone. Setup also
adjusts how much food is present using party size, difficulty, and other live
conditions. The dungeon's food supply is not simply the stored map.

The quarter itself takes a surprisingly indirect route. The coin switches
connect to the sound board. A status exchange carries their counters back to
the main processor; the operating-system code applies the operator's pricing
and bonus-credit rules, and the game notices the resulting counter changes.
For a live player that becomes health. For an empty position it begins the
joining process. Physical coins, priced credit units, and the game's own
coin count are related stages, not interchangeable hardware readings.

## The score you keep and the score that ranks

Health asks whether you can continue. Score asks how much you accomplished,
and the bonus multiplier makes that question competitive even when everyone
needs the same exit.

In ordinary multiplayer play, collecting treasure raises the collector's
multiplier by two, capped at twice the active-player count. Other living
players lose one multiplier step, stopping at one. The redistribution happens
before the pickup's score award. With four players starting at one, the first
collector moves to three and receives 300 for an ordinary 100-point treasure.
The next treasure is consequently more than a race for a small fixed award:
it changes what later scoring events will be worth. Solo play skips the
increase. Treasure rooms use their own tally instead.

Raw points are not the final ranking currency. The game keeps separate
top-ten tables for the character classes and submits score divided by the
player's recorded coins. Compare two Warrior runs: 96,000 points on eight
coins is 12,000 per coin; 45,000 on three is 15,000. The lower-scoring
run ranks higher in that class.

![The game's class-specific score-per-coin tables](img/ch14_score_per_coin.png)

Buying survival can still be worthwhile. It simply does not conceal the
additional spending from the ranking calculation.

## Pressure, relief, and the operator's records

The efficiency calculation also influences generators, but through a
counter rather than an immediate command to create more monsters. At level
handoff, a scaled score-per-coin calculation for the active party adds to
an existing spawn-probability bonus. It accumulates; it is not a fresh
replacement value. A further coin for a living player reduces that bonus
by one when it is positive.

Generators add the bonus to their ordinary probability threshold. They still
need to be processed, pass their creation gate, and find room for the new
creature. This changes the likelihood of future births, not a population
cap, and it neither creates nor removes a crowd at the moment a coin drops.

After the last death, a qualifying continue offer can preserve the current
depth instead of sending the party through the opening again. Its `PRESS
START` instruction uses Magic on this control panel. Ranking and initials
entry belong to each player's ending; the game can keep hosting other
players meanwhile.

Long-term memory serves another audience. EEPROM retains settings, rankings,
and maze-rotation state, but also play-time statistics, including
difficulty-adjusted time-per-coin histograms. An operator can compare how long
customers play with the price and difficulty selected. Those records do not
automatically retune the machine. They provide business feedback for a human
with access to the service controls: what was sold, and how long it lasted.

### For the full chapter

- Follow one priced coin through pending credits, joining, and live top-up,
  keeping the three counters visibly separate.
- Expand the food and treasure examples into a two-player resource decision,
  including the thief's conditional theft of a multiplier.
- Show one service-screen histogram and explain its difficulty normalization
  without turning EEPROM's storage format into the main story.

### Source notes

- [Game subsystems](../doc/04_game_subsystems.md), §§4.3, 4.6–4.7 and
  10.1–10.5: health drain, pickups, scoring, sound-board coin path, ranking,
  and continue conditions.
- [Data reference](../doc/05_data_reference.md), RAM entries `0x90405F`,
  `0x90490E`, and `0x904B1A`: accumulated spawn bonus, treasure multiplier,
  and score-per-coin. The treasure redistribution and award order are at
  `0x51A16–0x51AC4`; the transition update is `0x48B58`.
- [OS ROM](../doc/02_os_rom.md), §§8.10–8.13, and
  [game subsystems](../doc/04_game_subsystems.md), §20: pricing,
  statistics, operator controls, and persistent settings.

[Previous: The game's clock](07_the_games_clock.md) |
[Contents](README.md) |
[Next: The next maze](09_mazes_and_slapstic.md)
