#!/usr/bin/env python3
"""Require canonical confidence labels for every chapter-level finding group."""

from __future__ import annotations

import re
from pathlib import Path


FILES = (
    "01_hardware.md",
    "02_os_rom.md",
    "03_game_rom_structure.md",
    "04_game_subsystems.md",
    "05_data_reference.md",
    "06_maze_catalog.md",
    "07_function_index.md",
)
LABELS = ("Verified", "Strong inference", "Hypothesis", "Unknown", "Contradicted")
LABEL_PATTERN = re.compile(
    r"Confidence:\s*(Verified|Strong inference|Hypothesis|Unknown|Contradicted)(?=[.*\s])"
)


def main() -> None:
    here = Path(__file__).resolve().parent
    failures: list[str] = []
    section_count = 0
    label_count = 0
    for name in FILES:
        text = (here / name).read_text()
        lines = text.splitlines()
        headings = [index for index, line in enumerate(lines) if line.startswith("## ")]
        for number, start in enumerate(headings):
            end = headings[number + 1] if number + 1 < len(headings) else len(lines)
            section_count += 1
            body = "\n".join(lines[start + 1 : end])
            if not LABEL_PATTERN.search(body):
                failures.append(f"{name}:{start + 1}: section lacks a canonical Confidence label")
        label_count += len(LABEL_PATTERN.findall(text))
        for match in re.finditer(r"Confidence:\s*([^\n*]+)", text):
            if not any(match.group(1).startswith(label) for label in LABELS):
                line = text.count("\n", 0, match.start()) + 1
                failures.append(f"{name}:{line}: noncanonical Confidence label {match.group(1)!r}")
    if failures:
        raise SystemExit("\n".join(failures))
    print(
        f"confidence labels: {section_count} chapter sections covered; "
        f"{label_count} canonical labels"
    )


if __name__ == "__main__":
    main()
