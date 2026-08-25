# gauntpy clean-context handoff

## Goal

`gauntpy/` is a faithful Python reimplementation of the Gauntlet II arcade
game, reverse-engineered from ROMs owned by the repository owner. The target is
not merely visual similarity: game routines should reproduce the original
program's behavior and write modeled hardware memory, while rendering decodes
that state. ROM execution and MAME behavior outrank prose when they disagree.

Repository root:

`D:\Users\alinsa\Documents\SmartGit\gauntlet-gamerom-ai-reveng`

Current implementation branch: `book_plus_emu`

## Read first, in order

1. `gauntpy/ISSUES.md`
   - Authoritative implementation/status ledger.
   - Resolved entries preserve important traps and prior regressions.
   - Add newly discovered issues and record their resolution here.
2. `gauntpy/FIDELITY.md`
   - Short authoritative engineering invariants and investigation workflow.
   - Add a new invariant whenever a fix reveals a reusable rule.
3. Relevant reverse-engineering references under `doc/`:
   - `04_game_subsystems.md` - behavior and routine-level contracts.
   - `05_data_reference.md` - RAM fields and ROM tables.
   - `01_hardware.md` - display hardware and memory formats.
   - `06_maze_catalog.md` - maze selection/catalog behavior.
   - `02_os_rom.md` - OS text, formatting, EEPROM, and service APIs.
   - `07_function_index.md` - checked function signatures and addresses.
4. Relevant narrative chapters under `book/`.
   - Update these when findings change the player-facing or architectural
     explanation, not just an implementation detail.
5. `LOGO_HANDOFF.md`
   - Worked example of the ROM/MAME/Unicorn reverse-engineering workflow.

Generated contracts under `doc/generated/` are useful independent checks for
routine signatures, calls, RAM operands, and ROM table ranges.

## Code map

- `gauntpy/src/gauntpy/state.py`
  - Modeled game RAM and hardware-visible state.
- `gauntpy/src/gauntpy/subsystems/`
  - The 28 main-loop calls and related ROM routines.
- `gauntpy/src/gauntpy/maze.py`
  - ROM/gex bridge for maze decode, placement, mirroring, and level VRAM setup.
- `gauntpy/src/gauntpy/playfield_vram.py`
  - Authoritative column-first playfield descriptor/color writers.
- `gauntpy/src/gauntpy/render/`
  - Pure consumers of modeled playfield, MOB, alpha, and color RAM.
- `gauntpy/src/gauntpy/romtext.py`
  - Literal ROM text/glyph data used by game-side alpha writers.
- `gauntpy/tests/`
  - Unit, architecture, deterministic lifecycle, and end-to-end regressions.
- `python-gex/`
  - Sibling ROM graphics/maze decoder. gauntpy imports it only through bridge
    surfaces such as assets, maze, and rendering.

## Core invariants

Read all of `gauntpy/FIDELITY.md`; especially preserve these:

- Native MOB positions use bits 15-7; one pixel is `0x80`.
- Native V increases upward. Screen conversion belongs in `coords.py`.
- A live dynamic MOB's slot is its maze-cell identity.
- Preserve H/V low fields: palette/software flags and encoded sprite size.
- Randomness always routes through `state.getrandom()`.
- ROM tables are literal transcriptions with their ROM address nearby.
- Alpha, playfield, MOB, and color RAM are authoritative. Renderers do not
  reconstruct gameplay content or apply sampled visual overrides.
- Screen setup and teardown are both game-side RAM writes.
- PC-relative table addresses must use the CPU's resolved effective address.
- Large OS text is variable-width according to its ROM quad records.
- Stored identities can outlive markers: for example,
  `maze_player_start_slot` remains authoritative after setup consumes the
  PLAYERSTART marker.
- Transporter routes are bidirectional tables; thief routing requires the
  destination lookup and the opposite-table direction lookup.

## Evidence and tooling

### radare2

Executable:

`C:\portable\radare2-6.0.8-w64\bin\radare2.exe`

From the repository root:

```powershell
$env:PYTHONUTF8 = '1'
& 'C:\portable\radare2-6.0.8-w64\bin\radare2.exe' `
  -q -n -e scr.color=0 `
  -c '. doc/gauntlet_loader.r2' `
  -c 'pd 120 @ 0xADDRESS' `
  -c q malloc://1
```

Game ROM `row76.bin` maps game address `0x40000` to file offset zero. Other
local ROM images include `row9.bin`, `row10.bin`, graphics under `ROMs/`, and
sound ROM data.

### Unicorn

Unicorn's M68K backend can execute ROM routines directly. Always call:

`uc.ctl_set_cpu_model(UC_CPU_M68K_M68000)`

before running code containing `movem`. See `LOGO_HANDOFF.md` for a complete
example.

### MAME

Current executable:

`C:\portable\MAME\mame.exe`

Current version used by this project: 0.289.

If MAME is needed:

1. Search ignored `gauntpy/traces/mame/` for an existing capture.
2. Save the Lua script, raw trace, and metadata under
   `gauntpy/traces/mame/<scenario>/<timestamp>/`.
3. Record MAME version, driver (`gaunt2`), ROM hashes, command line, watched
   addresses, initial writes, inputs, and frame convention.
4. Keep traces locally and do not commit them.
5. Document conclusions in `doc/`, `book/`, `FIDELITY.md`, and/or `ISSUES.md`.

MAME 0.289 Lua uses `manager.machine` and `machine.screens:at(1)`.

## Validation

Use PowerShell or explicitly change directory because shell working directories
can drift.

ROM-backed gauntpy suite:

```powershell
Set-Location gauntpy
$env:GEX_ROM_DIR = '../ROMs'
python -m pytest -q
```

Current expected result:

`2359 passed, 9 skipped`

ROM-free gauntpy suite:

```powershell
Set-Location gauntpy
Remove-Item Env:GEX_ROM_DIR -ErrorAction SilentlyContinue
python -m pytest -q
```

Current expected result:

`2122 passed, 246 skipped`

Sibling decoder suite:

```powershell
Set-Location python-gex
$env:GEX_ROM_DIR = '../ROMs'
python -m pytest -q
```

Last known result: `700 passed`. A historical Windows-only
`test_env_override` path failure is unrelated if it reappears.

Run the smallest relevant tests during iteration, then both full gauntpy modes
before committing.

## Required workflow for each bug

1. Reproduce it with the smallest deterministic state or full-frame scenario.
2. Trace the exact ROM routine and relevant callers before choosing behavior.
3. Check existing helpers/tables before adding new logic.
4. Implement game-side state writes; do not patch the renderer to hide a
   simulation or VRAM bug.
5. Add a regression that would fail for the reported symptom.
6. Check tightly coupled lifecycle paths and ROM-free behavior.
7. Update:
   - `gauntpy/ISSUES.md` with the finding/resolution.
   - `gauntpy/FIDELITY.md` when a reusable invariant surfaced.
   - `doc/` when ROM/OS/hardware behavior was clarified or corrected.
   - `book/` when the architectural or player-facing explanation changed.
8. Run targeted tests, the complete ROM-backed suite, and the complete ROM-free
   suite.
9. Commit the completed batch. Do not include local ROMs, MAME data, traces,
   EEPROM/NVRAM files, `extra_docs/`, or unrelated user changes.

## Repository hygiene

- The working tree may contain untracked ROMs, local MAME files, `python-gex/`,
  `extra_docs/`, and other owner resources. Do not add them.
- At this handoff, `gauntpy/play.bat` has an unrelated user-owned modification.
  Preserve it and exclude it from commits unless explicitly asked.
- Do not reset, stash, amend, or discard user work.
- Temporary `gauntpy/gauntpy_eeprom.json` files created by tests may be removed
  if they were generated during the current work.
- Avoid names or implementation guidance from `extra_docs/dnd2c`.

## Current state

Latest completed commit:

`04802b4 gauntpy: fix post-death continue spawn`

Recent work also completed:

- RAM-driven alpha/playfield/MOB rendering.
- Correct OS large-font mapping and variable-width glyphs.
- Continuous maze boundaries and opaque/status-panel setup.
- Level and treasure-room splash lifecycle/countdown display.
- Moving-exit destination geometry.
- Per-level idle-door reset.
- Player-taught thief transporter routes and transition repair.
- Post-death continue placement using saved `maze_player_start_slot`.

The dragon's leading-wall behavior was verified as intentional ROM behavior:
`dragon_choose_move_direction` rejects a candidate before flame-lock target
publication when either leading footprint probe contains picture `0x8000`.

Start new work from the user's next observed bug rather than launching another
whole-codebase audit unless explicitly requested.
