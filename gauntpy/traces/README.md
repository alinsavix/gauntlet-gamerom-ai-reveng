# Trace workspace

This directory documents local fidelity traces. Generated traces are ignored by
Git and must not be committed.

- `scenarios/` — output from `gauntpy-scenario`.
- `mame/` — MAME RAM/video traces captured while investigating a behavior.

Whenever MAME is run for a bug investigation, keep the reusable Lua script,
raw trace, and a small local metadata file together under
`mame/<scenario>/<timestamp>/`. Record the MAME version, driver, ROM hashes,
exact command, watched addresses, initial RAM writes, input script, and frame
number convention. Reuse an existing capture before launching MAME again.

## Safely routing to a target level

Do not rewrite `game_mode`, player statuses, or the active maze while it is
running. That bypasses teardown/setup ownership and can leave stale player and
input state.

To reach ordinary target level `L` / maze `M` interactively:

1. Start a normal game and wait for a live player.
2. Set the current and next counters to `L-1` / `M-1`:
   - `levelnum_current` `0x904004`
   - `mazenum_current` `0x904000`
   - `level_next` `0x904B52`
   - `maze_next` `0x904B54`
3. Set `escape_timer` `0x9048C6` to `0x51F7`, the installed MAME cheat pack's
   "Turn walls to Exits Now!" value.
4. Walk into a converted wall exit.

The exit then computes `L` / `M` and uses the ROM's normal transition,
including maze teardown, Slapstic selection/decode, display setup, and player
respawn. For keyboard-only testing, launch MAME with `-nojoystick` so a
connected controller cannot contribute held directions or buttons.
