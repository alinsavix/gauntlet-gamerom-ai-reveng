"""RAM address map and trace helpers for comparing gauntpy with MAME.

This began as WP-21's plan for a MAME cross-check: replay ``golden.py``'s scripted
input in MAME with the RNG seed forced, dump watched RAM each frame, and diff it
here. That trace was never recorded, and the comparison is now done by other means:

- ``tools/demo_compare.py`` with ``tools/mame_demo_trace.lua`` captures the attract
  demo, and three poked variants of it, frame by frame in MAME 0.289 and compares
  every MOB record and the RNG seed with gauntpy (``tests/test_demo_compare.py``).
- ``tools/rom_exec.py`` runs the original routines under Unicorn, and
  ``tools/thief_walk.py``, ``dragon_walk.py``, ``forcefield_check.py`` and
  ``secret_check.py`` compare whole subsystems with them (``tests/test_rom_*``,
  ``test_thief_walk.py``, ``test_dragon_walk.py``, ``test_level_setup_rom.py``).

The helpers below remain as a checked address map and a small trace reader.

## What exists today

``field_addresses()`` is not hand-copied -- it parses ``GameState``'s own
field comments at import time (reusing ``contracts.first_address_in``), so
it can never silently drift from what ``state.py`` documents. Per-player
fields need their own map because ``GameState.players`` is a list, not
individually addressed fields; ``PLAYER_FIELD_ADDRESSES`` below intentionally
covers only ``health`` (0x904980, stride 4 -- confirmed both in ``state.py``
and ``doc/05_data_reference.md`` line 149). Other ``Player`` fields' per-slot
strides are not confirmed in the documentation read for this package, so they
are left out rather than guessed; extending this map is future work, not a
guess made here.
"""

from __future__ import annotations

import csv
import inspect
from pathlib import Path

from contracts import first_address_in, parse_int
from gauntpy.game.state import GameState

#: Per-player fields whose base address (player 0's copy) and byte stride are
#: confirmed in the documentation. address(player_index) = base + stride *
#: player_index.
PLAYER_FIELD_ADDRESSES: dict[str, tuple[int, int]] = {
    "health": (0x904980, 4),  # 32-bit longword, stride 4 -- doc/05_data_reference.md line 149
}


def field_addresses() -> dict[str, int]:
    """``{GameState field name: documented ROM address}``.

    Parsed from ``state.py``'s own trailing ``# 0x...`` field comments, so
    this can never drift from what ``GameState`` documents about itself.
    Composite fields with no single address (``mobs``, ``rng``, ``players``)
    are simply absent -- each has its own internal addresses documented
    elsewhere (``mob.py``, ``rng.py``, ``PLAYER_FIELD_ADDRESSES`` above).
    """
    source = inspect.getsource(GameState)
    addresses: dict[str, int] = {}
    for line in source.splitlines():
        line = line.strip()
        if ":" not in line or "#" not in line:
            continue
        name, _, rest = line.partition(":")
        name = name.strip()
        if not name.isidentifier():
            continue
        _, _, comment = rest.partition("#")
        addr = first_address_in(comment)
        if addr is not None:
            addresses[name] = addr
    return addresses


def load_mame_trace(path: str | Path) -> list[dict[str, int]]:
    """Load a MAME RAM-watch export.

    Expected CSV shape (header required), one row per ``(frame, address)``
    pair watched::

        frame,address,value
        0,0x904006,0
        0,0x904BFC,4660
        1,0x904006,1

    ``address`` and ``value`` may be decimal or ``0x``-prefixed hex. This is
    *not* MAME's native watch-list format -- it is the simplest shape a small
    Lua export script (see the module docstring; not yet written) could
    reasonably emit.
    """
    resolved = Path(path)
    with resolved.open(newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    return [
        {
            "frame": parse_int(r["frame"]),
            "address": parse_int(r["address"]),
            "value": parse_int(r["value"]),
        }
        for r in rows
        if (r.get("frame") or "").strip()
    ]


def compare_state_to_trace(
    state: GameState,
    trace_rows: list[dict[str, int]],
    frame: int,
) -> list[str]:
    """Diff one frame's watched MAME values against our ``GameState``.

    Only addresses present in ``field_addresses()`` / ``PLAYER_FIELD_
    ADDRESSES`` are checked; a MAME watch list will usually be broader than
    what we track, and unrecognised addresses are silently ignored rather
    than treated as errors.
    """
    problems: list[str] = []
    rows_this_frame = {r["address"]: r["value"] for r in trace_rows if r["frame"] == frame}
    if not rows_this_frame:
        return problems

    addr_to_field = {addr: name for name, addr in field_addresses().items()}
    for addr, value in rows_this_frame.items():
        if addr in addr_to_field:
            name = addr_to_field[addr]
            actual = int(getattr(state, name))
            if actual != value:
                problems.append(
                    f"frame {frame} {name} (0x{addr:X}): got {actual}, MAME says {value}"
                )

    for name, (base_addr, stride) in PLAYER_FIELD_ADDRESSES.items():
        for i, player in enumerate(state.players):
            addr = base_addr + stride * i
            if addr in rows_this_frame:
                actual = int(getattr(player, name))
                value = rows_this_frame[addr]
                if actual != value:
                    problems.append(
                        f"frame {frame} player[{i}].{name} (0x{addr:X}): "
                        f"got {actual}, MAME says {value}"
                    )

    return problems
