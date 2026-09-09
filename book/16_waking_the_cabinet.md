# 16. Waking the cabinet

Imagine an operator opening the arcade for the morning. Yesterday, one
player complained that a button sometimes did nothing. The game otherwise
seemed to work. Before admitting customers, the operator opens the coin
door, engages the self-test switch, and powers on.

This is an illustrative inspection, not a report from a particular machine.
It begins with two different questions. Can the board store and execute
its program reliably? And does the physical control produce the input the
program expects? A good answer to either question does not settle the other.

The first instructions come from the OS ROM, not the game loop. On reset,
the 68010 reads an initial stack pointer and execution address from the
beginning of that ROM. The stack points into the spare part of video RAM,
which also serves as working memory. The reset code masks interrupts,
pulses a board-control latch, and waits through a delay loop.

During that wait it repeatedly writes to the watchdog register. The
watchdog is a hardware timer: running software must keep servicing it, or
the board resets. A deliberate delay still needs those writes. To the
timer, a useful long calculation and a program stuck forever look alike
unless software continues announcing its presence.

Next comes the self-test switch. It is electrically active low: engaging
it clears the input bit. The engaged switch selects extended memory tests
and, eventually, the operator interface. Ordinary startup takes a shorter
route toward the game.

## How can you test RAM without trusting RAM?

A normal subroutine call saves its return address on the stack. Calling a
RAM tester that way would immediately depend on the memory it was supposed
to examine. The initial stack pointer tells the processor where storage
will be; it does not prove that storage works.

Instead, the OS puts the continuation address in address register A4 and
jumps into the tester. The tester keeps the region boundaries, patterns,
and status in registers too. On completion or a failed comparison, it
jumps through A4 to the next boot step. Another register, A6, connects the
individual test stages. This temporary scaffolding lives inside the CPU.

The order starts with that spare working RAM, followed by color RAM,
playfield RAM, alpha RAM, and motion-object RAM. These last four hold the
palette, background tiles, text overlay, and moving-picture descriptions
introduced in Chapter 5. Testing them separately allows a failure report
to distinguish, for example, the storage describing monsters from the
storage describing the floor.

The tests are destructive. They write patterns into a region and compare
what comes back with what should be there. One stage changes bits from the
high end of a word; another works from the low end. The extended suite
also includes restoration passes, an all-ones fill, and a final pass that
inverts each word and changes it back. None of this preserves a dungeon
left in RAM before reset.

There is an important limit to the shorter route. Its initial zero fill
reaches the whole region, but its subsequent high-bit-first stages test
only the first word. The loop compares the current address with the end
address, then services the watchdog before using the comparison's result.
That intervening write clears the processor's carry flag. The conditional
branch therefore cannot repeat the outer word loop.

Some stages of the extended suite share this problem. Its unaffected
low-bit-first and final inversion loops still traverse the full range,
however. The distinction is not simply “quick test” versus “the same test
for longer.” An ordinary startup can miss a failure that the self-test
route reaches.

## Reading a failure

Suppose the first playfield word cannot retain its highest bit. The tester
can read its initial zero successfully, write hexadecimal `8000`, then
read zero instead. Here is what those values mean in the error display:

```text
PLAYFIELD  RAM error at: 900000       ← address of the failed comparison
Wrote: 8000   Read: 0000              ← expected word and returned word
```

*Schematic layout, with constructed failure values and added annotations;
not a screenshot or a captured hardware fault. The region name, six-digit
address, and two four-digit words follow the ROM's detailed RAM reporter.*

Hexadecimal gives each group of four bits one digit. `8000` is a sixteen-bit
word with only its highest bit set. The difference between these two words
therefore identifies one bit that did not read back as written. It does
not, by itself, prove which chip, connection, or other board fault caused
the mismatch.

Nor can every memory failure produce this useful display. The spare
working-RAM failure has a simpler fixed “Working RAM error” message.
Detailed reporting uses the alpha layer and working storage; trouble in
those resources can impair the reporter itself. Legible text is evidence
that enough of the display path works to show it, not proof that the whole
video system is healthy.

On ordinary startup, a RAM error is displayed and testing continues without
waiting. Later initialization clears the alpha display. A person who sees
only the eventual title screen may never have read the warning.

With self-test engaged, a failing region is tested repeatedly. The loop
waits on the display rhythm and polls Magic at the **first player
position**. Pressing and releasing that button acknowledges the failure
and advances to the next region. Fire is not the acknowledgment, and
neither is a neighbor's Magic button. Acknowledgment says “continue the
inspection,” not “this memory has been repaired.”

## Who decides whether the game can start?

After the RAM paths rejoin, the OS initializes the display and checks its
own ROM. It adds the even-addressed bytes separately from the odd-addressed
bytes, retaining an eight-bit sum for each lane. The odd accumulator starts
at one; both finished accumulators must be `FF`. This is a compact
integrity check, not a guarantee that every possible corruption is detectable.

The game ROM must then present a recognizable entrance. Its header begins
with a jump instruction whose target must fall inside the boot check's
game-program range. Without that entrance, the OS displays “NO GAME
PROGRAM” and waits for Magic even on the ordinary route. After
acknowledgment, the missing-program state selects diagnostics instead of
blindly entering game code.

A valid header supplies checksum descriptors for game ROM ranges. It also
offers a verification hook: an entry through which the OS can ask the game
to perform a test it knows how to conduct. Gauntlet II uses that hook to
check the Slapstic-controlled storage from Chapter 9.

That verifier selects each of the four banks and accumulates separate
even- and odd-byte sums across their contents. Its successful result is
`0001FFFE`: bit 16 reports success, while the lower two bytes carry the
sums `FF` and `FE`. The OS consumes that result without needing to embed
Gauntlet II's bank-selection sequence in the shared checker.

Fault policy still depends on the route. Self-test can repeat failed ROM
checks until acknowledged. Normal boot reports ordinary ROM checksum
errors, but its final dispatch passes control to the game's error entry
with action one. In Gauntlet II, a nonzero action falls into startup.
The Slapstic verifier's failed result likewise produces a report and an
operator retry path; on normal boot it does not independently set the
ordinary checksum-error dispatch flag.

Thus “the game started” is weaker evidence than “the tests found no
errors.” The ROM establishes this behavior, not a historical explanation
for why Atari chose it.

The two-way arrangement continues during play. The game calls fixed OS
entries for text, sound transport, credits, and persistent storage. Its
header supplies hooks, control labels, and option descriptions in the
other direction. For example, the OS can run a general-purpose option
editor while the game supplies the bitfields and words describing health
per coin or game difficulty. The shared editor handles selection and
storage; game code later gives the selected values their gameplay meaning.

## Following the operator's controls

Once boot checks finish, the engaged switch selects OS-owned VBLANK
processing and the repeating diagnostic interface. VBLANK, the interval
between displayed fields, gives these screens their rhythm just as it
paces the game. The OS continues servicing the watchdog, updating text
effects, and advancing persistent-storage work while the operator looks
at a pattern.

Return to the reported intermittent button. The switch test displays all
four positions' inputs. Moving a joystick and pressing each button lets
the operator ask whether the expected switch state reaches the program.
An input that never appears is a different symptom from one that appears
correctly here but seems ineffective during play.

The latter can have a gameplay explanation. A held Fire button cannot
create another arrow while that player's reserved shot is still live.
Magic without an available potion cannot supply the same result as Magic
with one. A switch test removes those rules from the experiment; it does
not reproduce the fight in which the complaint arose.

The shipped prompt strings call the first position's controls “WARRIOR
joystick,” “WARRIOR &lt;FIRE&gt; button,” and “WARRIOR &lt;MAGIC&gt; button.”
These are diagnostic labels, not a restriction on which character can
play there. First-position Magic advances the tests. The input helper
requires consecutive agreeing samples before accepting a changed switch
state, so the menu does not treat every brief contact transition as a
fresh deliberate press.

The other screens separate more of the path from stored description to
visible or audible result:

| Test | A useful comparison |
|------|---------------------|
| Playfield and alpha | Do background tiles and text patterns fail in the same way, or only one layer? |
| Motion objects | Does changing an object's picture, position, size, or palette expose the defect? |
| Color and convergence | Are color relationships or the alignment of the monitor's color images wrong even when the patterns are recognizable? |
| Sound | Does the sound processor respond, and can selected music, effects, and speech be exercised? |

The motion-object test is particularly concrete. Second-position buttons
select the object number; the third-position joystick changes its
position, and that position's buttons change its palette. Fourth-position
buttons step its picture number. This lets the operator vary one stored
description without assembling a dungeon around it. A distorted image
that follows one picture selection suggests a different investigation
from a defect that remains at one screen position.

The sound test distinguishes failure to communicate from reported sound
CPU RAM, ROM, interrupt, music-chip, and speech-chip errors. Its command
wait can time out after thirty VBLANK ticks rather than wait indefinitely
for a response. These are useful distinctions, not automatic component
replacement instructions.

Coin options, game options, and statistics accompany the hardware tests.
Statistics can explain how the game has been used; clearing them is a
separate operator action, not a harmless way of refreshing the screen.
Chapter 8 followed those records from the players' side. Here, their value
depends on surviving the next power cycle.

## Recovering a stored record

EEPROM is electrically rewritable memory that retains information without
power. The board's part holds 512 bytes. It appears on the 68010's low
byte lane, at odd addresses, so consecutive device bytes are two CPU
addresses apart.

The OS encodes ten data bytes together with five check bytes. That uses
fifteen EEPROM bytes and spans thirty CPU address positions. The check
bytes are interleaved with the data, not appended as a second copy.
Certain configuration records also have a separate redundant copy;
error-correcting checks and duplicate records are two distinct protections.

The checks use exclusive OR, or XOR. For one bit position, XOR records
whether an odd or even number of its inputs are set. Each data byte
participates in a particular combination of four checks, with a fifth
overall check. Recomputing them during a read produces a *syndrome*: a
pattern of disagreements that can identify a correctable damaged bit.

Here is a constructed codec example, not a captured EEPROM image. Let the
first data byte be `2A` and the remaining nine bytes be zero. The ROM's
placement table puts that first byte at encoded position 3. The resulting
check bytes at positions 0, 1, 2, 4, and 8 are:

```text
Encoded check position:    0    1    2    4    8
Stored check byte:       D5   2A   2A   00   00
```

Position zero includes an inversion, which is why its value is `D5`
rather than `2A`. Now suppose bit 2 of the first data byte changes:

```text
intended data:  2A = 00101010
stored data:   2E = 00101110
difference:    04 = 00000100
```

On decode, checks 1 and 2 disagree by `04`, as does the overall check;
checks 4 and 8 still agree. For bit 2, the decoder assembles syndrome
`13` hexadecimal. Its table identifies data byte zero. XORing that byte
with `04` restores `2A` in RAM. The decoder returns a positive,
correctable status rather than pretending the read was clean.

Follow that result through initialization. Suppose it occurred in the
first configuration block and its redundant partner is clean. The OS
temporarily preserves the corrected ten bytes, reads the partner, and
retains the usable result. It sets the rewrite-request bit for logical
region zero. If the partner instead has an uncorrectable syndrome, the
temporary corrected copy can supply the data. If neither copy is usable,
the initialization path resets the affected configuration and statistics
rather than manufacturing the missing values.

When the worker selects the requested region, it re-encodes those ten
bytes, regenerating the check bytes from the RAM image. For this paired
configuration region, it writes the primary encoded record and then its
partner. The useful outcome is not merely that this boot obtained `2A`;
the stored copies can be made usable for the next boot too.

Initialization actively drains queued repair work, servicing the watchdog
and calling the worker through a delay loop, then checks again. It also
has error exits. This is not an unlimited promise to repair a part that
cannot retain writes.

## Writing is a process, not a moment

During ordinary operation the same worker advances alongside VBLANK.
It compares a byte with the desired value, performs a write when needed,
then verifies on a later visit. Writing requires an EEPROM-unlock access
followed by the byte store, with interrupts masked around that short
sequence. Failed comparisons can consume retries; exhausted failures
increase a saturating error counter instead of wrapping it back to zero.

A request therefore differs from a completed physical update. The OS's
busy query includes pending requests, queued block work, and an active
write. The game also has its own policy for deciding when to submit some
of its persistent information.

Its periodic save check reloads a countdown to 36,000 calls, roughly ten
minutes at sixty calls per second. When due, it compares six values with
its saved cache: ordinary maze number and stride, treasure-maze number
and stride, games-played count, and game settings. Any difference submits
the game block. All six unchanged means this path skips the submission.
Other events can shorten the wait by setting the countdown to one.

For example, a changed maze stride is enough to pass that gate when the
timer expires. A changed monster position is not: it is neither among the
six comparisons nor a promise of resumable play. Scores and OS statistics
also have their own storage services; this gate is not a universal rule
that all EEPROM information waits ten minutes.

Several limits follow. A value changed only in working RAM can be lost
before submission. A submitted record can still be partway through its
byte updates when power disappears. Check information and redundant
configuration copies improve recovery, but they do not make every
multi-byte update an indivisible transaction or preserve an interrupted
game.

## Leaving the back room

The operator releases the self-test switch. The OS does not simply return
from the diagnostic routine into gameplay; that routine loops forever.
Instead, its VBLANK handler checks whether EEPROM work is idle. Once it
is, the handler masks interrupts and deliberately spins without servicing
the watchdog. The resulting reset starts the ordinary boot route.

Waiting for idle avoids deliberately abandoning pending storage work.
It does not turn the watchdog into a memory repair mechanism. The same
distinction matters when a CPU exception reaches the game's error entry:
action zero takes its abort route, unlike the nonzero boot-check action
that continues into startup. The abort relies on watchdog recovery rather
than returning to uncertain execution.

Back at the title screen, yesterday's players have not resumed their
fight. The program has started again, loading the records it can recover.
The morning inspection has separated a button's electrical state from its
gameplay meaning, a displayed warning from a clean test, and a recovered
setting from a restored session. Those are different kinds of confidence,
and the operator needs all three distinctions before trusting the game
with another evening's play.

### Source notes

- Reset, RAM ranges, A4/A6 continuations, short-loop condition-code behavior,
  and acknowledgment: [OS ROM](../doc/02_os_rom.md), §5.1–5.7;
  [memory-test contracts](../doc/generated/os_memory_test_contracts.csv).
  The constructed failure follows `0x0AF4–0x0B2C`; its display fields follow
  `display_ram_error_detail` (`0x2828`) and strings at `0x5A8A–0x5B35`
  in `row9.bin`. The schematic does not reproduce screen coordinates.
- Header checks, checksum dispatch, and hooks: [OS ROM](../doc/02_os_rom.md),
  §4–6. Directly checked: `validate_game_rom` (`0x21A0–0x2268`),
  its boot caller at `0x094C`, and final dispatch at `0x09D8`;
  `slapstic_verify` (`0x56EAA`) and `game_exception_abort` (`0x40140`)
  in [function index](../doc/07_function_index.md).
- Diagnostic screens and controls: [OS ROM](../doc/02_os_rom.md),
  §8.13–8.14; [screen contracts](../doc/generated/os_selftest_screen_contracts.csv).
  Motion-object control consumers were checked at `0x1CE0–0x2008`;
  game-header control strings at `0x40102–0x4013F`.
- EEPROM capacity and byte lane: [hardware reference](../doc/01_hardware.md),
  §2–3. Codec and initialization: [OS ROM](../doc/02_os_rom.md), §8.9;
  [EEPROM contracts](../doc/generated/os_eeprom_contracts.csv).
  The example follows the encoder at `0x43BE`, placement table `0x44BE`,
  decoder `0x467C`, correction table `0x4736`, and paired-copy loader
  `0x4540–0x459A`. “Thirty bytes” in the codec reference denotes the
  CPU-address stride: fifteen populated odd-addressed EEPROM bytes.
- Queue/worker direction was checked directly at `0x4858–0x4888` and
  `0x4398–0x4448`: the nonzero mode of the service named
  `eeprom_read_block` queues a source buffer for encoding/writing; mode
  zero decodes a read. The reference's “asynchronous read” wording does
  not describe the nonzero-mode consumer. Game save comparisons and
  submission: `0x43192–0x43278`; countdown storage:
  [data reference](../doc/05_data_reference.md), `eeprom_write_timer`.
  Boot repair draining: `0x47E4–0x4800`; watchdog exit waits for idle:
  [OS ROM](../doc/02_os_rom.md), §7.2.

[Previous: When nobody is playing](15_attract_and_demo.md) |
[Contents](README.md) |
[Next: Gauntlet in Python](17_gauntpy.md)
