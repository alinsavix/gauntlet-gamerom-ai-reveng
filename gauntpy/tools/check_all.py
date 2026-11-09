"""Run every ROM comparison at once and report one line each.

    python tools/check_all.py               # every tool, the four demo captures if present
    python tools/check_all.py --flights 6   # and six lockstep flights of 30,000 frames

Each tool is its own process, and the slowest ones share their cases between worker
processes too, so the whole check costs about as long as its slowest tool. Every case
runs exactly as it does when the tool is started by hand. The exit status is 1 when any
tool reports a difference or fails, and each tool's full output goes to ``--out``.

Needs GEX_ROM_DIR and the ROMs ``rom_exec.py`` needs.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import os
import subprocess
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_TRACES = _ROOT / "traces" / "mame"
# Flights that between them reach deaths, initials, second games, doors and deep levels.
_FLIGHTS = (
    ("--pilot", "1", "--warp", "--seed", "141"),
    ("--pilot", "2", "--warp", "--seed", "142"),
    ("--pilot", "3", "--warp", "--seed", "143"),
    ("--pilot", "4", "--warp", "--seed", "144"),
    ("--pilot", "2", "--coins", "2", "--rich", "--seed", "145"),
    ("--pilot", "3", "--coins", "2", "--rich", "--warp", "--seed", "146"),
    ("--pilot", "4", "--coins", "1", "--warp", "--seed", "89"),
    ("--pilot", "1", "--coins", "2", "--warp", "--seed", "85"),
)


def _checks(flights: int) -> list[tuple[str, list[str]]]:
    checks = [
        ("level loads", ["level_load_check.py"]),
        ("name entry", ["name_entry_check.py"]),
        ("forcefields", ["forcefield_check.py"]),
        ("secret rooms", ["secret_check.py"]),
        ("thief", ["thief_walk.py"]),
        ("dragon", ["dragon_walk.py"]),
    ]
    checks += [(f"sweep {sweep}", ["rom_sweeps.py", sweep])
               for sweep in ("walk", "scan", "routes", "reflect", "exits", "shots")]
    demos = (("none", _TRACES / "demo-state" / "20261031" / "trace.txt"),
             *((poke, _TRACES / "poked" / f"{poke}.txt") for poke in ("families", "lobbers", "death")))
    checks += [(f"demo {poke}", ["demo_compare.py", "compare", str(trace), "--poke", poke])
               for poke, trace in demos if trace.is_file()]
    checks += [(f"flight {' '.join(args)}", ["game_run.py", "--frames", "30000", *args])
               for args in _FLIGHTS[:flights]]
    return checks


def _run(name: str, argv: list[str], out: Path) -> tuple[str, int, float, str]:
    env = {**os.environ, "PYTHONPATH": os.pathsep.join((str(_ROOT / "src"), str(_ROOT / "tools")))}
    started = time.perf_counter()
    result = subprocess.run(
        [sys.executable, "-X", "utf8", str(_ROOT / "tools" / argv[0]), *argv[1:]],
        cwd=_ROOT, env=env, capture_output=True, check=False, text=True, encoding="utf-8", errors="replace",
    )
    seconds = time.perf_counter() - started
    text = result.stdout + result.stderr
    (out / (name.replace(" ", "_").replace("-", "") + ".txt")).write_text(text, encoding="utf-8")
    lines = [line for line in text.splitlines() if line.strip()]
    return name, result.returncode, seconds, lines[-1].strip() if lines else ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--flights", type=int, default=0, help=f"up to {len(_FLIGHTS)} lockstep flights")
    parser.add_argument("--out", type=Path, default=_ROOT / "check_all_out")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    checks = _checks(args.flights)
    started = time.perf_counter()
    failed = 0
    with concurrent.futures.ThreadPoolExecutor(len(checks)) as pool:
        futures = [pool.submit(_run, name, argv, args.out) for name, argv in checks]
        for future in concurrent.futures.as_completed(futures):
            name, code, seconds, last = future.result()
            failed += code != 0
            print(f"{'FAIL' if code else 'ok  '} {seconds:6.0f}s  {name}: {last[:100]}", flush=True)
    print(f"{len(checks)} checks, {failed} failed, {time.perf_counter() - started:.0f}s; output in {args.out}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
