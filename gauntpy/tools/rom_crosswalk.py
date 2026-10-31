"""Build the bidirectional callable inventory from source-local ROM comments.

Run from gauntpy: python tools\\rom_crosswalk.py --write (or --check).
No game imports, optional dependencies, or local ROM images are required.
"""

from __future__ import annotations

import argparse
import ast
from collections import Counter, defaultdict
import csv
from dataclasses import dataclass
import io
import json
from pathlib import Path
import re
import sys
import tokenize
from typing import Iterable


ROOT = Path(__file__).resolve().parents[2]
PREFIX = "# ROM: "
MAPPED_KINDS = {"direct", "part", "merged", "adapter"}
UNMAPPED_KINDS = {"helper", "infrastructure", "unresolved"}
REFERENCE = re.compile(r"(game|os):0x([0-9A-F]+)\Z")
ROM_REPORT = "ROM_FUNCTION_CROSSWALK.csv"
PYTHON_REPORT = "PYTHON_FUNCTION_CROSSWALK.csv"
SUMMARY_REPORT = "FUNCTION_CROSSWALK.md"


class MappingError(ValueError):
    """Invalid, missing, or inconsistent callable metadata."""


@dataclass(frozen=True)
class Annotation:
    kind: str
    refs: tuple[str, ...]
    note: str

    def comment(self) -> str:
        references = " " + ",".join(self.refs) if self.refs else ""
        return f"{PREFIX}{self.kind}{references} | {self.note}"


@dataclass(frozen=True)
class RomFunction:
    image: str
    address: int
    name: str
    entry_kind: str
    catalog: str
    purpose: str = ""
    target: str = ""
    legacy_status: str = ""
    legacy_evidence: str = ""

    @property
    def ref(self) -> str:
        return f"{self.image}:0x{self.address:X}"


@dataclass(frozen=True)
class PythonFunction:
    path: str
    qualname: str
    line: int
    anchor: int
    annotations: tuple[Annotation, ...] = ()

    @property
    def symbol(self) -> str:
        module = self.path.removesuffix(".py").replace("/", ".")
        return f"gauntpy.{module}.{self.qualname}"

    @property
    def layer(self) -> str:
        first = self.path.split("/")[0]
        return first if first in {"game", "host", "render"} else "bridge/tool"

    @property
    def refs(self) -> tuple[str, ...]:
        return tuple(ref for annotation in self.annotations for ref in annotation.refs)

    @property
    def notes(self) -> str:
        return " ".join(annotation.note for annotation in self.annotations)


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_rom_inventory(root: Path = ROOT) -> dict[str, RomFunction]:
    generated = root / "doc" / "generated"
    legacy_rows = _csv_rows(root / "gauntpy" / "ROM_FUNCTION_AUDIT.csv")
    legacy = {int(row["address"], 16): row for row in legacy_rows}
    targets = {
        int(row["address"], 16): row["target"]
        for row in _csv_rows(generated / "os_callable_contracts.csv")
        if row["target"].strip()
    }
    inventory: dict[str, RomFunction] = {}
    for image, catalog in (
        ("game", "callable_contract_coverage.csv"),
        ("os", "os_all_function_contracts.csv"),
    ):
        for row in _csv_rows(generated / catalog):
            address = int(row["address"], 16)
            old = legacy.get(address, {}) if image == "game" else {}
            target = targets.get(address, "") if image == "os" else ""
            entry = RomFunction(
                image, address, row["name"], row.get("entry_kind", "callable"),
                catalog, row.get("purpose", ""),
                f"os:0x{int(target, 16):X}" if target else "",
                old.get("status", ""), old.get("evidence", ""),
            )
            if entry.ref in inventory:
                raise MappingError(f"duplicate ROM entry: {entry.ref}")
            inventory[entry.ref] = entry
    return inventory


def validate_annotations(
    annotations: tuple[Annotation, ...],
    label: str,
    roms: dict[str, RomFunction] | None = None,
) -> None:
    if not annotations:
        raise MappingError(f"{label}: missing {PREFIX.strip()} metadata")
    refs: set[str] = set()
    for annotation in annotations:
        if annotation.kind not in MAPPED_KINDS | UNMAPPED_KINDS:
            raise MappingError(f"{label}: unknown mapping kind {annotation.kind!r}")
        if not annotation.note.strip() or "\n" in annotation.note or "\r" in annotation.note:
            raise MappingError(f"{label}: each annotation needs a single-line explanation")
        if annotation.kind in UNMAPPED_KINDS:
            if annotation.refs or len(annotations) != 1:
                raise MappingError(f"{label}: an unmapped classification must stand alone")
        elif not annotation.refs:
            raise MappingError(f"{label}: {annotation.kind} needs ROM references")
        if annotation.kind == "direct" and len(annotation.refs) != 1:
            raise MappingError(f"{label}: direct needs exactly one ROM reference")
        if annotation.kind == "merged" and len(annotation.refs) < 2:
            raise MappingError(f"{label}: merged needs at least two ROM references")
        for ref in annotation.refs:
            if not REFERENCE.fullmatch(ref):
                raise MappingError(f"{label}: invalid ROM reference {ref!r}")
            if ref in refs:
                raise MappingError(f"{label}: duplicate ROM reference {ref}")
            if roms is not None and ref not in roms:
                raise MappingError(f"{label}: {ref} is not a catalogued callable entry")
            refs.add(ref)


def _parse_comment(line: str, label: str) -> Annotation:
    head, separator, note = line.strip()[len(PREFIX):].partition("|")
    if not separator:
        raise MappingError(f"{label}: ROM comment needs ' | explanation'")
    kind, _, references = head.strip().partition(" ")
    refs = tuple(item.strip() for item in references.split(",")) if references else ()
    return Annotation(kind, refs, note.strip())


def discover_functions(
    source: str, path: str, *, require_metadata: bool = True,
) -> list[PythonFunction]:
    lines = source.splitlines()
    tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    found: list[PythonFunction] = []
    attached_lines: set[int] = set()

    def visit(node: ast.AST, parents: tuple[str, ...]) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name = (*parents, node.name)
            if not isinstance(node, ast.ClassDef):
                anchor = node.lineno
                if node.decorator_list:
                    first = node.decorator_list[0]
                    # Parenthesized decorators can start before their AST expression.
                    anchor = max(
                        token.start[0] for token in tokens
                        if token.type == tokenize.OP and token.string == "@"
                        and token.start[1] == node.col_offset
                        and token.start <= (first.lineno, first.col_offset)
                    )
                start = anchor - 1
                while start > 0 and lines[start - 1].strip().startswith(PREFIX):
                    start -= 1
                label = f"{path}:{node.lineno} {'.'.join(name)}"
                annotations = tuple(
                    _parse_comment(line, label) for line in lines[start:anchor - 1]
                )
                attached_lines.update(range(start + 1, anchor))
                if require_metadata or annotations:
                    validate_annotations(annotations, label)
                found.append(PythonFunction(
                    path, ".".join(name), node.lineno, anchor, annotations,
                ))
            for child in node.body:
                visit(child, name)
        else:
            for child in ast.iter_child_nodes(node):
                visit(child, parents)

    visit(ast.parse(source, filename=path), ())
    for token in tokens:
        if (
            token.type == tokenize.COMMENT
            and token.string.startswith(PREFIX)
            and token.start[0] not in attached_lines
        ):
            raise MappingError(
                f"{path}:{token.start[0]}: ROM metadata is not attached to a definition"
            )
    names = [function.qualname for function in found]
    duplicates = [name for name, count in Counter(names).items() if count > 1]
    if duplicates:
        raise MappingError(f"{path}: ambiguous duplicate definitions: {duplicates}")
    return found


def load_python_inventory(root: Path = ROOT) -> list[PythonFunction]:
    source_root = root / "gauntpy" / "src" / "gauntpy"
    functions = []
    for path in sorted(source_root.rglob("*.py")):
        functions.extend(discover_functions(
            path.read_text(encoding="utf-8"), path.relative_to(source_root).as_posix(),
        ))
    return functions


def mapping_categories(
    functions: list[PythonFunction], roms: dict[str, RomFunction],
) -> tuple[dict[str, str], dict[str, list[PythonFunction]]]:
    """Classify connected components, not misleading individual edge counts."""
    owners: dict[str, list[PythonFunction]] = defaultdict(list)
    by_symbol = {function.symbol: function for function in functions}
    for function in functions:
        validate_annotations(function.annotations, function.symbol, roms)
        for ref in function.refs:
            owners[ref].append(function)
    categories = {}
    for function in functions:
        if function.symbol in categories:
            continue
        if not function.refs:
            kind = function.annotations[0].kind
            categories[function.symbol] = "python-only" if kind == "helper" else kind
            continue
        python_members: set[str] = set()
        rom_members: set[str] = set()
        pending = [function.symbol]
        while pending:
            symbol = pending.pop()
            if symbol in python_members:
                continue
            python_members.add(symbol)
            for ref in by_symbol[symbol].refs:
                rom_members.add(ref)
                pending.extend(owner.symbol for owner in owners[ref])
        if len(rom_members) == len(python_members) == 1:
            category = (
                "one-to-one"
                if function.annotations[0].kind == "direct"
                else "adapted-or-partial"
            )
        elif len(rom_members) == 1:
            category = "one-to-many"
        elif len(python_members) == 1:
            category = "many-to-one"
        else:
            category = "many-to-many"
        for symbol in python_members:
            categories[symbol] = category
    return categories, owners


def _csv_text(fieldnames: list[str], rows: Iterable[dict[str, object]]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def _cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def _function_link(function: PythonFunction) -> str:
    return f"[`{function.symbol}`](src/gauntpy/{function.path}#L{function.line})"


def build_reports(root: Path = ROOT) -> dict[str, str]:
    roms = load_rom_inventory(root)
    functions = load_python_inventory(root)
    categories, owners = mapping_categories(functions, roms)
    python_rows = [
        {
            "python_function": function.symbol,
            "path": f"src/gauntpy/{function.path}",
            "line": function.line,
            "layer": function.layer,
            "category": categories[function.symbol],
            "rom_entries": ";".join(function.refs),
            "relationships": ";".join(
                annotation.kind + (
                    " " + ",".join(annotation.refs) if annotation.refs else ""
                )
                for annotation in function.annotations
            ),
            "notes": function.notes,
        }
        for function in functions
    ]
    rom_rows = []
    for entry in roms.values():
        matching = owners.get(entry.ref, [])
        rom_rows.append({
            "image": entry.image,
            "address": f"0x{entry.address:X}",
            "rom_name": entry.name,
            "entry_kind": entry.entry_kind,
            "category": categories[matching[0].symbol] if matching else "rom-only",
            "python_functions": ";".join(function.symbol for function in matching),
            "catalog": entry.catalog,
            "veneer_target": entry.target,
            "mapping_notes": "; ".join(
                f"{function.symbol} [{annotation.kind}]: {annotation.note}"
                for function in matching for annotation in function.annotations
                if entry.ref in annotation.refs
            ),
            "rom_purpose": entry.purpose,
            "legacy_game_audit_status": entry.legacy_status,
            "legacy_game_audit_evidence": entry.legacy_evidence,
        })
    image_counts = Counter(entry.image for entry in roms.values())
    report = [
        "# ROM/Python function crosswalk",
        "",
        "Generated by `python tools/rom_crosswalk.py --write`. Edit the `# ROM:`",
        "comments at Python definitions, not these generated lists.",
        "",
        "## Scope and interpretation",
        "",
        f"This inventory contains **{len(roms)} documented ROM callable entries**",
        f"({image_counts['game']} game and {image_counts['os']} OS)",
        f"and **{len(functions)} named Python definitions** under `src/gauntpy`.",
        "The ROM inputs are `../doc/generated/callable_contract_coverage.csv`",
        "(game) and `../doc/generated/os_all_function_contracts.csv` (OS).",
        "OS API veneer targets come from `os_callable_contracts.csv`.",
        "This is not a fresh disassembly or a proof that all binary entry points",
        "have been discovered. ROM data tables and the 6502 sound ROM are outside",
        "this callable inventory; the latter's host playback model is infrastructure.",
        "",
        "Python definitions include methods and nested named functions. Imported",
        "reexports, assignment aliases, lambdas, and generated dataclass methods",
        "are not counted as additional implementations. Nested names use lexical",
        "dot-separated names without `<locals>`.",
        "",
        "**One-to-one is a recorded routine-boundary correspondence, not proof",
        "of instruction-level or behavioral equivalence.** Renamed implementations",
        "can still be one-to-one. Connected mapping components identify splits",
        "(one ROM entry to many Python functions), mergers, and many-to-many",
        "relationships. A lone `part` or `adapter` mapping is not promoted to an",
        "exact match just because the graph has one node on each side.",
        "",
        "**Python-only helpers** have no separately identified ROM callable",
        "boundary; this does not mean their behavior was invented. **Unresolved**",
        "means the correspondence is not established and must not be mistaken",
        "for Python-only behavior. **ROM-only** means no identified local Python",
        "definition, not necessarily missing gameplay: veneers, hardware services,",
        "dead routines, table-driven replacements and delegated implementations",
        "need separate interpretation. The old game audit's coverage labels are",
        "retained as historical evidence, not recomputed or treated as proof.",
        "",
        "The CSVs are the machine-readable views:",
        f"[ROM entries]({ROM_REPORT}) and [Python definitions]({PYTHON_REPORT}).",
        "",
        "## Totals",
        "",
        "| Category | Python definitions | ROM entries |",
        "|---|---:|---:|",
    ]
    python_counts = Counter(row["category"] for row in python_rows)
    rom_counts = Counter(row["category"] for row in rom_rows)
    for category in (
        "one-to-one", "one-to-many", "many-to-one", "many-to-many",
        "adapted-or-partial", "python-only", "infrastructure", "unresolved", "rom-only",
    ):
        report.append(f"| {category} | {python_counts[category]} | {rom_counts[category]} |")
    sections = (
        ("One-to-one routine matches", {"one-to-one"}, (
            "**Meaning:** One catalogued ROM callable entry is associated with",
            "one named Python definition, annotated `direct`. Neither side has",
            "another recorded counterpart in the mapping group. The Python name",
            "may differ from the ROM name; the address identifies the routine.",
            "",
            "**Not a fidelity verdict:** This identifies corresponding function",
            "boundaries, not identical instructions, arguments, memory writes,",
            "timing, or behavior. Read each row's explanation for representation",
            "differences and known caveats. A routine with separately mapped",
            "extracted helpers belongs in the next section instead.",
        )),
        ("Split, merged, adapted, and partial mappings", {
            "one-to-many", "many-to-one", "many-to-many", "adapted-or-partial",
        }, (
            "**Meaning:** A ROM correspondence is identified, but it is not an",
            "isolated one-to-one `direct` pair. Each row is one Python definition.",
            "The numeric relationship is always **ROM entries to Python",
            "definitions**, counted across the whole connected mapping group:",
            "",
            "- **Split (`one-to-many`):** One ROM entry maps to several Python",
            "  definitions, such as an entry function and extracted body helpers.",
            "- **Merged (`many-to-one`):** Several ROM entries map to one Python",
            "  definition, such as separately entered bodies combined in one helper.",
            "- **Mixed (`many-to-many`):** Several entries and definitions are",
            "  connected through shared or extracted implementations.",
            "- **Adapted or partial (`adapted-or-partial`):** There is only one",
            "  entry and one definition in the group, but the annotation is not",
            "  `direct`, so it is not classified as a one-to-one routine match.",
            "",
            "The labels in parentheses describe each function's own provenance:",
            "`direct` identifies an entry boundary; `part` identifies a portion",
            "of a ROM body; `merged` identifies bodies combined from multiple",
            "entries; `adapter` identifies an ABI, representation, or delegation",
            "boundary rather than a direct body. A `direct` function can therefore",
            "appear in a split or mixed group because other functions map to the",
            "same entry. Ordinary calls alone do not create mapping relationships.",
            "",
            "**Not a completeness verdict:** `part` does not establish that the",
            "rest is missing; other functions may supply it. Conversely, several",
            "mapped parts do not prove that every branch of the ROM is covered.",
        )),
        ("Python-only game and representation helpers", {"python-only"}, (
            "**Meaning:** These definitions are annotated `helper`: Python",
            "implementation conveniences supporting game logic or its data model,",
            "without a separately identified ROM callable boundary. Examples",
            "include packed-field accessors, signed-integer conversions, and",
            "container bookkeeping. No ROM entry address is assigned.",
            "",
            "**Not necessarily Python-only behavior:** The operation may",
            "correspond to instructions repeated or inlined throughout the ROM.",
            "This category describes the helper's function boundary, not permission",
            "to change gameplay. Known extracted portions of specific entries use",
            "`part` instead; genuinely uncertain provenance uses `unresolved`.",
        )),
        ("Unresolved Python correspondences", {"unresolved"}, (
            "**Meaning:** These definitions are annotated `unresolved` because",
            "the audit has not established their specific ROM correspondence.",
            "They are kept separate from known Python-only helpers and host",
            "infrastructure rather than being assigned a guessed address.",
            "",
            "**Not evidence of invented behavior:** Further investigation might",
            "identify a direct routine, an extracted or merged body, or a genuinely",
            "Python-only helper. `None.` means no definitions currently carry this",
            "classification; it does not prove that all other mappings are correct",
            "or that the ROM and Python behave identically.",
        )),
        ("Python-only host, renderer, and harness infrastructure", {"infrastructure"}, (
            "**Meaning:** These definitions are annotated `infrastructure`:",
            "Python-side facilities for running, presenting, or inspecting the",
            "model, with no claimed callable counterpart in the inventoried game",
            "and OS ROMs. Examples include window/input handling, rasterization,",
            "asset loading, audio playback, snapshots, diagnostics, and scenarios.",
            "Classification follows the function's role, not just its directory.",
            "",
            "**Not game-side presentation logic:** ROM-shaped routines that",
            "choose HUD content or write modeled video memory still belong to the",
            "game mappings. A host renderer may consume ROM graphics or reproduce",
            "hardware display rules without implementing a game/OS CPU routine.",
            "Infrastructure is not required to share ROM function boundaries, but",
            "must preserve the intended simulation and observation boundaries.",
        )),
    )
    for title, selected, explanation in sections:
        report.extend(["", f"## {title}", "", *explanation, ""])
        matching = [function for function in functions if categories[function.symbol] in selected]
        if not matching:
            report.append("None.")
            continue
        report.extend([
            "| Python definition | Relationship | ROM entry / name | Explanation |",
            "|---|---|---|---|",
        ])
        for function in matching:
            references = "; ".join(
                f"`{ref}` `{roms[ref].name}`" for ref in function.refs
            ) or "-"
            kinds = ", ".join(annotation.kind for annotation in function.annotations)
            report.append(
                f"| {_function_link(function)} | {categories[function.symbol]} ({kinds})"
                f" | {references} | {_cell(function.notes)} |"
            )
    report.extend([
        "", "## Legacy coverage claims without a mapped definition", "",
        "**Meaning:** These game-ROM entries were labelled `complete` in",
        "`ROM_FUNCTION_AUDIT.csv`, but no current Python definition's structured",
        "metadata maps to the entry. The older audit assessed caller-visible",
        "behavior, including merged or delegated implementations; it did not",
        "require a one-to-one function boundary. This section flags the gap",
        "between that historical coverage claim and the current mapping evidence.",
        "",
        "**Not a confirmed missing implementation:** The old owner may be stale,",
        "the behavior may be represented indirectly, or the old claim may be wrong.",
        "Reconcile it against actual code and ROM evidence before assigning an",
        "address or declaring missing gameplay. These rows are a **subset** of",
        "the ROM-only list below, not additional ROM entries to add to the totals.",
        "",
    ])
    disagreements = [
        entry for entry in roms.values()
        if entry.legacy_status == "complete" and not owners.get(entry.ref)
    ]
    if disagreements:
        report.extend([
            "| ROM entry | Name | Historical claim needing reconciliation |",
            "|---|---|---|",
        ])
        for entry in disagreements:
            report.append(
                f"| `{entry.ref}` | `{entry.name}` | {_cell(entry.legacy_evidence)} |"
            )
    else:
        report.append("None.")
    report.extend([
        "", "## ROM entries without an identified Python definition", "",
        "**Meaning:** These catalogued game or OS ROM entries have no reference",
        "from any inventoried Python definition's structured metadata: no `direct`,",
        "`part`, `merged`, or `adapter` mapping. This is the ROM-side unmatched",
        "list (`rom-only`), whereas unresolved Python correspondences are the",
        "Python-side uncertain list. An entry with even a partial mapping is",
        "excluded here; absence from this list does not certify complete coverage.",
        "",
        "**Not automatically missing gameplay:** An entry may be a hardware",
        "service, unused code, an ABI wrapper, or behavior supplied through data",
        "or an external dependency rather than a local Python definition. An OS",
        "API veneer (a jump to another entry) can appear here even when its target",
        "has a Python mapping. Read the entry kind, target, and historical evidence",
        "to distinguish intentional omissions from questions still requiring",
        "investigation. The preceding legacy-claims section repeats the subset",
        "previously called `complete`; do not count that subset twice.",
        "",
        "| ROM entry | Name | Entry kind | Legacy coverage / explanation |",
        "|---|---|---|---|",
    ])
    for entry in roms.values():
        if owners.get(entry.ref):
            continue
        explanation = entry.legacy_evidence or entry.purpose
        if entry.legacy_status:
            explanation = f"Legacy audit: {entry.legacy_status}. {explanation}"
        if entry.target:
            explanation += f" Veneer target: {entry.target}."
            if owners.get(entry.target):
                explanation += " Target has a Python mapping; no separate veneer definition."
        report.append(
            f"| `{entry.ref}` | `{entry.name}` | {entry.entry_kind} | {_cell(explanation)} |"
        )
    report.extend([
        "", "## Maintaining annotations", "",
        "Place one or more contiguous comments immediately before the first",
        "decorator, or before `def` when there are no decorators:",
        "",
        "```python",
        "# ROM: direct game:0x40644 | input_debounce callable boundary.",
        "def input_debounce(state):",
        "    ...",
        "",
        "# ROM: part game:0x4017E | Palette-writing portion of game_vblank.",
        "def palette_step(state):",
        "    ...",
        "",
        "# ROM: helper | Python representation helper; no separate ROM entry.",
        "def position_view(word):",
        "    ...",
        "```",
        "",
        "Mapped kinds are `direct` (one reference), `part`, `merged` (two or",
        "more references), and `adapter`. Unmapped kinds are `helper`,",
        "`infrastructure`, and `unresolved`; these stand alone without an address.",
        "References use `game:0xADDRESS` or `os:0xADDRESS`, separated by commas.",
        "Every annotation needs an explanation. Do not substitute a callee,",
        "table, or interior instruction address for a catalogued callable entry.",
        "Only map inlined/extracted bodies, not ordinary calls to other routines.",
        "",
        "Run `python tools/rom_crosswalk.py --check` to detect missing metadata,",
        "unknown addresses, duplicate references, or stale generated reports.",
        "",
    ])
    return {
        ROM_REPORT: _csv_text(list(rom_rows[0]), rom_rows),
        PYTHON_REPORT: _csv_text([
            "python_function", "path", "line", "layer", "category",
            "rom_entries", "relationships", "notes",
        ], python_rows),
        SUMMARY_REPORT: "\n".join(report),
    }


def annotate_source(
    source: str, path: str, metadata: dict[str, tuple[Annotation, ...]],
) -> str:
    """Install reviewed comments without changing any AST node or original line."""
    functions = discover_functions(source, path, require_metadata=False)
    expected = {function.qualname for function in functions}
    if set(metadata) != expected:
        raise MappingError(
            f"{path}: annotation coverage differs: missing={sorted(expected - set(metadata))}, "
            f"extra={sorted(set(metadata) - expected)}"
        )
    lines = source.splitlines(keepends=True)
    newline = "\r\n" if any(line.endswith("\r\n") for line in lines) else "\n"
    for function in reversed(functions):
        annotations = metadata[function.qualname]
        validate_annotations(annotations, f"{path}:{function.qualname}")
        end = function.anchor - 1
        start = end
        while start > 0 and lines[start - 1].strip().startswith(PREFIX):
            start -= 1
        indentation = lines[end][:len(lines[end]) - len(lines[end].lstrip())]
        lines[start:end] = [
            indentation + annotation.comment() + newline for annotation in annotations
        ]
    result = "".join(lines)
    if ast.dump(ast.parse(source)) != ast.dump(ast.parse(result)):
        raise MappingError(f"{path}: annotation installation changed the executable AST")
    discover_functions(result, path)
    return result


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise MappingError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def install_annotations(paths: list[Path], root: Path = ROOT) -> None:
    """Bulk-install complete, reviewed per-definition metadata from JSON files."""
    metadata: dict[str, dict[str, tuple[Annotation, ...]]] = {}
    roms = load_rom_inventory(root)
    for path in paths:
        raw = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_unique_json_object,
        )
        if not isinstance(raw, dict):
            raise MappingError(f"{path}: expected a file-to-function mapping object")
        for source_path, entries in raw.items():
            if source_path in metadata:
                raise MappingError(f"duplicate metadata file owner: {source_path}")
            if not isinstance(entries, dict):
                raise MappingError(f"{source_path}: expected a function mapping object")
            metadata[source_path] = {}
            for qualname, records in entries.items():
                if not isinstance(records, list) or not all(
                    isinstance(record, dict)
                    and set(record) == {"kind", "refs", "note"}
                    and isinstance(record["kind"], str)
                    and isinstance(record["refs"], list)
                    and all(isinstance(ref, str) for ref in record["refs"])
                    and isinstance(record["note"], str)
                    for record in records
                ):
                    raise MappingError(f"{source_path}:{qualname}: invalid annotation records")
                annotations = tuple(
                    Annotation(record["kind"], tuple(record["refs"]), record["note"])
                    for record in records
                )
                validate_annotations(annotations, f"{source_path}:{qualname}", roms)
                metadata[source_path][qualname] = annotations
    source_root = root / "gauntpy" / "src" / "gauntpy"
    sources = {
        path.relative_to(source_root).as_posix(): path
        for path in sorted(source_root.rglob("*.py"))
    }
    if set(metadata) - set(sources):
        raise MappingError(f"unknown source paths: {sorted(set(metadata) - set(sources))}")
    pending = []
    for source_path, path in sources.items():
        with path.open(encoding="utf-8", newline="") as handle:
            source = handle.read()
        result = annotate_source(source, source_path, metadata.get(source_path, {}))
        if source != result:
            pending.append((path, result))
    # Validate the entire batch before changing any source file.
    for path, result in pending:
        with path.open("w", encoding="utf-8", newline="") as handle:
            handle.write(result)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--check", action="store_true", help="reject stale reports")
    action.add_argument("--write", action="store_true", help="regenerate reports")
    action.add_argument(
        "--annotate", nargs="+", type=Path, metavar="JSON",
        help="install complete reviewed metadata, then regenerate reports",
    )
    args = parser.parse_args(argv)
    try:
        if args.annotate:
            install_annotations(args.annotate)
        reports = build_reports()
    except (MappingError, OSError, json.JSONDecodeError, SyntaxError) as error:
        print(f"ROM crosswalk: {error}", file=sys.stderr)
        return 1
    stale = []
    for name, content in reports.items():
        path = ROOT / "gauntpy" / name
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                stale.append(name)
        else:
            path.write_text(content, encoding="utf-8", newline="\n")
    if stale:
        print("Stale ROM crosswalk reports: " + ", ".join(stale), file=sys.stderr)
        return 1
    print("ROM crosswalk is current." if args.check else "ROM crosswalk reports generated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
