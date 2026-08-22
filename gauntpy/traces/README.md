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
