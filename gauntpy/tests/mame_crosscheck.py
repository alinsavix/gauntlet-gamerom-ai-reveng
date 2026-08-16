"""WP-21 sub-deliverable 3 -- MAME cross-check interface.

**Scoped down to a design, not a run.** PLAN.md says "The repository already
has this workflow (see the 2026-08-12 trace pass)," but that pass -- recorded
in ``doc/08_known_issues.md`` under "Resolved in the 2026-08-12 MAME trace
pass" (SOL-02, SOL-09, SOL-10, the operator-field and sound-control
resolutions) -- was a set of one-off, expert-driven interactive MAME/6502
sessions written up as prose corrections. There is no reusable script, Lua
watch file, or RAM-watch export committed anywhere in the tree: checked for a
``mame/`` (or similarly named) directory, any ``*.lua`` file (only
``doc/table-widths.lua`` exists, unrelated), and any watch/trace/export file
under ``doc/`` or ``refs/`` -- none exist. Producing a fresh trace requires an
interactive MAME session with a scripted input sequence and a debugger poke
to force the RNG seed, which is out of scope for one sitting. What follows is
the interface a future session (or a human with MAME open) needs in order to
finish the cross-check, plus the one part of it that *is* checkable without
MAME: that the address map it will compare against is sound.

## What a completed cross-check needs

1. A MAME Lua script that, for our fixed RNG seed and a scripted input
   sequence -- ideally exactly ``tests/golden.py``'s ``SCRIPTED_INPUTS``,
   replayed onto MAME's input ports -- dumps one row per ``(frame, address)``
   pair being watched, in the CSV shape ``load_mame_trace`` reads (see its
   docstring). This script does not exist yet.
2. Per PLAN.md §21 ("When cross-checking against MAME, force the seed on
   both sides"): before the scripted run starts, MAME's debugger must poke
   the RNG seed at ``0x904BFC`` to the same value ``golden.GOLDEN_SEED``
   seeds ``GameRandom`` with. The seed is never initialized on real hardware
   (see ``rng.py``), so without this step the two runs cannot agree from
   frame one.
3. Run ``golden.run_scripted_trace`` on our side and the Lua script on MAME
   with the identical input sequence, then call ``compare_state_to_trace``
   once per frame that has trace rows.

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
from gauntpy.state import GameState

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
