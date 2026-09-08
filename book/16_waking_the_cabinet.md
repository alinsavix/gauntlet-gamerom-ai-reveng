# 16. Waking the cabinet

An operator switches on a cabinet and waits. Startup conceals an awkward
problem: the computer must examine its own memory before it can safely
use that memory to run the examination.
It also has to distinguish a machine ready for customers from one whose
operator has opened the coin door to investigate a fault.

The first instructions come from the OS ROM, not the game loop. The 68010
loads its initial stack pointer and execution address from the reset
vectors, masks interrupts, and brings the board through its startup
sequence. It also begins servicing the watchdog. This hardware timer
expects periodic writes from running software; if they stop, it resets
the machine.

## How can you test RAM without trusting RAM?

A normal subroutine call places a return address on the stack. Early
memory testing cannot assume that stack storage works. Instead, the OS
keeps the next instruction address in a CPU register and jumps into the
tester. Completion jumps through the register to continue booting.
The temporary scaffolding lives in registers while RAM is under examination.

Working storage, color memory, the playfield, the text layer, and motion-object
memory are tested separately. Patterns are written and compared with what
comes back. Those writes destroy old contents, which is acceptable before
a new session has begun.

The self-test switch selects the extended route. Ordinary startup takes
a shorter one, and the distinction is more than waiting time: the short
route fills each region but its walking-bit stages examine only the first
word. The extended route includes additional stages that traverse the
whole region. Seeing a normal startup complete is therefore not equivalent
to completing every available memory test.

Failure does not always mean an immediate halt. On normal startup a RAM
error is displayed and the sequence proceeds. In self-test, a failing
region is repeatedly tested until the operator acknowledges it with the
first position's Magic button, then testing advances. A usable text
display can thus report trouble elsewhere on the board.

## Who decides whether the game can start?

The OS checks its own ROM and examines the game ROM's header. That header
must begin with a valid jump into game-program territory. Without it,
the machine displays “NO GAME PROGRAM” and, after acknowledgment, can
enter diagnostics rather than trying to execute an absent game.

The game also supplies checksum information and a hardware-verification
hook. This lets the shared OS ask Gauntlet II to check the bank-switched
level storage that the game knows how to operate. A checksum error has
a different policy from a missing program: the normal path reports it
and passes control through the game's error entry, whose nonzero action
continues into startup. A displayed warning is not a certificate that the
remaining program will behave correctly.

This exchange continues after boot. The game calls fixed OS service
entries for text, sound transport, credits, persistent storage, and other
shared work. In the other direction, its header offers hooks for
game-specific interrupts, tests, and options. The OS is neither a desktop
environment nor a program that disappears once loading is complete. It
remains part of every running session.

## What can the operator preserve or recover?

Settings and records must survive being unplugged. EEPROM holds that
persistent information, but the OS does not treat every stored byte as
infallible. It decodes redundant records, uses check information to
repair correctable single-bit errors, and can recover from a usable copy
when its partner is damaged. Unrecoverable groups are reinitialized.
Repaired data is queued for writing rather than silently accepted only
in RAM.

During operation, writes and verification proceed in small steps alongside
the display rhythm. A failed byte write can be retried, and repeated
failures contribute to an error count. This is a persistence service,
not a promise that arbitrary damage or a power interruption can never
lose information.

The operator's screens bring these mechanisms back to visible questions.
Does this joystick switch change state? Are the colors right? Can a
motion object be displayed? Does the sound board answer? Coin and game
options sit beside statistics about use. The game has a second
interface for the person maintaining it, not just the people playing it.

Leaving self-test uses the watchdog to obtain a clean reset. Certain
exception paths also rely on that timer rather than trying to resume
uncertain execution. Recovery means starting again; it does not repair
a failing chip. Behind the apparently effortless return to the title
screen lies a practical distinction between preserving records, reporting
faults, and abandoning a run.

### For the full chapter

Walk through an operator's morning inspection, include one annotated RAM
error screen, and trace one EEPROM record from validation to queued
rewrite. Keep the complete boot decision tree and test patterns in the
technical reference.

### Source notes

- Reset, RAM tests, and error dispatch: [OS ROM](../doc/02_os_rom.md),
  §5–7; game error-entry behavior: [function index](../doc/07_function_index.md),
  `game_exception_abort`.
- Persistence, option screens, and diagnostics:
  [OS ROM](../doc/02_os_rom.md), §8.9, §8.13–8.14.
  Board registers: [hardware reference](../doc/01_hardware.md), §3.

[Previous: When nobody is playing](15_attract_and_demo.md) |
[Contents](README.md) |
[Next: Gauntlet in Python](17_gauntpy.md)
