"""Verify and decode a Gauntlet II secret-room contest code."""

from __future__ import annotations

import argparse

from .subsystems.players import _SECRET_CODE_ALPHABET, secret_code_for


def verify_secret_code(name: str, code: str) -> tuple[bool, int, int, int]:
    """Validate the name-bound symbols and decode the embedded game state."""
    code = code.strip().upper()
    if len(code) != 7 or code[3] != "-":
        raise ValueError("code must use the ROM's XXX-XXX format")
    try:
        symbols = [_SECRET_CODE_ALPHABET.index(char) for char in code if char != "-"]
    except ValueError as exc:
        raise ValueError(
            "code contains a symbol outside the ROM alphabet"
        ) from exc

    expected = secret_code_for(name, 0, 0, 0)
    valid = all(code[index] == expected[index] for index in (0, 2, 5))
    packed = (symbols[1] << 10) | (symbols[3] << 5) | symbols[5]
    previous_trick = (packed >> 11) & 0x0F
    challenge = 0x50 | ((packed >> 7) & 0x0F)
    previous_maze = packed & 0x7F
    return valid, previous_maze, previous_trick, challenge


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", help="name entered at the cabinet")
    parser.add_argument("code", help="displayed XXX-XXX code")
    args = parser.parse_args(argv)
    try:
        valid, maze, trick, challenge = verify_secret_code(args.name, args.code)
    except ValueError as exc:
        parser.error(str(exc))
    supplied = args.code.strip().upper()
    if valid:
        print(
            f"valid: {supplied} "
            f"(maze {maze}, trick {trick}, challenge {challenge:#04x})"
        )
        return 0
    print(f"invalid: {supplied} does not match the submitted name")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
