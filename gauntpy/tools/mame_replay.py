"""Replay a lockstep flight on MAME and find where real timing parts from the harness.

    python tools/mame_replay.py --pilot 2 --warp --seed 142 --frames 3000

tools/game_run.py runs the ROM under Unicorn one main-loop pass per frame, with VBLANK just
before each pass, and shows gauntpy matching it. A real board can overrun a frame, and then
VBLANK lands inside a pass. This flies the same flight, then has MAME boot normally, take the
harness ROM's RAM while its loop waits for VBLANK, and play the flight's input pass by pass.
Each pass's records and seed are compared with the harness's, and the first difference is
reported with the VBLANKs MAME counted, which is what shows an overrun.

The copy leaves MAME its own stack, OS words (0x904F00 up) and sound handshake, since its
sound board is real. Needs GEX_ROM_DIR, the ROMs ``rom_exec.py`` needs, MAME (``--mame``,
``MAME_EXE``) and its ROM path (``--rompath``, ``MAME_ROMPATH``).
"""

from __future__ import annotations

import argparse
import hashlib
import os
import random
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import game_run  # noqa: E402

_REPO = Path(__file__).resolve().parents[2]
_LUA = Path(__file__).resolve().with_name("mame_replay.lua")
# What the replay copies into MAME: playfield, records and game words up to the stack, the
# alpha RAM with its trailing words, and color RAM, less the sound queue and handshake.
_IMAGE = ((0x900000, 0x90404A), (0x904055, 0x9049ED), (0x9049F6, 0x904C01),
          (0x905000, 0x905FFF), (0x910000, 0x9107FF))
_TABLES = (0x902000, 0x903800, 0x902800, 0x903000, 0x904066)   # picture, link, H, V, state


def _image(machine) -> bytes:
    out = bytearray()
    for start, end in _IMAGE:
        start &= ~1
        length = ((end + 1) & ~1) - start
        out += struct.pack(">II", start, length) + bytes(machine.cpu.mem_read(start, length))
    return bytes(out)


def _words(machine) -> list[tuple[int, bytes]]:
    return [(start & ~1, bytes(machine.cpu.mem_read(start & ~1, ((end + 1) & ~1) - (start & ~1))))
            for start, end in _IMAGE]


def _pokes(before: list[tuple[int, bytes]], after: list[tuple[int, bytes]]) -> list[tuple[int, int]]:
    """The words a warp or a score poke changed on the harness's side, to make on MAME's too."""
    out = []
    for (start, old), (_, new) in zip(before, after):
        if old == new:
            continue
        for offset in range(0, len(old), 2):
            if old[offset:offset + 2] != new[offset:offset + 2] and start + offset != 0x904916:
                out.append((start + offset, int.from_bytes(new[offset:offset + 2], "big")))
    return out


def _digest(tables: list[bytes], seed: int, overflow: int) -> bytes:
    """The records, the seed, and frame_overflow, which a real overrun sets (0x42B4E)."""
    return hashlib.blake2b(b"".join(tables) + struct.pack(">HH", seed, overflow), digest_size=16).digest()


def _rom_tables(machine) -> list[bytes]:
    return [bytes(machine.cpu.mem_read(base, 2048)) for base in _TABLES]


def fly(args, stop: int | None = None):
    """The flight: its input per pass, and the harness ROM's digest after each pass."""
    lockstep = game_run.Lockstep(args.seed, args.settings, args.pricing)
    pilot = game_run.Pilot(random.Random(args.seed), args.pilot, args.coins, args.dragon, args.secret, args.stall,
                           args.powers, deep=args.warp or args.dragon or args.secret or args.walls, walls=args.walls)
    image = _image(lockstep.machine)
    inputs, digests, overflows = [], [], []
    pokes: dict[int, list[tuple[int, int]]] = {}       # after pass N: (address, word)
    try:
        for frame in range(1, (stop or args.frames) + 1):
            if args.rich and frame == 100:
                before = _words(lockstep.machine)
                for index, player in enumerate(lockstep.state.players):
                    if player.active:
                        lockstep.set_score(index, 3_000_000 + index * 1000)
                pokes.setdefault(frame - 1, []).extend(_pokes(before, _words(lockstep.machine)))
            raw, coins = pilot.inputs(frame, lockstep.state)
            for player in coins:
                lockstep.coin(player)
            lockstep.step(raw)
            inputs.append((raw, coins))
            overflow = lockstep.machine.r16(0x904916)
            overflows.append((overflow, lockstep.state.levelnum_current, int(lockstep.state.game_mode)))
            digests.append(_digest(_rom_tables(lockstep.machine), lockstep.machine.r16(0x904BFC),
                                   0 if args.timing else overflow))
            if args.warp or args.dragon or args.secret or args.stall or args.powers or args.walls:
                before = _words(lockstep.machine)
                pilot.warp(lockstep, frame)
                changed = _pokes(before, _words(lockstep.machine))
                if changed:
                    pokes.setdefault(frame, []).extend(changed)
        return image, inputs, digests, lockstep, overflows, pokes
    except BaseException:
        lockstep.close()
        raise


def _fingerprint(image: bytes, inputs, pokes) -> str:
    """What a trace was captured from: a saved trace is only reused for the same flight."""
    return hashlib.blake2b(repr((image, inputs, sorted(pokes.items()))).encode(), digest_size=12).hexdigest()


def capture(args, image: bytes, inputs, pokes, trace: Path) -> None:
    with tempfile.TemporaryDirectory() as work:
        work = Path(work)
        for name in ("cfg", "nvram"):
            shutil.copytree(_REPO / name, work / name)
        shutil.copy(_LUA, work / _LUA.name)
        (work / "image.bin").write_bytes(image)
        with open(work / "input.txt", "w", encoding="ascii") as out:
            for raw, coins in inputs:
                out.write(" ".join(f"{word:04x}" for word in raw))
                out.write("".join(f" {player:x}" for player in coins) + "\n")
        with open(work / "pokes.txt", "w", encoding="ascii") as out:
            out.writelines(f"{number:x} {address:x} {word:04x}\n"
                           for number, words in sorted(pokes.items()) for address, word in words)
        env = {**os.environ, "REPLAY_IMAGE": str(work / "image.bin"), "REPLAY_POKES": str(work / "pokes.txt"),
               "REPLAY_DUMP": str(args.dump if args.dump is not None else -1),
               "REPLAY_INPUT": str(work / "input.txt"), "REPLAY_PASSES": str(len(inputs))}
        with open(trace, "w", encoding="utf-8") as out:
            out.write(f"FLIGHT,{_fingerprint(image, inputs, pokes)}" + "\n")
            out.flush()
            subprocess.run(
                [args.mame, "gaunt2", "-rompath", args.rompath, "-autoboot_script", _LUA.name,
                 "-window", "-nothrottle", "-sound", "none", "-skip_gameinfo",
                 "-seconds_to_run", str(60 + len(inputs) // 30)],
                cwd=work, stdout=out, stderr=subprocess.STDOUT, env=env, check=False,
                timeout=args.timeout,
            )


def passes(trace: Path):
    """Each pass's end: ``(pass, seed, mode, overflow, level, vblanks, records)``."""
    records: dict[int, tuple[int, ...]] = {}
    current = None
    with open(trace, encoding="utf-8", errors="replace") as lines:
        for line in lines:
            fields = line.rstrip().split(",")
            if fields[0] == "P":
                sample = (int(fields[1]), *(int(x, 16) for x in fields[2:6]), int(fields[6]))
                if current is not None and sample[0] != current[0]:
                    yield (*current, records)
                current = sample
            elif fields[0] == "M" and current is not None:
                records[int(fields[1])] = tuple(int(x, 16) for x in fields[2:7])
    if current is not None:
        yield (*current, records)


def _mame_tables(records: dict[int, tuple[int, ...]]) -> list[bytes]:
    columns = [[0] * 1024 for _ in range(5)]
    for slot, (picture, link, h, v, word) in records.items():
        for column, value in zip(columns, (picture, link, h, v, word)):
            column[slot] = value
    return [struct.pack(">1024H", *column) for column in columns]


def _dump(args, image: bytes, inputs, pokes) -> int:
    """MAME's game RAM after pass ``--dump`` against the harness's, word by word."""
    with tempfile.TemporaryDirectory() as work:
        trace = Path(work) / "trace.txt"
        capture(args, image, inputs[:args.dump + 1], {k: v for k, v in pokes.items() if k <= args.dump}, trace)
        mame = {}
        with open(trace, encoding="utf-8", errors="replace") as lines:
            for line in lines:
                if line.startswith("D,"):
                    _, start, words = line.rstrip().split(",")
                    start = int(start, 16)
                    for i in range(0, len(words), 4):
                        mame[start + i // 2] = int(words[i:i + 4], 16)
    _, _, _, rom, _, _ = fly(args, stop=args.dump)
    try:
        wrong = [(address, rom.machine.r16(address), word) for address, word in sorted(mame.items())
                 if rom.machine.r16(address) != word]
    finally:
        rom.close()
    print(f"{len(wrong)} words differ after pass {args.dump} (address: harness/MAME)")
    for address, ours, theirs in wrong[:60]:
        print(f"  {address:#x}: {ours:#06x}/{theirs:#06x}")
    return 0


def _report_timing(timing: list[tuple[int, int, int, int, int]]) -> None:
    if not timing:
        return
    print(f"frame_overflow differs on {len(timing)} passes (pass: harness/MAME, level, mode):")
    for number, ours, theirs, level, mode in timing[:40]:
        print(f"  {number}: {ours}/{theirs} level {level} mode {mode:#06x}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--frames", type=int, default=3000)
    parser.add_argument("--pilot", type=int, default=2)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--warp", action="store_true")
    parser.add_argument("--coins", type=int)
    parser.add_argument("--rich", action="store_true")
    parser.add_argument("--dragon", action="store_true", help="warp only to dragon mazes, and fight it")
    parser.add_argument("--secret", action="store_true", help="win the secret room on each level past 6")
    parser.add_argument("--stall", action="store_true", help="let each level time out, so its walls become exits")
    parser.add_argument("--powers", action="store_true", help="give the heroes permanent powers on each level")
    parser.add_argument("--walls", action="store_true", help="warp only to mazes with movable walls, and push them")
    parser.add_argument("--settings", type=lambda text: int(text, 0))
    parser.add_argument("--pricing", type=lambda text: int(text, 0))
    parser.add_argument("--dump", type=int, help="print the game RAM that differs after this pass")
    parser.add_argument("--timing", action="store_true",
                        help="compare records and seed only, and list where frame_overflow differs")
    parser.add_argument("--trace", type=Path, help="keep MAME's trace here (and reuse it if present)")
    parser.add_argument("--mame", default=os.environ.get("MAME_EXE", r"C:\Portable\MAME\mame.exe"))
    parser.add_argument("--rompath", default=os.environ.get("MAME_ROMPATH", r"D:\users\alinsa\LaunchBox\Games\Arcade"))
    parser.add_argument("--timeout", type=int, default=3600)
    args = parser.parse_args()

    image, inputs, digests, lockstep, overflows, pokes = fly(args)
    lockstep.close()
    if args.dump is not None:
        return _dump(args, image, inputs, pokes)
    with tempfile.TemporaryDirectory() as work:
        trace = args.trace or Path(work) / "trace.txt"
        stale = False
        if trace.is_file():
            with open(trace, encoding="utf-8") as saved:
                stale = not saved.readline().startswith(f"FLIGHT,{_fingerprint(image, inputs, pokes)}")
        if stale:
            print(f"{trace} was captured from another flight; capturing again")
        if stale or not trace.is_file():
            capture(args, image, inputs, pokes, trace)
        last_vblanks = 0
        compared = overruns = 0
        timing: list[tuple[int, int, int, int, int]] = []
        for number, seed, mode, overflow, level, vblanks, records in passes(trace):
            if not 1 <= number <= len(digests):
                continue
            overran = vblanks - last_vblanks > 1
            overruns += overran
            last_vblanks = vblanks
            compared = number
            if args.timing and overflow != overflows[number - 1][0]:
                timing.append((number, overflows[number - 1][0], overflow, level, mode))
            if _digest(_mame_tables(records), seed, 0 if args.timing else overflow) == digests[number - 1]:
                continue
            print(f"first difference at pass {number}: MAME seed {seed:#06x} mode {mode:#06x} "
                  f"overflow {overflow} level {level}, {'after an overrun' if overran else 'no overrun'}")
            _report_timing(timing)
            _, _, _, rom, _, _ = fly(args, stop=number)
            try:
                rom_seed = rom.machine.r16(0x904BFC)
                if rom_seed != seed:
                    print(f"  seed: harness {rom_seed:#06x} MAME {seed:#06x}")
                rom_overflow = rom.machine.r16(0x904916)
                if rom_overflow != overflow:
                    print(f"  frame_overflow: harness {rom_overflow} MAME {overflow}")
                ours = _rom_tables(rom.machine)
                theirs = _mame_tables(records)
                names = ("picture", "link", "H", "V", "state")
                shown = 0
                for slot in range(1024):
                    pairs = [(name, struct.unpack_from(">H", a, 2 * slot)[0], struct.unpack_from(">H", b, 2 * slot)[0])
                             for name, a, b in zip(names, ours, theirs)]
                    wrong = [f"{name} {a:#x}/{b:#x}" for name, a, b in pairs if a != b]
                    if wrong and shown < 12:
                        print(f"  slot {slot:#x} (harness/MAME): {', '.join(wrong)}")
                        shown += 1
            finally:
                rom.close()
            return 1
        _report_timing(timing)
        print(f"{compared} passes, no differences; {overruns} of them overran on MAME")
        return 0 if compared == len(digests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
