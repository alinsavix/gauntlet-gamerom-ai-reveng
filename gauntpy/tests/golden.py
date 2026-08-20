"""WP-21 sub-deliverable 2 -- golden frame traces.

Serializes a ``GameState`` to a compact, deterministic, JSON-safe digest each
frame, runs a fixed scripted-input sequence through ``tick()``, and compares
the resulting trace against a stored golden fixture. A one-pixel change in
where a monster ends up, a one-frame shift in a debounce edge, or a changed
RNG draw all show up as a loud, specific diff instead of silent drift.

Every subsystem is implemented now, so the digest is a genuine cross-section
of the whole simulation: ``digest_frame`` below reads the mob chain, the SLIP
heads, player health/position/score, credits and the RNG seed alongside the
frame and input-debounce bookkeeping. The scripted run itself is deliberately
narrow -- a bare ``GameState`` with no maze loaded -- so most of those fields
stay still and the trace stays readable on a diff; what it pins down is the
frame loop, the input path, and that nothing draws from the shared RNG stream
when nothing should.

RNG caveat (PLAN.md §21): the original's seed free-runs and is never
reproducible. We seed ``GameRandom`` explicitly so golden traces *are*
reproducible; see ``GOLDEN_SEED`` below.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from gauntpy.mainloop import tick
from gauntpy.rng import GameRandom
from gauntpy.state import NUM_PLAYERS, GameState

GOLDENS_DIR = Path(__file__).resolve().parent / "goldens"

#: Arbitrary fixed seed -- not a ROM value (the hardware seed at 0x904BFC is
#: never initialized; see rng.py). Picked once and frozen so goldens are
#: reproducible across machines and Python versions.
GOLDEN_SEED = 0xACE1

#: Scripted per-player raw input words (active low; see subsystems/input.py),
#: keyed by the frame index at which the word changes. A player's raw word
#: holds at its last-set value on frames without an entry -- exactly like a
#: real host, which keeps driving whatever the joystick currently reads.
#: Player 0 taps Magic (frames 5-7) then Left (frames 15-16); players 1-3
#: stay idle throughout, to keep the trace small and easy to read on a diff.
SCRIPTED_INPUTS: dict[int, dict[int, int]] = {
    5: {0: 0xFFFE},   # JOY_IDLE with bit 0 (Magic) cleared -- pressed
    8: {0: 0xFFFF},   # released
    15: {0: 0xFFDF},  # JOY_IDLE with bit 5 (Left) cleared -- pressed
    17: {0: 0xFFFF},  # released
}

SCRIPTED_RUN_FRAMES = 30


def build_scripted_state() -> GameState:
    """A fresh, explicitly-seeded ``GameState`` for a scripted run."""
    from gauntpy.constants import GameMode

    return GameState(game_mode=GameMode.NORMAL, rng=GameRandom(seed=GOLDEN_SEED))


def digest_frame(state: GameState) -> dict[str, Any]:
    """A compact, deterministic, JSON-safe snapshot of one frame's state.

    Every value here is a plain int, str, or a list/dict of those -- integers
    only, per PLAN.md ground rule 5. Field names and addresses match
    ``state.py``'s own comments.
    """
    return {
        "frame_counter": state.frame_counter,          # 0x904006
        "vblank_flag": state.vblank_flag,               # 0x904002
        "frame_overflow": state.frame_overflow,          # 0x904916
        "game_mode": int(state.game_mode),               # 0x904918
        "dialog_timer": state.dialog_timer,              # 0x904A9E
        "credits": state.credits,
        "rng_seed": state.rng.seed,                      # 0x904BFC
        "mob_chain": list(state.mobs.iter_chain()),       # depth_list_head walk
        "slip_heads": list(state.mobs.slip_heads),        # 0x905F80
        "player_input_raw": list(state.player_input_raw),               # 0x904920
        "debounce_shift_magic": list(state.debounce_shift_magic),       # 0x905F58
        "debounce_shift_fire": list(state.debounce_shift_fire),         # 0x905F60
        "players": [
            {
                "status": int(p.status),           # 0x9049A0
                "character": int(p.character),      # 0x9048E8
                "health": p.health,                 # 0x904980, longword
                "score": p.score,                   # 0x904990, longword
                "keysnum": p.keysnum,                # 0x90405A
                "potionsnum": p.potionsnum,          # 0x904055
                "bonusmult": p.bonusmult,
                "mob_slot": p.mob_slot,
                "direction": p.direction,
            }
            for p in state.players
        ],
    }


def run_scripted_trace(
    state: GameState,
    script: dict[int, dict[int, int]] = SCRIPTED_INPUTS,
    num_frames: int = SCRIPTED_RUN_FRAMES,
) -> list[dict[str, Any]]:
    """Run ``num_frames`` frames, applying ``script``'s input overrides, and
    return one digest per frame, oldest first."""
    trace: list[dict[str, Any]] = []
    for frame in range(num_frames):
        for player, raw in script.get(frame, {}).items():
            assert 0 <= player < NUM_PLAYERS
            state.player_input_raw[player] = raw
        tick(state)
        trace.append(digest_frame(state))
    return trace


def diff_trace(actual: list[dict[str, Any]], golden: list[dict[str, Any]]) -> list[str]:
    """Human-readable, per-frame mismatches between a fresh trace and the golden."""
    problems: list[str] = []
    if len(actual) != len(golden):
        problems.append(f"frame count: got {len(actual)}, golden has {len(golden)}")
    for i, (a_frame, g_frame) in enumerate(zip(actual, golden)):
        if a_frame != g_frame:
            keys = set(a_frame) | set(g_frame)
            for key in sorted(keys):
                if a_frame.get(key) != g_frame.get(key):
                    problems.append(
                        f"frame {i} field {key!r}: got {a_frame.get(key)!r}, "
                        f"golden says {g_frame.get(key)!r}"
                    )
    return problems


def load_golden(name: str) -> list[dict[str, Any]]:
    path = GOLDENS_DIR / name
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def save_golden(name: str, trace: list[dict[str, Any]]) -> None:
    """Write (or rewrite) a golden fixture. Not called by any test -- run it
    by hand (``python -c "from golden import *; save_golden(...)"``) only
    when a landed work package legitimately changes the scripted run's
    behaviour and the new trace has been reviewed by eye."""
    path = GOLDENS_DIR / name
    with path.open("w", encoding="utf-8") as fh:
        json.dump(trace, fh, indent=2)
        fh.write("\n")
