"""Validate RDF data (already loaded into a :class:`~quackl.store.Store`)
against a SHACL shapes graph, using SQL.

This first version returns a flat list of violating focus nodes as RDF terms.
The per-shape SQL in :mod:`quackl.translator` and :meth:`Store.terms_for_ids`
are kept as seams so a richer ``ValidationReport`` can be added later without
re-architecting.
"""
from __future__ import annotations

from typing import List, Optional

from rdflib import Graph
from rdflib.term import Identifier

from slsparser import parse

from quackl.store import Store
from quackl.loader import load_graph
from quackl import translator


class Validator:
    """Runs SHACL validation against a loaded :class:`Store`."""

    def __init__(self, store: Store):
        self._store = store

    def validate(self, shapes_graph: Graph) -> List[Identifier]:
        """Return the violating focus nodes for ``shapes_graph`` as RDF terms."""
        definitions, targets = parse(shapes_graph)
        sql = translator.translate_conformance_all(definitions, targets)
        if sql is None:  # no shapes with targets -> nothing can be violated
            return []
        rows = self._store.connection.execute(sql).fetchall()
        return self._store.terms_for_ids(row[0] for row in rows)

    def validate_file(self, path: str, format: Optional[str] = None) -> List[Identifier]:
        graph = Graph()
        graph.parse(path, format=format)
        return self.validate(graph)

    def conforms(self, shapes_graph: Graph) -> bool:
        """Whether the data conforms (no violations)."""
        return not self.validate(shapes_graph)


def validate(data_graph: Graph, shapes_graph: Graph) -> List[Identifier]:
    """Convenience: load ``data_graph`` into a fresh in-memory store and validate."""
    store = Store.create()
    load_graph(store, data_graph)
    return Validator(store).validate(shapes_graph)
