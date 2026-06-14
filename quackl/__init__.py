"""quackl: DuckDB-backed SHACL validation by compilation into SQL.

Typical use::

    from rdflib import Graph
    from quackl import Store, load_graph, Validator

    store = Store.create("graph.duckdb")   # or Store.create() for in-memory
    load_graph(store, Graph().parse("data.ttl"))

    violations = Validator(store).validate(Graph().parse("shapes.ttl"))

Loading and validation are deliberately separate: load once (optionally to a
file) and validate many times, even from another process via ``Store.open``.
"""
from quackl.store import Store
from quackl.loader import load_graph, load_file
from quackl.validator import Validator, validate

__version__ = "0.1.0"

__all__ = [
    "Store",
    "load_graph",
    "load_file",
    "Validator",
    "validate",
]
