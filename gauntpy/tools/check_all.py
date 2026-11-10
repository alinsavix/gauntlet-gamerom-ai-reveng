"""Run every ROM comparison at once and report one line each.

    python tools/check_all.py               # every tool, the four demo captures if present
    python tools/check_all.py --flights 6   # and six lockstep flights of 30,000 frames

It keeps at most ``--jobs`` processes busy (``GAUNTPY_JOBS``, a quarter of the logical
CPUs unless set; see ``jobs.py``). The slowest tools get a share of that budget for their
own workers and start first; the rest take one each. Every case runs exactly as it does
when the tool is started by hand. The exit status is 1 when any tool reports a difference
or fails, and each tool's full output goes to ``--out``.

Needs GEX_ROM_DIR and the ROMs ``rom_exec.py`` needs.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from jobs import default_jobs  # noqa: E402

_ROOT = Path(__file__).resolve().parents[1]
_TRACES = _ROOT / "traces" / "mame"
# Flights that between them reach deaths, initials, second games, doors and deep levels, and
# from the twelfth on other operator settings and free play.
_FLIGHTS = (
    ("--pilot", "1", "--warp", "--seed", "141"),
    ("--pilot", "2", "--warp", "--seed", "142"),
    ("--pilot", "3", "--warp", "--seed", "143"),
    ("--pilot", "4", "--warp", "--seed", "144"),
    ("--pilot", "2", "--coins", "2", "--rich", "--seed", "145"),
    ("--pilot", "3", "--coins", "2", "--rich", "--warp", "--seed", "146"),
    ("--pilot", "4", "--coins", "1", "--warp", "--seed", "89"),
    ("--pilot", "1", "--coins", "2", "--warp", "--seed", "85"),
    ("--pilot", "2", "--warp", "--seed", "201", "--settings", "0x60FF"),
    ("--pilot", "3", "--warp", "--seed", "202", "--settings", "0x6000"),
    ("--pilot", "2", "--coins", "2", "--rich", "--seed", "203", "--settings", "0x6C90"),
    ("--pilot", "4", "--warp", "--seed", "204", "--settings", "0x6390"),
    ("--pilot", "2", "--coins", "2", "--rich", "--warp", "--seed", "205", "--settings", "0x0090"),
    ("--pilot", "3", "--warp", "--seed", "206", "--pricing", "0"),
    ("--pilot", "4", "--coins", "2", "--rich", "--warp", "--seed", "209", "--pricing", "0"),
)


# These share their cases between workers; the rest run in one process each.
_HEAVY = {"level loads", "secret rooms", "name entry", "thief", "sweep reflect", "sweep shots", "sweep exits",
          "sweep routes"}


class _Budget:
    """A count of busy processes that a check holds while it runs, handed out in turn."""

    def __init__(self, slots: int) -> None:
        self.free = slots
        self.ready = threading.Condition()
        self.issued = 0
        self.serving = 0

    def take(self, slots: int) -> None:
        with self.ready:
            ticket = self.issued
            self.issued += 1
            self.ready.wait_for(lambda: self.serving == ticket and self.free >= slots)
            self.free -= slots
            self.serving += 1
            self.ready.notify_all()

    def give(self, slots: int) -> None:
        with self.ready:
            self.free += slots
            self.ready.notify_all()


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


def _run(name: str, argv: list[str], out: Path, budget: _Budget, slots: int) -> tuple[str, int, float, str]:
    budget.take(slots)
    try:
        return _run_one(name, argv, out, slots)
    finally:
        budget.give(slots)


def _run_one(name: str, argv: list[str], out: Path, slots: int) -> tuple[str, int, float, str]:
    env = {**os.environ, "PYTHONPATH": os.pathsep.join((str(_ROOT / "src"), str(_ROOT / "tools"))),
           "GAUNTPY_JOBS": str(slots)}
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
    parser.add_argument("--flights", type=int, default=0,
                        help=f"up to {len(_FLIGHTS)} lockstep flights; past 8 they vary the operator settings")
    parser.add_argument("--out", type=Path, default=_ROOT / "check_all_out")
    parser.add_argument("--jobs", type=int, default=default_jobs(),
                        help="processes kept busy at once (GAUNTPY_JOBS; a quarter of the CPUs by default)")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    jobs = max(1, args.jobs)
    budget = _Budget(jobs)
    heavy_share = max(1, jobs // 2)
    checks = sorted(_checks(args.flights), key=lambda check: check[0] not in _HEAVY)   # heavy first
    started = time.perf_counter()
    failed = 0
    print(f"{len(checks)} checks, at most {jobs} processes at once", flush=True)
    with concurrent.futures.ThreadPoolExecutor(len(checks)) as pool:
        futures = []
        for name, argv in checks:
            futures.append(pool.submit(_run, name, argv, args.out, budget,
                                       heavy_share if name in _HEAVY else 1))
            time.sleep(0.02)        # each thread takes its ticket in this order
        for future in concurrent.futures.as_completed(futures):
            name, code, seconds, last = future.result()
            failed += code != 0
            print(f"{'FAIL' if code else 'ok  '} {seconds:6.0f}s  {name}: {last[:100]}", flush=True)
    print(f"{len(checks)} checks, {failed} failed, {time.perf_counter() - started:.0f}s; output in {args.out}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
