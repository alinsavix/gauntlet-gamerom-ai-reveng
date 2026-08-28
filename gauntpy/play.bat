@echo off
rem Launch the playable Gauntlet II runner with uv.
rem
rem   play.bat                         level 1, Warrior (mid-level drop)
rem   play.bat --attract               boot the real front end (coin 5, pick, Enter)
rem   play.bat --level 2 --character elf --scale 3
rem
rem Any arguments are passed straight through to gauntpy-play.


echo F1 - Admin interface               F5 - Next level         F9 - Enable Secret Room
echo F2 - Admin previous page           F6 - Add keys           F10 - Force Secret Room
echo F3 - Admin next page               F7 - Add potions
echo F4 - Save state                    F8 - Pause/resume timer


rem Run from this (the gauntpy project) dir regardless of where it's invoked.
cd /d "%~dp0"

rem copy link mode avoids uv's cross-drive hardlink warning on this checkout.
set "UV_LINK_MODE=copy"

uv run --all-extras gauntpy-play %* --scale 4 --no-first-encounter-messages
