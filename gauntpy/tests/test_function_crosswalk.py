"""The source-local correspondence inventory is complete and reproducible."""

from __future__ import annotations

import ast
import csv
from dataclasses import replace
import importlib.util
import io
import json
from pathlib import Path
import sys

import pytest


TOOL = Path(__file__).resolve().parents[1] / "tools" / "rom_crosswalk.py"
SPEC = importlib.util.spec_from_file_location("gauntpy_rom_crosswalk_tool", TOOL)
crosswalk = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = crosswalk
SPEC.loader.exec_module(crosswalk)


def annotation(kind="direct", refs=("game:0x40644",), note="Documented input routine."):
    return crosswalk.Annotation(kind, refs, note)


def roms():
    return {
        ref: crosswalk.RomFunction("game", int(ref.split(":")[1], 16), name, "callable", "test.csv")
        for ref, name in (
            ("game:0x40644", "input_debounce"),
            ("game:0x42A66", "g2mainloop"),
            ("game:0x4017E", "game_vblank"),
        )
    }


def function(name, *annotations):
    return crosswalk.PythonFunction("game/example.py", name, 2, 2, annotations)


def test_named_definitions_include_methods_nested_and_async_but_not_aliases():
    source = """
from elsewhere import exported
# ROM: helper | Model convenience, not a ROM entry.
def outer():
    # ROM: helper | Local implementation closure.
    async def inner():
        return 1
    return inner
alias = outer
anonymous = lambda: 1
class Model:
    # ROM: helper | Property over modeled state.
    @property
    def value(self):
        return 1
"""
    found = crosswalk.discover_functions(source, "game/example.py")
    assert [item.qualname for item in found] == ["outer", "outer.inner", "Model.value"]
    assert found[-1].anchor == found[-1].line - 1


@pytest.mark.parametrize("source", [
    'def f():\n    """Routine mentions 0x40644, but has no structured metadata."""\n',
    '# ROM: direct game:0x40644 | Not next to a function.\nvalue = 1\ndef f(): pass\n',
    '@property\n# ROM: helper | Must precede the first decorator.\ndef f(): pass\n',
])
def test_freeform_hex_or_detached_comments_do_not_supply_metadata(source):
    with pytest.raises(crosswalk.MappingError):
        crosswalk.discover_functions(source, "example.py")


def test_docstring_examples_are_not_mistaken_for_detached_annotations():
    source = '''"""
# ROM: helper | Example, not an actual comment token.
"""
# ROM: direct game:0x40644 | Documented input routine.
def input_debounce(state):
    pass
'''
    assert len(crosswalk.discover_functions(source, "example.py")) == 1


@pytest.mark.parametrize("record,match", [
    (annotation(refs=()), "needs ROM references"),
    (annotation(refs=("game:0x40644", "game:0x42A66")), "exactly one"),
    (annotation("merged"), "at least two"),
    (annotation("helper"), "must stand alone"),
    (annotation("invented"), "unknown mapping kind"),
    (annotation(refs=("game:0x904002",)), "not a catalogued callable"),
    (annotation(refs=("game:0x40645",)), "not a catalogued callable"),
    (annotation(refs=("game:0x406ab",)), "invalid ROM reference"),
    (annotation(note=""), "single-line explanation"),
    (annotation(note="first\nsecond"), "single-line explanation"),
])
def test_invalid_mappings_are_rejected(record, match):
    with pytest.raises(crosswalk.MappingError, match=match):
        crosswalk.validate_annotations((record,), "example.f", roms())


def test_duplicate_references_and_mixed_mapped_unmapped_statuses_fail():
    for records in (
        (annotation(), annotation("part")),
        (annotation(), annotation("unresolved", (), "Entry not known.")),
    ):
        with pytest.raises(crosswalk.MappingError):
            crosswalk.validate_annotations(records, "example.f", roms())


def test_ambiguous_duplicate_definitions_fail_instead_of_losing_an_owner():
    source = (
        "# ROM: helper | First definition.\ndef same(): pass\n"
        "# ROM: helper | Second definition.\ndef same(): pass\n"
    )
    with pytest.raises(crosswalk.MappingError, match="duplicate definitions"):
        crosswalk.discover_functions(source, "example.py")


def test_graph_distinguishes_exact_split_merged_and_partial():
    exact = function("input_debounce", annotation())
    categories, _ = crosswalk.mapping_categories([exact], roms())
    assert categories[exact.symbol] == "one-to-one"

    helper = function("input_tail", annotation("part"))
    categories, _ = crosswalk.mapping_categories([exact, helper], roms())
    assert set(categories.values()) == {"one-to-many"}

    merged = function("combined", annotation(
        "merged", ("game:0x40644", "game:0x42A66"), "Two inlined ROM bodies.",
    ))
    categories, _ = crosswalk.mapping_categories([merged], roms())
    assert categories[merged.symbol] == "many-to-one"

    categories, _ = crosswalk.mapping_categories([merged, helper], roms())
    assert set(categories.values()) == {"many-to-many"}

    categories, _ = crosswalk.mapping_categories([helper], roms())
    assert categories[helper.symbol] == "adapted-or-partial"


def test_unresolved_is_not_counted_as_python_only_or_an_exact_match():
    functions = [
        function("unknown", annotation("unresolved", (), "Entry is not established.")),
        function("view", annotation("helper", (), "Representation convenience.")),
        function("window", annotation("infrastructure", (), "Host window service.")),
    ]
    categories, _ = crosswalk.mapping_categories(functions, roms())
    assert list(categories.values()) == ["unresolved", "python-only", "infrastructure"]


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_bulk_annotations_preserve_ast_newlines_and_are_idempotent(newline):
    source = newline.join([
        '"""Existing module text."""',
        "class Model:",
        "    @property",
        "    def value(self):",
        '        """Existing function text."""',
        "        def local():",
        "            return 1",
        "        return local()",
        "",
    ])
    metadata = {
        "Model.value": (annotation("helper", (), "Model property."),),
        "Model.value.local": (annotation("helper", (), "Local closure."),),
    }
    result = crosswalk.annotate_source(source, "example.py", metadata)
    assert ast.dump(ast.parse(result)) == ast.dump(ast.parse(source))
    assert crosswalk.annotate_source(result, "example.py", metadata) == result
    assert result.replace(
        "    # ROM: helper | Model property." + newline, "",
    ).replace(
        "        # ROM: helper | Local closure." + newline, "",
    ) == source
    assert len(crosswalk.discover_functions(result, "example.py")) == 2


def test_bulk_annotation_requires_exact_definition_coverage():
    with pytest.raises(crosswalk.MappingError, match="annotation coverage differs"):
        crosswalk.annotate_source("def f(): pass\n", "example.py", {})


def test_parenthesized_decorator_uses_the_at_sign_not_the_expression_line():
    source = (
        "class Model:\n"
        "    @(\n"
        "        property\n"
        "    )\n"
        "    def value(self):\n"
        "        return 1\n"
    )
    metadata = {"Model.value": (annotation("helper", (), "Model property."),)}
    result = crosswalk.annotate_source(source, "example.py", metadata)
    assert result.startswith(
        "class Model:\n    # ROM: helper | Model property.\n    @(\n"
    )
    found = crosswalk.discover_functions(result, "example.py")
    assert found[0].anchor == 3
    assert ast.dump(ast.parse(source)) == ast.dump(ast.parse(result))
    assert crosswalk.annotate_source(result, "example.py", metadata) == result


@pytest.mark.parametrize("payload", [
    '{"a.py": {}, "a.py": {}}',
    '{"a.py": {"f": [], "f": []}}',
    '{"a.py": {"f": [{"kind": "direct", "kind": "helper", "refs": [], "note": "x"}]}}',
])
def test_duplicate_reviewed_metadata_keys_are_rejected(tmp_path, monkeypatch, payload):
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(payload, encoding="utf-8")
    monkeypatch.setattr(crosswalk, "load_rom_inventory", lambda root: roms())
    with pytest.raises(crosswalk.MappingError, match="duplicate JSON object key"):
        crosswalk.install_annotations([metadata_path], tmp_path)


def test_install_validates_the_whole_batch_before_writing(tmp_path, monkeypatch):
    source_root = tmp_path / "gauntpy" / "src" / "gauntpy"
    source_root.mkdir(parents=True)
    first = source_root / "a.py"
    second = source_root / "b.py"
    first.write_text("def a(): pass\n", encoding="utf-8")
    second.write_text("def b(): pass\n", encoding="utf-8")
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(json.dumps({
        "a.py": {"a": [{"kind": "direct", "refs": ["game:0x40644"], "note": "Input entry."}]},
    }), encoding="utf-8")
    monkeypatch.setattr(crosswalk, "load_rom_inventory", lambda root: roms())
    with pytest.raises(crosswalk.MappingError, match="b.py: annotation coverage"):
        crosswalk.install_annotations([metadata_path], tmp_path)
    assert first.read_text() == "def a(): pass\n"
    assert second.read_text() == "def b(): pass\n"


def test_report_contains_all_rom_entries_and_separate_infrastructure(monkeypatch):
    functions = [
        function("renamed_input", annotation()),
        function("window", annotation("infrastructure", (), "Host window.")),
        function("unknown", annotation("unresolved", (), "Unknown entry.")),
    ]
    monkeypatch.setattr(crosswalk, "load_rom_inventory", lambda root: roms())
    monkeypatch.setattr(crosswalk, "load_python_inventory", lambda root: functions)
    reports = crosswalk.build_reports()
    assert reports == crosswalk.build_reports()
    rows = list(csv.DictReader(io.StringIO(reports[crosswalk.ROM_REPORT])))
    assert len(rows) == 3
    assert [row["category"] for row in rows] == ["one-to-one", "rom-only", "rom-only"]
    python_rows = list(csv.DictReader(io.StringIO(reports[crosswalk.PYTHON_REPORT])))
    assert len(python_rows) == 3
    assert "Python-only host, renderer, and harness infrastructure" in reports[crosswalk.SUMMARY_REPORT]
    assert "Unresolved Python correspondences" in reports[crosswalk.SUMMARY_REPORT]


@pytest.mark.parametrize("populated", [False, True])
def test_section_explanations_precede_rows_or_empty_results(monkeypatch, populated):
    functions = [
        function("input_debounce", annotation()),
        function("loop_tail", annotation("part", ("game:0x42A66",), "Loop tail.")),
        function("view", annotation("helper", (), "Representation helper.")),
        function("window", annotation("infrastructure", (), "Host window.")),
        function("unknown", annotation("unresolved", (), "Unknown entry.")),
    ] if populated else []
    inventory = roms()
    inventory["game:0x4017E"] = replace(
        inventory["game:0x4017E"],
        legacy_status="complete", legacy_evidence="Historical interrupt coverage.",
    )
    monkeypatch.setattr(crosswalk, "load_rom_inventory", lambda root: inventory)
    monkeypatch.setattr(crosswalk, "load_python_inventory", lambda root: functions)
    report = crosswalk.build_reports()[crosswalk.SUMMARY_REPORT]
    expected = {
        "One-to-one routine matches": ("annotated `direct`", "Not a fidelity verdict"),
        "Split, merged, adapted, and partial mappings": (
            "whole connected mapping group", "Not a completeness verdict",
        ),
        "Python-only game and representation helpers": (
            "annotated `helper`", "Not necessarily Python-only behavior",
        ),
        "Unresolved Python correspondences": (
            "annotated `unresolved`", "Not evidence of invented behavior",
        ),
        "Python-only host, renderer, and harness infrastructure": (
            "annotated `infrastructure`", "Not game-side presentation logic",
        ),
        "Legacy coverage claims without a mapped definition": (
            "`ROM_FUNCTION_AUDIT.csv`", "Not a confirmed missing implementation",
        ),
        "ROM entries without an identified Python definition": (
            "ROM-side unmatched", "Not automatically missing gameplay",
        ),
    }
    for title, phrases in expected.items():
        section = report.split(f"## {title}\n\n", 1)[1].split("\n## ", 1)[0]
        explanation = section.split("\n| ", 1)[0].split("\nNone.", 1)[0]
        assert explanation.startswith("**Meaning:**")
        assert all(phrase in explanation for phrase in phrases), title


def test_current_mapping_notes_are_distinct_from_historical_coverage_claims(monkeypatch):
    inventory = roms()
    inventory["game:0x40644"] = replace(
        inventory["game:0x40644"],
        legacy_status="complete", legacy_evidence="A historical owner description.",
    )
    inventory["game:0x42A66"] = replace(
        inventory["game:0x42A66"],
        legacy_status="complete", legacy_evidence="An unreconciled historical claim.",
    )
    monkeypatch.setattr(crosswalk, "load_rom_inventory", lambda root: inventory)
    monkeypatch.setattr(
        crosswalk, "load_python_inventory",
        lambda root: [function("input_debounce", annotation())],
    )
    reports = crosswalk.build_reports()
    rows = list(csv.DictReader(io.StringIO(reports[crosswalk.ROM_REPORT])))
    assert "Documented input routine." in rows[0]["mapping_notes"]
    assert "historical" not in rows[0]["mapping_notes"]
    assert rows[0]["legacy_game_audit_evidence"] == "A historical owner description."
    section = reports[crosswalk.SUMMARY_REPORT].split(
        "## Legacy coverage claims without a mapped definition", 1,
    )[1].split("## ROM entries without", 1)[0]
    assert "game:0x42A66" in section
    assert "game:0x40644" not in section


def test_repository_reports_are_current_and_all_functions_are_classified():
    reports = crosswalk.build_reports()
    for name, expected in reports.items():
        path = crosswalk.ROOT / "gauntpy" / name
        assert path.read_text(encoding="utf-8") == expected, (
            f"{name} is stale; run python tools\\rom_crosswalk.py --write"
        )
    python_rows = list(csv.DictReader(io.StringIO(reports[crosswalk.PYTHON_REPORT])))
    assert python_rows
    assert all(row["category"] and row["notes"] for row in python_rows)
    inventory = crosswalk.load_rom_inventory()
    assert {entry.image for entry in inventory.values()} == {"game", "os"}
    rom_rows = list(csv.DictReader(io.StringIO(reports[crosswalk.ROM_REPORT])))
    assert len(rom_rows) == len(inventory)
