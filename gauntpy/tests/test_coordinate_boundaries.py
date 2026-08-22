"""Architecture guards for native MOB coordinate arithmetic."""

from __future__ import annotations

import ast
from pathlib import Path


SRC = Path(__file__).resolve().parents[1] / "src" / "gauntpy"
COORDS = SRC / "coords.py"


def _python_sources():
    yield from sorted(SRC.rglob("*.py"))


def test_native_mask_literals_live_only_in_coords():
    forbidden = {0xFF80}
    violations = []
    for path in _python_sources():
        if path == COORDS:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value in forbidden:
                violations.append(
                    f"{path.relative_to(SRC)}:{node.lineno}: {node.value:#06x}"
                )
    assert violations == [], (
        "use coords constants/helpers for native MOB masks:\n"
        + "\n".join(violations)
    )


def test_no_direct_position_shift_on_mob_words():
    violations = []
    for path in _python_sources():
        if path == COORDS:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.BinOp) or not isinstance(
                node.op, (ast.LShift, ast.RShift)
            ):
                continue
            if not isinstance(node.right, ast.Constant) or node.right.value != 7:
                continue
            expression = ast.unparse(node.left).lower()
            if "hpos" in expression or "vpos" in expression:
                violations.append(
                    f"{path.relative_to(SRC)}:{node.lineno}: {ast.unparse(node)}"
                )
    assert violations == [], (
        "decode/encode MOB words through coords.py:\n" + "\n".join(violations)
    )


def test_no_direct_coordinate_field_masks():
    violations = []
    for path in _python_sources():
        if path == COORDS:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            direct_mask = (
                isinstance(node, ast.BinOp)
                and isinstance(node.op, ast.BitAnd)
                and isinstance(node.right, ast.Name)
                and node.right.id in {"POS_FIELD_MASK", "POS_LOW_MASK"}
            )
            augmented_mask = (
                isinstance(node, ast.AugAssign)
                and isinstance(node.op, ast.BitAnd)
                and isinstance(node.value, ast.Name)
                and node.value.id in {"POS_FIELD_MASK", "POS_LOW_MASK"}
            )
            if direct_mask or augmented_mask:
                violations.append(
                    f"{path.relative_to(SRC)}:{node.lineno}: {ast.unparse(node)}"
                )
    assert violations == [], (
        "use coords.position_field/low_field/replace_position:\n"
        + "\n".join(violations)
    )


def test_no_hand_packed_pixel_cell_formula():
    violations = []
    for path in _python_sources():
        if path == COORDS:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.BinOp) or not isinstance(node.op, ast.LShift):
                continue
            if not isinstance(node.right, ast.Constant) or node.right.value != 5:
                continue
            if any(
                isinstance(child, ast.BinOp)
                and isinstance(child.op, ast.RShift)
                and isinstance(child.right, ast.Constant)
                and child.right.value == 4
                for child in ast.walk(node.left)
            ):
                violations.append(
                    f"{path.relative_to(SRC)}:{node.lineno}: {ast.unparse(node)}"
                )
    assert violations == [], (
        "use coords.biased_pixels_to_slot/mob_words_to_slot:\n"
        + "\n".join(violations)
    )
