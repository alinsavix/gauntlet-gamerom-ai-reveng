# 14. A machine that speaks

“Blue Elf needs food, badly.” You do not need to stop moving, find your
status column, and read a number to understand that warning. Nor do the
other three players have to wonder whom it concerns. The voice combines a
condition in the game with the identity of the person who can act on it.

That identity has two parts. Blue names a control position; Elf names the
class chosen at that position. As [four-player play](03_four_players.md)
showed, those are independent choices in Gauntlet II. The speech system
preserves the distinction. Its name table contains all sixteen color-and-class
combinations, not merely four hero names.

## How does it put your name into a sentence?

For this warning, the game selects the Blue Elf phrase, command `0xC4`,
and then a warning phrase such as `0x5A`, “needs food, badly.” It sends
numbers, not a sentence represented as text. The sound board supplies the
spoken material associated with those numbers.

The same arrangement lets the game announce who is IT or describe a newly
acquired power without storing every possible complete sentence. A name,
a connecting phrase, and a description can be combined as circumstances
require. Low-health commentary even has alternatives: a random selection
chooses among ordinary warnings, while a separate branch can warn a
well-equipped player about losing their powers.

This is not a voice that simply reads every state change aloud. A spoken
latch and a cooldown constrain the low-health warning. Many explanatory
phrases pass through a wrapper that obeys the operator's Disable Speech
setting, while some character vocal effects take a different path. The
game also has to decide when a message box should hold the action, linking
spoken advice to the pauses described in [the game's clock](07_the_games_clock.md).
The words, their timing, and their recipient are all parts of the interface.

## What happens after the game asks for a sound?

The main 68010 and the sound board's 6502 are separate computers. Their
conversation crosses two one-byte latches: one carries a command outward,
the other carries a reply back. A latch holds its byte until the receiver
collects it. A status bit tells the sender whether the outgoing latch is
still occupied; interrupts notify the receiving processors of traffic.

Most game sounds take a short route. `sound_play` tries to submit the byte
immediately. If the latch is busy, the byte can wait in a small ring in game
RAM. That ring has eight physical slots but room for seven pending commands,
because its index convention needs to distinguish full from empty. Once
full, it drops a new request rather than waiting indefinitely.

Near the end of a frame, `main_update_sound` makes a bounded number of
submission attempts. A busy latch leaves the oldest byte in place for
another attempt. Sound-board recovery and the game's frame-overflow signal
can suspend this draining. Consequently, requesting a noise and hearing
it are not the same instant, and an overloaded queue need not preserve
every request.

There is another queue on the sound side for speech, with its own priority
rules. It is not the main CPU's outgoing ring. Keeping those two waiting
places distinct explains how short game-side requests can become longer
spoken phrases without holding the dungeon still for each syllable.

## Why do quarters travel through the sound board?

The return latch carries more than audio diagnostics. The coin switches
belong to the sound board's input path. The OS regularly sends command 3;
its reply packs the changing coin counters into a byte. An interrupt
collects that reply, and the OS compares it with the previous value before
updating credits. Only then does the game turn a new credit into joining
or additional health.

Command 7 serves a different purpose: it asks for diagnostic status. The
game watches for faults and stalled communication, can reset the sound
processor independently, and allows a recovery interval for its startup
acknowledgment. The same narrow connection therefore carries warnings,
music requests, coin information, and evidence that the second computer
is still responding.

On that second computer, the YM2151, POKEY, and TMS5220 provide music,
effects, and speech capabilities. Their sequencing and synthesis are
sound-board work; the main game ROM tells us when and why commands are
requested, not the complete process that turns them into a waveform.
That boundary matters even when the result sounds like one machine
speaking directly to you.

### For the full chapter

Follow one low-health warning through both queues, contrast it with the
thief's arrival cue, and diagram a coin reply beside a diagnostic reply.
Explain speech priority and one looping effect without turning the chapter
into a sound-command catalog.

### Source notes

- Phrase selection and player warnings: [game subsystems](../doc/04_game_subsystems.md),
  §4.3 and §11; `speech_charname_tbl` and `character_lowhealth_speech` in the
  [data reference](../doc/05_data_reference.md).
- Latches, interrupt reception, coin polling, and reset:
  [hardware](../doc/01_hardware.md), §3, and [OS services](../doc/02_os_rom.md),
  §8.7–8.8. Command descriptions: [sound catalog](../refs/soundcmds.csv).

[Previous: Secrets and treasure](13_secrets_and_treasure.md) |
[Contents](README.md) |
[Next: When nobody is playing](15_attract_and_demo.md)
