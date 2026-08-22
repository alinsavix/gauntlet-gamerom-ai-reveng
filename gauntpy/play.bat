@echo off
rem Launch the playable Gauntlet II runner with uv.
rem
rem   play.bat                         level 1, Warrior (mid-level drop)
rem   play.bat --attract               boot the real front end (coin 5, pick, Enter)
rem   play.bat --level 2 --character elf --scale 3
rem
rem Any arguments are passed straight through to gauntpy-play.

rem Run from this (the gauntpy project) dir regardless of where it's invoked.
cd /d "%~dp0"

rem copy link mode avoids uv's cross-drive hardlink warning on this checkout.
set "UV_LINK_MODE=copy"

uv run --all-extras gauntpy-play %*
