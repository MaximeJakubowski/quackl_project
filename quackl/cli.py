"""Command-line interface for quackl.

Three subcommands realize the load/validate separation, plus a combined run:

* ``quackl load DATA --db FILE.duckdb``     -- load RDF into a persistent store
* ``quackl validate SHAPES --db FILE.duckdb`` -- validate against a loaded store
* ``quackl run DATA SHAPES``                 -- load (in-memory) and validate at once

``quackl DATA SHAPES`` (no subcommand) is shorthand for ``run``.

Exit status is 0 when the data conforms and 1 when there are violations.
"""
from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from rdflib.term import Identifier

from quackl.store import Store
from quackl.loader import load_file
from quackl.validator import Validator


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="quackl", description="DuckDB-backed SHACL validation by compilation into SQL."
    )
    sub = parser.add_subparsers(dest="command")

    p_load = sub.add_parser("load", help="Load an RDF file into a DuckDB store.")
    p_load.add_argument("data", help="RDF data file.")
    p_load.add_argument("--db", required=True, help="Path to the .duckdb file to create/populate.")
    p_load.add_argument("--format", default=None, help="rdflib format (guessed if omitted).")

    p_val = sub.add_parser("validate", help="Validate shapes against a loaded store.")
    p_val.add_argument("shapes", help="SHACL shapes file.")
    p_val.add_argument("--db", required=True, help="Path to an already-loaded .duckdb file.")
    p_val.add_argument("--format", default=None, help="rdflib format (guessed if omitted).")

    p_run = sub.add_parser("run", help="Load data and validate shapes in one in-memory step.")
    p_run.add_argument("data", help="RDF data file.")
    p_run.add_argument("shapes", help="SHACL shapes file.")
    p_run.add_argument("--data-format", default=None, help="rdflib format for the data.")
    p_run.add_argument("--shapes-format", default=None, help="rdflib format for the shapes.")

    return parser


_SUBCOMMANDS = {"load", "validate", "run"}


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # Allow `quackl DATA SHAPES` as shorthand for `quackl run DATA SHAPES`.
    if argv and argv[0] not in _SUBCOMMANDS and not argv[0].startswith("-"):
        argv = ["run"] + argv

    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "load":
        return _cmd_load(args)
    if args.command == "validate":
        return _cmd_validate(args)
    if args.command == "run":
        return _cmd_run(args)

    parser.print_help()
    return 2


def _cmd_load(args: argparse.Namespace) -> int:
    with Store.create(args.db) as store:
        count = load_file(store, args.data, format=args.format)
    print(f"Loaded {count} triples into {args.db}", file=sys.stderr)
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    with Store.open(args.db, read_only=True) as store:
        violations = Validator(store).validate_file(args.shapes, format=args.format)
    return _report(violations)


def _cmd_run(args: argparse.Namespace) -> int:
    with Store.create() as store:
        load_file(store, args.data, format=args.data_format)
        violations = Validator(store).validate_file(args.shapes, format=args.shapes_format)
    return _report(violations)


def _report(violations: List[Identifier]) -> int:
    if not violations:
        print("Conforms.", file=sys.stderr)
        return 0
    print(f"{len(violations)} violating node(s):", file=sys.stderr)
    for term in violations:
        print(term.n3())
    return 1


if __name__ == "__main__":
    sys.exit(main())
