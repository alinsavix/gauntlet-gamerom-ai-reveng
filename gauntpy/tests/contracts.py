"""WP-21 sub-deliverable 1 -- reusable contract-CSV checking infrastructure.

``test_mainloop.py`` already proved the shape: parse something transcribed
into Python, load the matching CSV under ``doc/generated/``, and diff them so
drift fails a test instead of rotting silently. That module hard-codes the
diff for exactly one CSV (the call order). This module generalizes the two
reusable halves -- *load a contract CSV* and *diff a transcribed table
against it* -- so a future work package (WP-5 through WP-17, mostly) can drop
a five-line test into its own ``test_<name>.py`` the moment it transcribes a
ROM table into a Python dict, list, or enum:

    from .contracts import assert_table_matches_contract, contract_map, load_contract_csv

    def test_my_table_matches_its_contract():
        rows = load_contract_csv("my_table_contracts.csv")
        expected = contract_map(rows, key_col="name", value_col="value", value_fn=parse_int)
        assert_table_matches_contract(MY_TRANSCRIBED_TABLE, expected, table_name="my_table")

Most of ``doc/generated/*.csv`` pairs with a work package that has not landed
yet -- there is no Python table to check most of them against. See
``test_contracts.py`` for two worked examples against what actually exists
today (WP-18's sound-command constants and ``mainloop.py``'s ROM address
comments), which is the point: this module is dead weight until a package
lands, and then it is a five-line test.
"""

from __future__ import annotations

import csv
import re
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATED_DIR = REPO_ROOT / "doc" / "generated"

#: A trailing "-- 0xNNNNNN" ROM address in a comment or docstring.
ADDRESS_RE = re.compile(r"0x[0-9A-Fa-f]{4,6}")


def resolve_contract_path(name: str) -> Path:
    """Resolve a CSV name to a path.

    Bare names (``"main_loop_contracts.csv"``) resolve under
    ``doc/generated/``, since that is where every *contracts.csv is
    generated. Anything else -- ``"refs/soundcmds.csv"``, an absolute path --
    is resolved relative to the repository root, or used as-is. This is what
    lets ``test_contracts.py`` point at ``refs/soundcmds.csv`` (the corrected
    catalog; see its module-level note) without a second loader function.
    """
    path = Path(name)
    if path.is_absolute():
        return path
    under_generated = GENERATED_DIR / name
    if under_generated.exists():
        return under_generated
    return REPO_ROOT / name


def load_contract_csv(name: str) -> list[dict[str, str]]:
    """Load a contract CSV into a list of ``{column: value}`` dicts.

    Handles the UTF-8 BOM the doc generators emit (``encoding="utf-8-sig"``)
    and drops fully-blank rows, which a couple of the generated files end
    with courtesy of a trailing newline.
    """
    path = resolve_contract_path(name)
    with path.open(newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    return [r for r in rows if any((v or "").strip() for v in r.values())]


def parse_int(value: str) -> int:
    """Parse a CSV cell as an integer, decimal or ``0x``-prefixed hex."""
    value = value.strip()
    return int(value, 16) if value.lower().startswith("0x") else int(value)


def contract_map(
    rows: Iterable[Mapping[str, str]],
    key_col: str,
    value_col: str,
    *,
    key_fn: Callable[[str], object] = str,
    value_fn: Callable[[str], object] = str,
) -> dict[object, object]:
    """Build a ``{key: value}`` table from two columns of a contract CSV."""
    return {key_fn(r[key_col]): value_fn(r[value_col]) for r in rows}


def diff_table(actual: Mapping[object, object], expected: Mapping[object, object]) -> list[str]:
    """Human-readable mismatches between a transcribed table and its contract.

    Reports missing keys (in the contract but not the transcription), extra
    keys (transcribed but not in the contract), and value mismatches --
    always in a stable, sorted order so a failing test's output is the same
    on every run.
    """
    problems: list[str] = []
    missing = sorted(set(expected) - set(actual), key=repr)
    extra = sorted(set(actual) - set(expected), key=repr)
    for key in missing:
        problems.append(f"missing {key!r}: contract says {expected[key]!r}")
    for key in extra:
        problems.append(f"unexpected {key!r}: transcribed as {actual[key]!r}, not in contract")
    for key in sorted(set(actual) & set(expected), key=repr):
        if actual[key] != expected[key]:
            problems.append(f"{key!r}: transcribed as {actual[key]!r}, contract says {expected[key]!r}")
    return problems


def assert_table_matches_contract(
    actual: Mapping[object, object],
    expected: Mapping[object, object],
    *,
    table_name: str = "table",
) -> None:
    """Assert ``actual`` matches ``expected`` exactly, with a full diff on failure."""
    problems = diff_table(actual, expected)
    assert not problems, (
        f"{table_name} diverges from its contract:\n  " + "\n  ".join(problems)
    )


def first_address_in(text: str) -> int | None:
    """The first ``0xNNNN``-shaped literal in ``text``, or ``None``."""
    match = ADDRESS_RE.search(text or "")
    return int(match.group(0), 16) if match else None
