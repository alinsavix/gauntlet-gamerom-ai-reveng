#!/usr/bin/env python3
"""Generate and verify the byte-exact top-level row76 ROM region catalog."""

from __future__ import annotations

import argparse
import csv
import hashlib
from pathlib import Path


ROM_BASE = 0x40000
ROM_END = 0x5FFFF
ROM_SHA1 = "decbe6438b3a2618bd7fe79d14be034efadd7ff4"

# Inclusive address ranges. These are physical top-level regions; the two
# executable regions contain the finer code/data/overlap views cataloged in
# 05_data_reference.md and gauntlet.r2.
REGIONS = (
    (0x40000, 0x5561F, "mixed_code_inline_data", "Compiled C/assembly plus inline tables"),
    (0x55620, 0x56E53, "erased_padding", "Solid 0xFF gap"),
    (0x56E54, 0x5FFB1, "mixed_code_data", "Slapstic helpers, later routines, and ROM tables"),
    (0x5FFB2, 0x5FFFD, "erased_padding", "Solid 0xFF end pad"),
    (0x5FFFE, 0x5FFFF, "checksum_trailer", "Final big-endian word 0xE19E"),
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    here = Path(__file__).resolve().parent
    rom = (here.parent.parent / "row76.bin").read_bytes()
    if len(rom) != 0x20000 or hashlib.sha1(rom).hexdigest() != ROM_SHA1:
        raise SystemExit("row76.bin is not the documented 128 KiB target ROM")

    cursor = ROM_BASE
    rows: list[dict[str, str]] = []
    for start, end, kind, description in REGIONS:
        if start != cursor or end < start:
            raise SystemExit(f"non-contiguous region at 0x{start:05X}")
        data = rom[start - ROM_BASE : end - ROM_BASE + 1]
        if kind == "erased_padding" and data != b"\xff" * len(data):
            raise SystemExit(f"non-0xFF byte in padding 0x{start:05X}-0x{end:05X}")
        rows.append(
            {
                "start": f"0x{start:05X}",
                "end_inclusive": f"0x{end:05X}",
                "size_bytes": str(end - start + 1),
                "kind": kind,
                "description": description,
                "confidence": "Verified",
            }
        )
        cursor = end + 1
    if cursor != ROM_END + 1:
        raise SystemExit("region union does not end at 0x5FFFF")
    if rom[-2:] != b"\xe1\x9e":
        raise SystemExit("unexpected final checksum-trailer word")

    output = here / "rom_regions.csv"
    if args.check:
        with output.open(newline="") as stream:
            existing = list(csv.DictReader(stream))
        if existing != rows:
            raise SystemExit("rom_regions.csv is stale; regenerate it")
        print("rom_regions.csv: verified contiguous 0x40000-0x5FFFF union")
        return

    with output.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} rows to {output}")


if __name__ == "__main__":
    main()
