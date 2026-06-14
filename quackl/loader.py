"""Load an RDF graph into a :class:`~quackl.store.Store`.

This is the slow part of validation and is deliberately separate from it: load
once (optionally into a file-backed store), validate many times.

The encoding is the "pooling" technique of the *Compiling SHACL into SQL*
paper: each distinct RDF term is assigned a unique integer id and recorded in
the type-specific table (``IRIs`` / ``Blanks`` / ``Literals``), numeric literals
additionally get a ``Numerics`` row, and ``Triples`` stores subject/object ids
with the predicate kept as an IRI string.
"""
from __future__ import annotations

from typing import List, Tuple

import duckdb
from rdflib import Graph, URIRef, BNode, Literal
from rdflib.term import Identifier

from quackl.rdfterms import sparql_datatype, numeric_value
from quackl.store import Store


def load_file(store: Store, path: str, format: str = None) -> int:
    """Parse the RDF file at ``path`` and load it into ``store``.

    ``format`` is passed to rdflib; when ``None`` it is guessed from the file
    extension. Returns the number of triples loaded.
    """
    graph = Graph()
    graph.parse(path, format=format)
    return load_graph(store, graph)


def load_graph(store: Store, graph: Graph) -> int:
    """Load an in-memory rdflib ``graph`` into ``store``. Returns triple count.

    Intended to be called once on a fresh store. New ids continue past any ids
    already present, but terms are not de-duplicated against earlier loads.
    """
    con = store.connection
    next_id = con.execute("SELECT COALESCE(MAX(Node), -1) FROM Nodes").fetchone()[0] + 1

    term_to_id: dict = {}
    iris: List[Tuple[int, str]] = []
    blanks: List[Tuple[int, str]] = []
    literals: List[Tuple[int, str, str, object]] = []
    numerics: List[Tuple[int, float]] = []
    triples: List[Tuple[int, str, int]] = []

    def intern(term: Identifier) -> int:
        nonlocal next_id
        tid = term_to_id.get(term)
        if tid is not None:
            return tid
        tid = next_id
        next_id += 1
        term_to_id[term] = tid
        if isinstance(term, URIRef):
            iris.append((tid, str(term)))
        elif isinstance(term, BNode):
            blanks.append((tid, str(term)))
        elif isinstance(term, Literal):
            literals.append((tid, str(term), str(sparql_datatype(term)), term.language))
            value = numeric_value(term)
            if value is not None:
                numerics.append((tid, value))
        else:
            raise TypeError(f"Unsupported RDF term type: {type(term)!r}")
        return tid

    count = 0
    for s, p, o in graph:
        triples.append((intern(s), str(p), intern(o)))
        count += 1

    nodes = [(tid,) for tid in term_to_id.values()]
    _insert_many(con, "Nodes", nodes)
    _insert_many(con, "IRIs", iris)
    _insert_many(con, "Blanks", blanks)
    _insert_many(con, "Literals", literals)
    _insert_many(con, "Numerics", numerics)
    _insert_many(con, "Triples", triples)
    return count


def _insert_many(con: duckdb.DuckDBPyConnection, table: str, rows: list) -> None:
    if not rows:
        return
    placeholders = ",".join(["?"] * len(rows[0]))
    con.executemany(f"INSERT INTO {table} VALUES ({placeholders})", rows)
