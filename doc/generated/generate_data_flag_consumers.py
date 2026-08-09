#!/usr/bin/env python3
"""Attribute every named game-ROM data flag to the code that consumes it.

Both `generate_ram_operand_report.py` and `generate_os_data_xrefs.py` extract
*literal* operands, which can never see a table reached through a base pointer
plus a signed displacement -- e.g. `lea 0x580fc,a0; move.w -0x34(a0,d1.w)`
touches 0x580C8, but 0x580C8 appears in no instruction. That blind spot is
exactly how a data table can carry a wrong semantic label for years: nothing
mechanically ties the label to a reader, so the label is never contradicted.

This generator closes the gap. For each documented game function it runs a
tiny straight-line resolver over the disassembly: it binds an address register
when it sees `lea 0xADDR,aN` (or `movea.l #imm,aN`), and when a later indexed
access `disp(aN,Xn)` uses that register it records the *effective* base
`regbase + disp` as a reference. Absolute operands (`0xADDR.l`) are recorded
directly. Every reference is mapped to the flag whose byte range covers it, so
each flag ends up with the set of functions that actually read it.

Output columns (`data_flag_consumers.csv`):
  address, flag_name, size_bytes, confidence, classification, consumers,
  sample_sites, review

  classification: direct    -- named by an absolute operand or lea/movea base
                  resolved  -- reached only via base+displacement (the 0x580C8
                              class; the interesting one)
                  indirect  -- carries no operand of its own but is pointed to
                              by a referenced pointer table, whose consumers it
                              inherits (sample_sites shows `ptr:<table>`)
                  unreferenced -- no reader found (dead data, padding, or a
                              computed-jump/PC-relative table this static pass
                              cannot see)
  review:  unreferenced_unexpected -- unreferenced and not obviously padding,
                              dead, reserved, a jump table, or pointer-referenced

The `review` column is advisory: it is the human worklist, not a build gate.
The build fails only on r2 analysis errors or a stale committed CSV.

Two passes give the coverage. (1) Each function is disassembled over its whole
`[start, next_function)` byte range -- a LINEAR sweep, not r2's CFG -- so the
`movea.l #imm` table loads hiding in computed-jump arms (monster_playerhit's
contact-damage arm at 0x497AE is the case that forced this) are seen. (2) Every
referenced table's longwords are read; any that land in another table's range
are pointer entries, and the pointed-to table inherits the pointer table's
consumers. A domain-mismatch heuristic -- flag a table whose name names a
subsystem none of its consumers do -- was tried and dropped: table names
describe the data domain while function names describe the action, so
legitimate splits like `*_palette` read by `init_display` drowned the signal.
The `consumers` column surfaces genuine mismatches for human review instead.

Scope and limits. The resolver follows a base only when it is a plain
`lea 0xADDR,aN` or `movea.l #imm,aN`; it does not chase a base computed by
arithmetic, a biased base plus a runtime index, or an overlapping sub-view.
The handful that remain `unreferenced_unexpected` are exactly those --
`potion_effect_matrix` (biased base `lea 0x5D978`, index `type<<4`, so 0x5DA98
never appears literally), `special_object_tile_numbers` (overlapping view),
`joystick_direction_bitmasks` (values self-evidently direction masks; consumer
untraced). The label therefore means "no reader found by this pass, confirm by
hand", not "provably dead". The value is bounding the manual audit to a few
tables instead of all ~350 and -- via the `consumers` column -- pinning every
resolvable table to the function and site that reads it, so a wrong semantic
label stands out against its real consumer (the miss that started this:
`player_collision_size` read only by `monster_find_and_shoot`).
"""

from __future__ import annotations

import argparse
import bisect
import csv
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# Game-ROM data lives in the row76 image window.
ROM_START = 0x40000
ROM_END = 0x5FFFF

# How many instructions a `lea`/`movea` base binding stays trustworthy. A base
# is often loaded once near the top of a function and used far below, so the
# window is generous; correctness comes from clearing the binding the moment
# the register is clobbered, not from the window.
FRESHNESS = 160

LINE_RE = re.compile(r"0x([0-9a-fA-F]{8})\s+([0-9a-fA-F]+)\s+(\S.*?)\s*$")
LEA_RE = re.compile(r"^lea(?:\.\w)?\s+0x([0-9a-fA-F]+)\.[wl],\s*(a[0-7])$")
# `movea.l #imm,aN` (opcode 2x7C) loads the address itself; r2 prints it bare,
# with neither `#` nor a `.l` suffix -- indistinguishable in text from the
# absolute form `movea.l (xxx).l,aN` (opcode 2x79) that loads the *pointer*
# stored at that address. The opcode word disambiguates them.
MOVEA_RE = re.compile(r"^movea\.l\s+#?0x([0-9a-fA-F]+),\s*(a[0-7])$")
ABS_RE = re.compile(r"0x([0-9a-fA-F]+)\.[wl]\b")
# optional signed displacement, then (aN) with an optional index register
DISP_RE = re.compile(r"(-?0x[0-9a-fA-F]+)?\((a[0-7])(?:,\s*[ad][0-7]\.[bwl])?\)")
AUTO_RE = re.compile(r"\((a[0-7])\)\+|-\((a[0-7])\)")

# Names whose data is reached through a pointer table, a computed jump, or the
# OS/boot path rather than a direct code operand -- being "unreferenced" by this
# static game-code pass is expected for them and must not raise a review flag.
# (A domain-mismatch heuristic -- flag a table whose name names a subsystem none
# of its consumers do -- was tried and dropped: table names describe the data
# domain while function names describe the action, so legitimate splits like
# `*_palette` read by `init_display` drowned the signal. The `consumers` column
# surfaces genuine mismatches for human review instead.)
EXPECTED_UNREF = re.compile(
    r"pad_|dead_|reserved_|unused|residue|_jmp|jumptbl|epilogue|fragment|"
    r"_pad$|truncated|copyright|signature|morse|"
    r"_string|_ptrs|_ptr$|_chain|_message|_text|_label|_name|_desc|_records|"
    r"_stream|_records$|instruction|speech|_tip|hint|credit|portrait|glyph|"
    r"logo|alphabet|anim_tiles|_hook|_slot|checksum|rom_type|difficulty|"
    r"eeprom|_fill_value|hook_slot|unreferenced",
    re.IGNORECASE,
)


def parse_functions(loader_text: str) -> list[tuple[int, str]]:
    # Every analysed function, OS included: a game-ROM table can be read by OS
    # code (e.g. the boot/self-test path reads the ROM header slots), so the
    # caller universe must not be limited to the game code segment.
    by_address: dict[int, str] = {}
    for addr_text, name in re.findall(r"^af\+\s+(0x[0-9a-fA-F]+)\s+(\S+)", loader_text, re.MULTILINE):
        by_address.setdefault(int(addr_text, 16), name)
    return sorted(by_address.items())


# Upper bound on how many bytes past a function's start to sweep, for the last
# function in a segment or one followed by a large data gap. Comfortably larger
# than any real function here.
SWEEP_LIMIT = 0x2000


def analyze_one(root: Path, loader: Path, item: tuple[int, int, str]) -> tuple[int, str, str, str]:
    start, end_excl, name = item
    # Linear disassembly of the whole [start, next_function) byte range, NOT
    # r2's CFG (`af;pdf`). A CFG walk drops the arms of a computed-jump dispatch
    # -- exactly where a `movea.l #imm` table load hides (monster_playerhit's
    # contact-damage arm at 0x497AE being the case that motivated this) -- so
    # the function would look like it reads nothing. Sweeping bytes decodes a
    # little embedded jump-table data as junk instructions, but that only adds
    # spurious refs (visible in `consumers`), never hides a real one.
    length = min(end_excl - start, SWEEP_LIMIT)
    command = [
        "r2", "-q", "-n", "-e", "scr.color=0", "-e", "asm.flags=false",
        "-e", "asm.sub.names=false", "-e", "asm.lines=false",
        "-i", str(loader),
        "-c", f"s 0x{start:x}; pD {length}",
        "-c", "q", "malloc://1",
    ]
    result = subprocess.run(command, cwd=root, text=True, capture_output=True)
    errors = "; ".join(
        line for line in result.stderr.splitlines() if line.startswith(("ERROR", "FATAL"))
    )
    return start, name, result.stdout, errors


def resolve_function(name: str, text: str,
                     direct: dict[int, set[str]], resolved: dict[int, set[str]]) -> None:
    """Straight-line register-base resolution over one function's disassembly."""
    regs: dict[str, tuple[int, int] | None] = {f"a{i}": None for i in range(8)}
    for i, raw in enumerate(text.splitlines()):
        m = LINE_RE.search(raw)
        if not m:
            continue
        site = int(m.group(1), 16)
        opword = int(m.group(2)[:4], 16) if len(m.group(2)) >= 4 else 0
        instr = m.group(3)
        # split mnemonic / operands
        sp = instr.find(" ")
        operands = instr[sp + 1:] if sp >= 0 else ""

        # (a) references visible in THIS instruction, using the CURRENT bindings
        for token in ABS_RE.findall(operands):
            target = int(token, 16)
            if ROM_START <= target <= ROM_END:
                direct.setdefault(target, set()).add(f"{name}@0x{site:05X}")
        for disp_text, reg in DISP_RE.findall(operands):
            binding = regs.get(reg)
            if binding is None:
                continue
            value, bound_at = binding
            if i - bound_at > FRESHNESS:
                continue
            disp = int(disp_text, 16) if disp_text else 0
            target = value + disp
            if ROM_START <= target <= ROM_END:
                resolved.setdefault(target, set()).add(f"{name}@0x{site:05X}")

        # (b) update bindings produced BY this instruction
        lea = LEA_RE.match(instr)
        if lea:
            regs[lea.group(2)] = (int(lea.group(1), 16), i)
            continue
        mov = MOVEA_RE.match(instr)
        if mov:
            value = int(mov.group(1), 16)
            reg = mov.group(2)
            # 2x7C = immediate (aN := address); 2x79 = absolute (aN := *address)
            if "#" in operands or (opword & 0xF1FF) == 0x207C:
                regs[reg] = (value, i)
                if ROM_START <= value <= ROM_END:
                    direct.setdefault(value, set()).add(f"{name}@0x{site:05X}")
            else:
                regs[reg] = None
                if ROM_START <= value <= ROM_END:
                    direct.setdefault(value, set()).add(f"{name}@0x{site:05X}")
            continue
        # (c) clobbers: auto inc/dec, or a bare address-register destination
        for a, b in AUTO_RE.findall(operands):
            regs[a or b] = None
        dst = operands.rsplit(",", 1)[-1].strip() if "," in operands else operands.strip()
        if re.fullmatch(r"a[0-7]", dst):
            regs[dst] = None


def build_rows(root: Path) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    doc = root / "doc"
    loader = doc / "gauntlet_loader.r2"
    loader_text = loader.read_text()
    functions = parse_functions(loader_text)
    # Game-ROM image (base ROM_START), read to follow pointer-table entries.
    rom = (root / "row76.bin").read_bytes()

    # The curated catalog of non-code data flags (address, size, name,
    # confidence) is the audit universe -- the same 352 rows the rest of the
    # docs track, not the raw loader flag set (which mixes in string labels).
    flags: list[tuple[int, int, str]] = []
    confidence: dict[int, str] = {}
    with (doc / "generated" / "rom_flag_reconciliation.csv").open(newline="") as stream:
        for row in csv.DictReader(stream):
            address = int(row["address"], 16)
            if not ROM_START <= address <= ROM_END:
                continue
            size = max(int(row["size_bytes"]), 1)
            flags.append((address, address + size - 1, row["flag_name"]))
            confidence[address] = row.get("confidence", "")
    flags.sort()

    # Each function is swept over [start, next_function_start), capped.
    extents = [
        (start, functions[i + 1][0] if i + 1 < len(functions) else start + SWEEP_LIMIT, name)
        for i, (start, name) in enumerate(functions)
    ]

    direct: dict[int, set[str]] = {}
    resolved: dict[int, set[str]] = {}
    failures: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = executor.map(lambda item: analyze_one(root, loader, item), extents)
        for function_address, name, output, errors in results:
            if errors:
                failures.append({
                    "function_address": f"0x{function_address:05X}",
                    "name": name,
                    "error": errors,
                })
                continue
            resolve_function(name, output, direct, resolved)

    def owners(start: int, end: int, table: dict[int, set[str]]) -> set[str]:
        found: set[str] = set()
        for addr, uses in table.items():
            if start <= addr <= end:
                found |= uses
        return found

    # First pass: the code that names each table via an operand or a resolved
    # base+displacement. Keyed by address; aliases at one address (e.g.
    # demo_input_streams and demo_player0_input_stream) share this analysis but
    # each still gets its own output row below.
    info: dict[int, dict[str, object]] = {}
    for start, end, name in flags:
        if start in info:
            continue
        info[start] = {
            "end": end, "name": name,
            "d_uses": owners(start, end, direct),
            "r_uses": owners(start, end, resolved),
            "indirect": set(), "via": "",
        }

    # Second pass: pointer-table indirection. A `*_ptrs` table is read by code as
    # a base, but the tables it *points to* carry no operand of their own. Read
    # each referenced table's longwords; any that land in another table's range
    # are pointer entries, so the pointed-to table inherits the pointer table's
    # consumers. A game-ROM address encodes as 0x0004xxxx/0x0005xxxx, which plain
    # data almost never is, so coincidental edges are rare.
    starts = sorted(info)
    def covering(addr: int) -> int | None:
        i = bisect.bisect_right(starts, addr) - 1
        if i >= 0 and info[starts[i]]["end"] >= addr >= starts[i]:  # type: ignore[operator]
            return starts[i]
        return None

    for start in starts:
        rec = info[start]
        consumers = {u.split("@", 1)[0] for u in rec["d_uses"] | rec["r_uses"]}  # type: ignore[operator]
        if not consumers:
            continue
        end = rec["end"]
        for off in range(start, end - 2, 2):
            image_off = off - ROM_START
            if not 0 <= image_off <= len(rom) - 4:
                continue
            pointer = int.from_bytes(rom[image_off:image_off + 4], "big")
            target = covering(pointer)
            if target is None or target == start:
                continue
            tgt = info[target]
            if tgt["d_uses"] or tgt["r_uses"]:  # already directly attributed
                continue
            tgt["indirect"].update(consumers)  # type: ignore[union-attr]
            tgt["via"] = rec["name"]  # type: ignore[assignment]

    rows = []
    for start, _end, name in flags:
        rec = info[start]
        d_uses, r_uses = rec["d_uses"], rec["r_uses"]
        indirect = rec["indirect"]
        d_funcs = {u.split("@", 1)[0] for u in d_uses}  # type: ignore[union-attr]
        r_funcs = {u.split("@", 1)[0] for u in r_uses}  # type: ignore[union-attr]

        if d_uses:
            classification, all_funcs, sample = "direct", d_funcs | r_funcs, sorted(d_uses)[:4]
        elif r_uses:
            classification, all_funcs, sample = "resolved", r_funcs, sorted(r_uses)[:4]
        elif indirect:
            classification = "indirect"
            all_funcs = set(indirect)  # type: ignore[arg-type]
            sample = [f"ptr:{rec['via']}"]
        else:
            classification, all_funcs, sample = "unreferenced", set(), []

        review = ""
        if classification == "unreferenced" and not EXPECTED_UNREF.search(name):
            review = "unreferenced_unexpected"

        rows.append({
            "address": f"0x{start:05X}",
            "flag_name": name,
            "size_bytes": str(rec["end"] - start + 1),  # type: ignore[operator]
            "confidence": confidence.get(start, ""),
            "classification": classification,
            "consumers": ";".join(sorted(all_funcs)) or "-",
            "sample_sites": ";".join(sample) or "-",
            "review": review,
        })
    rows.sort(key=lambda r: int(r["address"], 16))
    return rows, failures


FIELDS = ("address", "flag_name", "size_bytes", "confidence",
          "classification", "consumers", "sample_sites", "review")
FAIL_FIELDS = ("function_address", "name", "error")


def write_csv(path: Path, rows: list[dict[str, str]], fields: tuple[str, ...]) -> None:
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    rows, failures = build_rows(here.parent.parent)
    report = here / "data_flag_consumers.csv"
    failure_report = here / "data_flag_consumer_failures.csv"

    if args.check:
        if read_csv(report) != rows or read_csv(failure_report) != failures:
            raise SystemExit("data-flag consumer report is stale; regenerate it")
    else:
        write_csv(report, rows, FIELDS)
        write_csv(failure_report, failures, FAIL_FIELDS)

    counts = {"direct": 0, "resolved": 0, "indirect": 0, "unreferenced": 0}
    for row in rows:
        counts[row["classification"]] += 1
    unref = [r for r in rows if r["review"] == "unreferenced_unexpected"]
    print(
        f"data_flag_consumers.csv: {len(rows)} flags "
        f"({counts['direct']} direct, {counts['resolved']} resolved, "
        f"{counts['indirect']} indirect, {counts['unreferenced']} unreferenced); "
        f"{len(unref)} unreferenced-unexpected; "
        f"{len(failures)} function-analysis failures"
    )
    if failures:
        raise SystemExit("data-flag consumer extraction hit r2 analysis failures")


if __name__ == "__main__":
    main()
