"""Read each game-RAM variable's access width and array stride from the game ROM's own code.

doc/generated/ram_linear_reconciliation.csv lists every verified code site that names a main-RAM
address. Each site is disassembled with radare2 (on PATH as r2 or radare2):

* a direct access (``move.w d0,$904A0A``, ``clr.b``, ``tst.l``, ``btst.b`` ...) gives its size;
* a pointer load (``movea.l #$904A50,a1`` or ``lea``) is followed to the instructions that use the
  register, until it is overwritten, a call, a jump or a branch away: each use gives a size at the
  base plus its displacement, and an indexed use ``(a1,d3.w)`` gives a stride from how the index
  register was scaled just before (none: 1, ``add.w d3,d3`` once: 2, twice or ``asl #2``: 4).

``python tools/ram_widths.py`` prints every address with the sizes and strides the code uses.
``--check`` compares tools/ram_map.py against them and exits 1 on a disagreement.
"""

from __future__ import annotations

import argparse
import collections
import csv
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[1]
_SITES = _REPO / "doc" / "generated" / "ram_linear_reconciliation.csv"
_ROM = _REPO / "row76.bin"
_GAME_RAM = (0x904000, 0x906000)

_LINE = re.compile(r"0x([0-9a-f]{8})\s+[0-9a-f]+\s+(\S+)\s*(.*)$")
_SIZE = {"b": 1, "w": 2, "l": 4}
_ADDRESS_ONLY = {"lea", "pea", "movea", "jsr", "jmp"}
_STOP = re.compile(r"^(rts|rte|jmp|bra|jsr|bsr|unlk)")


def _r2() -> str:
    for name in ("radare2", "r2"):
        found = shutil.which(name)
        if found and not found.lower().endswith((".bat", ".cmd")):
            return found
    raise SystemExit("ram_widths: radare2 is not on PATH")


def _sites() -> dict[int, list[int]]:
    sites: dict[int, list[int]] = {}
    with _SITES.open(newline="") as stream:
        for row in csv.DictReader(stream):
            address = int(row["literal_address"], 16)
            if _GAME_RAM[0] <= address < _GAME_RAM[1]:
                sites[address] = [int(s, 16) for s in row["linear_sites"].split(";") if s]
    return sites


def _disassemble(pcs: list[int], before: int = 8, after: int = 24) -> dict[int, list[tuple[int, str, str]]]:
    """Each site's instruction, a few before it and the run after it, as (pc, mnemonic, operands)."""
    script = "\n".join(f"?e SITE{pc:x}\npd -{before} @ {pc:#x}\npd {after} @ {pc:#x}" for pc in pcs)
    with tempfile.TemporaryDirectory() as work:
        commands = Path(work) / "sites.r2"
        commands.write_text(script + "\n", encoding="ascii")
        out = subprocess.run([_r2(), "-q", "-a", "m68k", "-m", "0x40000", "-e", "scr.color=0", "-e", "asm.lines=false",
                              "-i", str(commands), str(_ROM)], capture_output=True, text=True, check=False).stdout
    listing: dict[int, list[tuple[int, str, str]]] = {}
    current = None
    for line in out.splitlines():
        if line.startswith("SITE"):
            current = int(line[4:], 16)
            listing[current] = []
            continue
        m = _LINE.search(line)
        if m and current is not None:
            listing[current].append((int(m.group(1), 16), m.group(2), m.group(3).strip()))
    return listing


def _size(mnemonic: str) -> int | None:
    suffix = mnemonic.rsplit(".", 1)[-1] if "." in mnemonic else ""
    return _SIZE.get(suffix)


def _scale(before: list[tuple[int, str, str]], register: str) -> int:
    """How the index register was scaled in the instructions just before its use."""
    scale = 1
    for _, mnemonic, operands in reversed(before):
        ops = [o.strip() for o in operands.split(",")]
        if mnemonic.startswith("add") and ops == [register, register]:
            scale *= 2
        elif mnemonic.startswith(("asl", "lsl")) and len(ops) == 2 and ops[1] == register and ops[0].startswith("0x"):
            scale <<= int(ops[0], 16)
        elif ops and ops[-1] == register and not mnemonic.startswith(("add", "asl", "lsl", "ext", "and")):
            break                                       # the register was loaded here: scaling ends
    return scale


def analyze() -> dict[int, dict[str, collections.Counter]]:
    sites = _sites()
    pcs = sorted({pc for pcs_ in sites.values() for pc in pcs_ if 0x40000 <= pc < 0x60000})
    listing = _disassemble(pcs)
    found: dict[int, dict[str, collections.Counter]] = collections.defaultdict(
        lambda: {"size": collections.Counter(), "stride": collections.Counter()})
    for base, base_sites in sites.items():
        literal = f"{base:#x}"
        for pc in base_sites:
            rows = listing.get(pc, [])
            at = next((i for i, row in enumerate(rows) if row[0] == pc), None)
            if at is None:
                continue
            _, mnemonic, operands = rows[at]
            stem = mnemonic.split(".")[0]
            if literal + ".l" in operands and stem not in _ADDRESS_ONLY:
                size = _size(mnemonic)
                if size:
                    found[base]["size"][size] += 1
                continue
            if stem not in ("movea", "lea") or literal not in operands:
                continue
            register = operands.split(",")[-1].strip()
            for index in range(at + 1, len(rows)):
                _, mnemonic, operands = rows[index]
                for m in re.finditer(r"(-?0x[0-9a-f]+|-?\d+)?\(" + register + r"(?:,\s*(d\d)\.[wl])?\)", operands):
                    displacement = int(m.group(1), 0) if m.group(1) else 0
                    size = _size(mnemonic)
                    if size and mnemonic.split(".")[0] not in _ADDRESS_ONLY:
                        found[base + displacement]["size"][size] += 1
                        if m.group(2):
                            found[base + displacement]["stride"][_scale(rows[:index], m.group(2))] += 1
                if operands.split(",")[-1].strip() == register or _STOP.match(mnemonic) or mnemonic.startswith("b"):
                    break
    return found


def _check(found) -> int:
    sys.path.insert(0, str(_HERE))
    import ram_map

    bad = 0
    fields = [field[:5] for field in ram_map.FIELDS + ram_map.CONVERTED]
    for owner, field, address, size, stride in fields:
        seen = found.get(address)
        if not seen or not seen["size"]:
            print(f"  {field} {address:#x}: the code never names it directly")
            continue
        sizes, strides = set(seen["size"]), set(seen["stride"])
        if size not in sizes:
            bad += 1
            print(f"MISMATCH {field} {address:#x}: map size {size}, code {dict(seen['size'])}")
        if strides and stride not in strides and owner == "player":
            bad += 1
            print(f"MISMATCH {field} {address:#x}: map stride {stride}, code {dict(seen['stride'])}")
    print(f"ram widths: {bad} disagreements with ram_map")
    return bad


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="compare tools/ram_map.py with the code")
    args = parser.parse_args()
    found = analyze()
    if args.check:
        return 1 if _check(found) else 0
    for address in sorted(found):
        sizes, strides = found[address]["size"], found[address]["stride"]
        mixed = " MIXED" if len(sizes) > 1 else ""
        print(f"{address:#x} size {dict(sizes)} stride {dict(strides) or '-'}{mixed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
