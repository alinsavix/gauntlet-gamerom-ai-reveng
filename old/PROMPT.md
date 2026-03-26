You have access to the radare2 MCP server.

Your job is to use radare2 to analyze the provided 68010 arcade ROM files, which are the game program for the "Gauntlet II" arcade game (which we will just call "Gauntlet" most of the time, for ease of reading). The ROMs are split into three files, which load at different addresses:
* row9.bin should load at 0x0
* row76.bin should load at 0x040000
* row10.bin should load at 0x038000

When using radare2, you should always load the existing project "gauntlet.r2", and stop working if you are unable to get the project to load. Due to various issues internal to radare2, there may be multiple mappings of row9.bin. Clean these up when you open the project so that each file has only one mapping. At the end of each phase, you should save the current radare2 project using the "PS" command (not the Ps command, note capitalization). If you can't successfully save the project for some reason, create an "emergency.r2" file by hand with the same knowledge, and stop running.

The row9.bin file is the "OS" for the game -- generic code that's intended to run multiple different Atari arcade games, though in this case it has been somewhat specialized for Gauntlet. We have already reverse engineered the OS ROM, and that analysis can be found in `OS_ROM.md`. In general, avoid reverse engineering anything in that part of the ROM unless the information presented in the existing analysis seems very wrong somewhere.

There is a summary of how much of the hardware works in `HW_WRITEUP.md`.

Quite a lot is already known about the Gauntlet ROMs, which should significantly help jumpstart your analysis. A breakdown of known and partially known RAM locations and function locations is in `GAME_ROM_KNOWN.md`. You can probably start your work at the main loop in the code.

Because it is sometimes useful for giving a clue as to what code is doing what, the list of sound commands is available in `soundcmds.csv`. This can be used, for example, to discover that certain code handles eating food (because that code uses the "eating food" sound effects).

If some terms are unclear during your planning, be sure to ask me for clarification, I can probably help. If some information seems contradictory, ask me then, too. I don't mind questions!

The results of your reverse engineering analysis should be persisted as a REPORT.md file, and in the radare2 project mentioned above.
