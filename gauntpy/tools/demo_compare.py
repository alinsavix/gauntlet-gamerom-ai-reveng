"""Compare gauntpy's attract demo with a MAME capture, optionally with RAM pokes.

The demo is deterministic: the same seed and the same recorded input give the same
run. A *poke* writes the same change into RAM on both sides at the same iteration,
which turns the demo into a test of something it does not normally show. Both sides
are then free to play out, and any difference is a real one. Modes:

    none      the demo as shipped
    families  at iteration 1, ghosts/grunts/aux grunts become demons, lobbers and
              sorcerers, and their generators follow
    lobbers   at iteration 1, every ghost, grunt and aux grunt generator makes lobbers
    death     at iteration 1500, the Elf's health becomes zero

To add one, change POKES below and the matching block in mame_demo_trace.lua.

    python tools/demo_compare.py capture --poke families --out traces/mame/poked/families.txt
    python tools/demo_compare.py compare traces/mame/poked/families.txt --poke families

``capture`` copies the repository's cfg/ and nvram/ to a temporary directory, because a
run changes them and the demo's start depends on them. ``compare`` needs GEX_ROM_DIR.
Traces are not committed. Comparison stops at the first state difference, since every
later frame depends on it, so fixing that difference is what lets it reach further.
"""

from __future__ import annotations

import argparse
import collections
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

GAUNTPY_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = GAUNTPY_ROOT.parent
sys.path.insert(0, str(GAUNTPY_ROOT / "src"))

from gauntpy.game.constants import MONSTER_TYPES, GameMode, MazeObjIds  # noqa: E402
from gauntpy.game.mainloop import tick  # noqa: E402
from gauntpy.game.rng import GameRandom  # noqa: E402
from gauntpy.game.state import GameState  # noqa: E402
from gauntpy.game.subsystems.attract import start_attract_screen  # noqa: E402

LUA_TRACE = Path(__file__).resolve().with_name("mame_demo_trace.lua")
MONSTERS = {int(t) for t in MONSTER_TYPES}
#: The trace's iterations start here; earlier video frames are demo setup.
FIRST_DEMO_FRAME = 28


# --- pokes -----------------------------------------------------------------------

def _poke_families(state: GameState) -> None:
    mobs = state.mobs
    for slot in range(32, 1024):
        old = mobs.obj_type(slot)
        new = None
        if old in (0x12, 0x13, 0x17):
            new = (0x14, 0x15, 0x16)[slot % 3]
        elif 0x1C <= old <= 0x21:
            new = old + 6
        elif 0x2B <= old <= 0x2D:
            new = old - 3
        if new is None:
            continue
        mobs.set_obj_type(slot, new)
        if new <= 0x16:
            tier = 8 if new == 0x14 else 0xB
            mobs.hpos[slot] = (mobs.hpos[slot] & 0xFFF0) | tier


def _poke_lobbers(state: GameState) -> None:
    mobs = state.mobs
    for slot in range(32, 1024):
        old = mobs.obj_type(slot)
        if 0x1C <= old <= 0x1E:
            mobs.set_obj_type(slot, old + 9)
        elif 0x1F <= old <= 0x21:
            mobs.set_obj_type(slot, old + 6)
        elif 0x2B <= old <= 0x2D:
            mobs.set_obj_type(slot, old - 6)


def _poke_death(state: GameState) -> None:
    state.players[1].health = 0


#: mode -> (iteration after which it applies, poke). Mirrors mame_demo_trace.lua.
POKES = {
    "none": None,
    "families": (1, _poke_families),
    "lobbers": (1, _poke_lobbers),
    "death": (1500, _poke_death),
}


# --- capture ---------------------------------------------------------------------

def capture(poke: str, out: Path, mame: str, rompath: str, timeout: int) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as work:
        for name in ("cfg", "nvram"):
            shutil.copytree(REPO_ROOT / name, Path(work) / name)
        shutil.copy(LUA_TRACE, Path(work) / LUA_TRACE.name)
        with open(out, "w", encoding="utf-8") as trace:
            subprocess.run(
                [mame, "gaunt2", "-rompath", rompath,
                 "-autoboot_script", LUA_TRACE.name, "-window", "-nothrottle",
                 "-sound", "none", "-skip_gameinfo", "-seconds_to_run", "900"],
                cwd=work, stdout=trace, stderr=subprocess.STDOUT, check=True,
                timeout=timeout, env={**os.environ, "POKE_MODE": poke},
            )
    print("wrote", out)


# --- loading ---------------------------------------------------------------------

def load_trace(path: Path) -> dict[int, tuple[dict[str, int], dict[int, tuple[int, ...]]]]:
    """``{iteration: (globals, {slot: (picture, link, H, V, state word)})}``.

    Each iteration keeps its last sample, because the loop bumps the counter on entry
    and a lag frame's first sample is mid-iteration.
    """
    iterations = {}
    mobs: dict[int, tuple[int, ...]] = {}
    current = None

    def finish() -> None:
        if current is not None and current["frame"] >= FIRST_DEMO_FRAME:
            iterations[current["iteration"]] = (current, dict(mobs))

    with open(path, encoding="utf-8", errors="replace") as trace:
        for line in trace:
            fields = line.rstrip().split(",")
            if fields[0] == "F":
                finish()
                current = {
                    "frame": int(fields[1]), "iteration": int(fields[2], 16),
                    "overflow": int(fields[3], 16), "seed": int(fields[4], 16),
                    "elf_slot": int(fields[9], 16), "elf_h": int(fields[10], 16),
                    "elf_v": int(fields[11], 16), "it": int(fields[14], 16),
                    "potions": int(fields[15], 16),
                }
            elif fields[0] == "M" and current is not None:
                mobs[int(fields[1])] = tuple(int(x, 16) for x in fields[2:7])
    finish()
    return iterations


# --- comparing -------------------------------------------------------------------

def new_demo() -> GameState:
    """The demo with the RAM it inherits from attract on the arcade (FIDELITY rule 102)."""
    state = GameState(rng=GameRandom(0xBFE6))
    state.eeprom_save_path = os.devnull
    state.tport_cycle_pos, state.tport_cycle_dir, state.tport_cycle_divider = 4, 1, 2
    state.forcefield_step_timer, state.forcefield_step = 5, 6
    start_attract_screen(state, int(GameMode.DEMO))
    return state


def _type_name(obj_type: int) -> str:
    try:
        return MazeObjIds(obj_type).name
    except ValueError:
        return hex(obj_type)


def _globals(state: GameState) -> dict[str, int]:
    elf = state.players[1]
    slot = elf.mob_slot
    return {
        "overflow": state.frame_overflow, "seed": state.rng.seed & 0xFFFF,
        "elf_slot": slot, "elf_h": state.mobs.hpos[slot] & 0xFFFF,
        "elf_v": state.mobs.vpos[slot] & 0xFFFF, "it": state.player_it & 0xFFFF,
        "potions": elf.potionsnum,
    }


def _record_differs(state: GameState, slot: int, mame: tuple[int, ...], heroes: set[int]) -> bool:
    """Everything but the picture. Heroes have no meaningful type word here (0x0F vs 0),
    and a monster's state field holds gauntpy's compass, two steps round from the ROM's."""
    mobs = state.mobs
    picture, link, h, v, word = mame
    if not picture and not mobs.picture[slot]:
        return False
    if (mobs.hpos[slot] & 0xFFFF, mobs.vpos[slot] & 0xFFFF) != (h, v):
        return True
    if slot in heroes:
        return False
    if mobs.obj_type(slot) != link >> 10:
        return True
    if link >> 10 in MONSTERS and bool(picture) == bool(mobs.picture[slot]):
        ours = mobs.state(slot) & 0x3F
        ours = (ours & 0x38) | (((ours & 7) + 2) & 7)
        return ours != (word >> 10) & 0x3F
    return False


def compare(path: Path, poke: str, show: int = 8) -> int | None:
    """Print a report; returns the iteration of the first state difference, or None."""
    iterations = load_trace(path)
    print(f"capture: {len(iterations)} iterations, last {max(iterations)}")
    state = new_demo()
    poke_at, poke_fn = POKES[poke] or (None, None)
    seen: collections.Counter[str] = collections.Counter()
    pictures: collections.Counter[str] = collections.Counter()
    first_picture = None
    link_samples = link_diffs = 0
    first_link = None
    stopped_at = None
    last = 0
    for iteration in range(1, max(iterations) + 1):
        tick(state)
        if state.game_mode != int(GameMode.DEMO) or iteration not in iterations:
            break
        last = iteration
        sampled, mame = iterations[iteration]
        ours = _globals(state)
        global_diffs = {k: (hex(ours[k]), hex(sampled[k])) for k in ours if ours[k] != sampled[k]}
        heroes = {p.mob_slot for p in state.players if p.mob_slot} | {sampled["elf_slot"]}
        diffs = []
        for slot in range(32, 1024):
            record = mame.get(slot)
            if record is None:
                continue
            obj_type = record[1] >> 10
            if obj_type in MONSTERS and record[0]:
                seen[_type_name(obj_type)] += 1
            if _record_differs(state, slot, record, heroes):
                diffs.append((slot, _type_name(state.mobs.obj_type(slot)), _type_name(obj_type),
                               hex(state.mobs.picture[slot]), hex(record[0]),
                               hex(state.mobs.hpos[slot]), hex(record[2]),
                               hex(state.mobs.vpos[slot]), hex(record[3]),
                               hex(state.mobs.state(slot)), hex(record[4] >> 10)))
            elif state.mobs.picture[slot] != record[0]:
                pictures[_type_name(obj_type)] += 1
                if first_picture is None:
                    first_picture = (iteration, slot, _type_name(obj_type),
                                     hex(state.mobs.picture[slot]), hex(record[0]))
        for slot, record in mame.items():
            if not (record[0] or state.mobs.picture[slot]):
                continue
            link_samples += 1
            links = (bool(state.mobs.picture[slot]), state.mobs.link[slot] & 0x3FF,
                     state.mobs.state_link[slot] & 0x3FF)
            if links != (bool(record[0]), record[1] & 0x3FF, record[4] & 0x3FF):
                link_diffs += 1
                if first_link is None:
                    first_link = (iteration, slot, links, (record[1] & 0x3FF, record[4] & 0x3FF))
        if global_diffs or diffs:
            stopped_at = iteration
            print(f"first state difference at iteration {iteration}: {global_diffs}")
            print("  (slot, type ours/mame, picture, H, V, state)")
            for row in diffs[:show]:
                print("  ", row)
            break
        if iteration == poke_at:
            poke_fn(state)
    print("compared through iteration", last)
    print("live monster samples:", dict(seen))
    print("picture-only differences:", dict(pictures), "first:", first_picture)
    print(f"depth link differences: {link_diffs} of {link_samples}", "first:", first_link)
    return stopped_at


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    cap = commands.add_parser("capture", help="run MAME and write a trace")
    cap.add_argument("--poke", choices=POKES, default="none")
    cap.add_argument("--out", type=Path, required=True)
    cap.add_argument("--mame", default=os.environ.get("MAME_EXE", r"C:\Portable\MAME\mame.exe"))
    cap.add_argument("--rompath", default=os.environ.get("MAME_ROMPATH", r"D:\users\alinsa\LaunchBox\Games\Arcade"))
    cap.add_argument("--timeout", type=int, default=600)
    cmp_ = commands.add_parser("compare", help="compare gauntpy with a trace")
    cmp_.add_argument("trace", type=Path)
    cmp_.add_argument("--poke", choices=POKES, default="none")
    args = parser.parse_args()
    if args.command == "capture":
        capture(args.poke, args.out, args.mame, args.rompath, args.timeout)
        return 0
    return 1 if compare(args.trace, args.poke) is not None else 0


if __name__ == "__main__":
    raise SystemExit(main())
