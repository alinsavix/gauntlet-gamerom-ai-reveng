"""Verify a Gauntlet II secret-room contest code."""

from __future__ import annotations

import argparse

from .subsystems.players import secret_code_for


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", help="name entered at the cabinet")
    parser.add_argument("code", help="displayed XXX-XXX code")
    parser.add_argument("--maze", type=lambda value: int(value, 0), required=True)
    parser.add_argument("--trick", type=lambda value: int(value, 0), required=True)
    parser.add_argument(
        "--challenge", type=lambda value: int(value, 0), required=True,
        help="secret challenge code, normally 0x50-0x5D",
    )
    args = parser.parse_args(argv)
    expected = secret_code_for(
        args.name, args.maze, args.trick, args.challenge,
    )
    supplied = args.code.upper()
    if supplied == expected:
        print(f"valid: {expected}")
        return 0
    print(f"invalid: expected {expected}, got {supplied}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
