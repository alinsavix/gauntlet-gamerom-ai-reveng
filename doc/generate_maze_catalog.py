#!/usr/bin/env python3
"""Generate/check the machine-readable row10.bin maze catalog."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import re
import struct
from pathlib import Path


ROM_BASE = 0x38000
MAZE_COUNT = 116
EXPECTED_SHA1 = "e4a36380f4a6394ad5cfb5aff5d7c8b352232d3d"
FIELDS = (
    "maze",
    "bank",
    "pointer",
    "file_offset",
    "record_size",
    "decoder_bytes_consumed",
    "terminator_offset",
    "padding_to_next_pointer",
    "secret_trick",
    "level_flags",
    "playfield_patterns",
    "playfield_colors",
    "htype1",
    "htype2",
    "vtype1",
    "vtype2",
)


def _decoder_end(rom: bytes, start: int) -> tuple[int, int]:
    """Return (cursor, file position) when the game decoder reaches 0x400."""
    cursor = 0x20
    pos = start + 0x0B
    contexts = (rom[start + 7], rom[start + 9], rom[start + 8], rom[start + 10])

    while cursor < 0x400:
        token = rom[pos]
        pos += 1
        token_class = token & 0xC0

        if token_class == 0x00:
            cursor += 1
        elif token_class == 0x40:
            context = contexts[(token >> 4) & 3]
            count = (token & 0x0F) + 1
            mode = context & 0xC0
            if mode == 0 and (token & 0x10):
                cursor += 1  # vertical writer; main cursor advances one column
            elif mode == 0:
                cursor += count
            else:
                cursor += count + 1
        elif token_class == 0x80:
            if token & 0x20:
                cursor += 1 if token & 0x10 else (token & 0x0F) + 1
            else:
                cursor += (token & 0x1F) + 1
        else:
            cursor += (token & 0x1F) + 1
            if token & 0x20:
                cursor += 1

    return cursor, pos


def generate(rom: bytes) -> str:
    digest = hashlib.sha1(rom).hexdigest()
    if digest != EXPECTED_SHA1:
        raise ValueError(f"row10.bin SHA-1 {digest} != expected {EXPECTED_SHA1}")
    if len(rom) != 0x8000:
        raise ValueError(f"row10.bin size {len(rom):#x} != 0x8000")

    pointers = [struct.unpack_from(">I", rom, 0x0C + 4 * i)[0] for i in range(MAZE_COUNT + 1)]
    if pointers[-1] != 0x3FE48:
        raise ValueError(f"pointer-table end sentinel {pointers[-1]:#x} != 0x3fe48")
    bank_bytes = rom[0x7FE0:0x8000]

    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()

    for maze in range(MAZE_COUNT):
        pointer = pointers[maze]
        next_pointer = pointers[maze + 1]
        start = pointer - ROM_BASE
        next_start = next_pointer - ROM_BASE
        bank = (bank_bytes[maze // 4] >> ((maze % 4) * 2)) & 3
        expected_bank = start // 0x2000
        if bank != expected_bank:
            raise ValueError(f"maze {maze}: bank table {bank} != pointer bank {expected_bank}")

        cursor, decoder_end = _decoder_end(rom, start)
        if cursor < 0x400:
            raise ValueError(f"maze {maze}: decoder stopped early at {cursor:#x}")
        if rom[decoder_end] != 0:
            raise ValueError(f"maze {maze}: missing trailing zero at {decoder_end:#x}")
        padding = next_start - (decoder_end + 1)
        if padding < 0:
            raise ValueError(f"maze {maze}: decoder overlaps next record by {-padding} bytes")

        writer.writerow(
            {
                "maze": maze,
                "bank": bank,
                "pointer": f"0x{pointer:05X}",
                "file_offset": f"0x{start:04X}",
                "record_size": decoder_end + 1 - start,
                "decoder_bytes_consumed": decoder_end - start,
                "terminator_offset": f"0x{decoder_end:04X}",
                "padding_to_next_pointer": padding,
                "secret_trick": f"0x{rom[start]:02X}",
                "level_flags": f"0x{struct.unpack_from('>I', rom, start + 1)[0]:08X}",
                "playfield_patterns": f"0x{rom[start + 5]:02X}",
                "playfield_colors": f"0x{rom[start + 6]:02X}",
                "htype1": f"0x{rom[start + 7]:02X}",
                "htype2": f"0x{rom[start + 8]:02X}",
                "vtype1": f"0x{rom[start + 9]:02X}",
                "vtype2": f"0x{rom[start + 10]:02X}",
            }
        )

    return output.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail if the checked-in CSV differs")
    args = parser.parse_args()

    doc_dir = Path(__file__).resolve().parent
    root = doc_dir.parent
    catalog_path = doc_dir / "maze_catalog.csv"
    generated = generate((root / "row10.bin").read_bytes())

    if args.check:
        existing = catalog_path.read_text() if catalog_path.exists() else ""
        if existing != generated:
            raise SystemExit("maze_catalog.csv is stale; run doc/generate_maze_catalog.py")
        csv_rows = {int(row["maze"]): row for row in csv.DictReader(io.StringIO(existing))}
        markdown_rows: dict[int, tuple[int, int]] = {}
        for line in (doc_dir / "06_maze_catalog.md").read_text().splitlines():
            if not re.match(r"^\|\s*\d+\s*\|", line):
                continue
            parts = [part.strip() for part in line.strip().strip("|").split("|")]
            if len(parts) >= 4 and parts[2].isdigit() and parts[3].startswith("0x"):
                markdown_rows[int(parts[0])] = (int(parts[2]), int(parts[3], 16))
        for maze in range(MAZE_COUNT):
            expected = (int(csv_rows[maze]["bank"]), int(csv_rows[maze]["file_offset"], 16))
            if markdown_rows.get(maze) != expected:
                raise SystemExit(f"06_maze_catalog.md row {maze} differs from maze_catalog.csv")
        print("maze_catalog.csv: verified 116 records and Markdown bank/offset rows")
        return 0

    catalog_path.write_text(generated)
    print(f"wrote {catalog_path} (116 records)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
