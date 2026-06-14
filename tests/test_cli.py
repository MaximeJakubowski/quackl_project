"""CLI tests, including the separated load-then-validate workflow."""
from pathlib import Path

from quackl.cli import main

FILES = Path(__file__).parent / "files"
DATA = str(FILES / "data.ttl")
SHAPES = str(FILES / "shapes.ttl")


def test_run_reports_violations(capsys):
    code = main(["run", DATA, SHAPES])
    out = capsys.readouterr().out
    assert code == 1
    assert "http://example.org/bob" in out
    assert "http://example.org/carol" in out
    assert "http://example.org/alice" not in out


def test_bare_args_are_shorthand_for_run(capsys):
    code = main([DATA, SHAPES])
    capsys.readouterr()
    assert code == 1


def test_load_then_validate_separately(tmp_path, capsys):
    db = str(tmp_path / "graph.duckdb")

    # Step 1: load (writes the file, no validation).
    assert main(["load", DATA, "--db", db]) == 0
    capsys.readouterr()

    # Step 2: validate against the already-loaded file (e.g. another process).
    code = main(["validate", SHAPES, "--db", db])
    out = capsys.readouterr().out
    assert code == 1
    assert "http://example.org/bob" in out
    assert "http://example.org/carol" in out
