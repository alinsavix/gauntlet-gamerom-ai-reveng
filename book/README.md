# Gauntlet II: How It Works

How does a 1986 arcade machine turn a little memory, a shared screen, and
two buttons per player into a dungeon worth arguing over? This book starts
at the cabinet and follows the rules inward: why getting closer can let
you shoot sooner, how a crowd forms, where the thief finds your footprints,
and what the machine does with another quarter. The explanations connect
play to the hardware and program without requiring assembly-language or
arcade-hardware experience. Familiarity with basic programming helps.

**This is a new first-pass manuscript.** Chapters 1 and 2 are full chapters.
Chapters 3-18 are shorter narrative drafts: they can be read in sequence,
and each ends with editorial notes identifying work for the full version.
Source notes are optional reading. The prose describes the arcade game
unless it explicitly identifies a Python example or a hypothetical
comparison.

## Contents

| Chapter | The question behind it | State |
|---------|------------------------|-------|
| 1. [Enter the Gauntlet](01_how_to_play.md) | What decisions do these simple controls create? | Full |
| 2. [One arrow in the air](02_one_arrow.md) | Why can moving closer let you shoot sooner? | Full |
| 3. [Three friends, one screen](03_four_players.md) | Who decides where four independent players can go? | Draft |
| 4. [A room full of monsters](04_the_horde.md) | How do simple creatures become an overwhelming crowd? | Draft |
| 5. [Painting the dungeon](05_painting_the_dungeon.md) | Who draws a picture too busy for the main processor? | Draft |
| 6. [A world in ten bytes](06_a_world_in_ten_bytes.md) | How does the game find the thing your arrow hit? | Draft |
| 7. [The game's clock](07_the_games_clock.md) | What keeps everything moving together, and what can stop it? | Draft |
| 8. [What a quarter buys](08_what_a_quarter_buys.md) | What changes when somebody feeds the coin slot? | Draft |
| 9. [The next maze](09_mazes_and_slapstic.md) | Why isn't level six always the same place? | Draft |
| 10. [The living maze](10_the_living_maze.md) | What happens when the route changes while you use it? | Draft |
| 11. [The thief's trail](11_the_thiefs_trail.md) | How does the thief know where you went? | Draft |
| 12. [Fighting the dragon](12_fighting_the_dragon.md) | What makes this encounter different from another large monster? | Draft |
| 13. [Secrets and treasure](13_secrets_and_treasure.md) | What else can the game ask you to accomplish? | Draft |
| 14. [A machine that speaks](14_a_machine_that_speaks.md) | How does the game make a warning belong to you? | Draft |
| 15. [When nobody is playing](15_attract_and_demo.md) | How does the idle machine demonstrate and teach its own game? | Draft |
| 16. [Waking the cabinet](16_waking_the_cabinet.md) | What has to work before a player can trust the screen? | Draft |
| 17. [Gauntlet in Python](17_gauntpy.md) | How can we play with and look inside a reconstruction? | Draft |
| 18. [Reading the ROMs](18_reading_the_roms.md) | What supports these explanations, and what remains unknowable? | Draft |
| [Glossary and source map](appendix_glossary.md) | Where can I look up a term or follow a source? | Reference |

## For readers

Start with [Chapter 1](01_how_to_play.md). Technical concepts are introduced
where they become useful; you do not need to learn the memory map before
learning why a shot behaves as it does. The later chapters return to some
mechanisms from a different angle, adding detail rather than requiring
every explanation to be finished at its first appearance.

The sound chapter covers game-side communication and its consequences.
It does not attempt a full account of the sound processor's synthesis
and speech implementation. The Python chapter distinguishes the
reconstruction's conveniences from features of the original arcade game.

## For the rewrite

- [Project handoff](../BOOK_HANDOFF.md): current state, decisions, source
  priorities, working-tree cautions, and how to continue.
- [Editorial outline](OUTLINE.md): the full reading plan, coverage, and
  positive writing requirements.
- [Removal and deferral ledger](REWRITE_REMOVALS.md): what was moved,
  shortened, or left out of the previous manuscript, with destinations
  for material worth restoring.

Existing illustrations remain in [`img/`](img/). Their `chNN_` filenames
are retained asset identifiers from the previous manuscript, not the new
chapter numbers. ROM-derived renderings and captured frames are identified
in their captions. The source ROMs are user-supplied; see the repository's
[ROM requirements](../README.md#appendix-roms).
