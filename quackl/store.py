"""The DuckDB-backed store of an RDF graph.

A :class:`Store` wraps a single DuckDB connection. It can be backed by an
on-disk ``.duckdb`` file or be purely in-memory. This is what lets loading and
validation be separate steps:

* load once with :meth:`Store.create` (+ :mod:`quackl.loader`), persisting to a
  file, then
* validate later -- even in a different process -- with :meth:`Store.open`.

The store also owns the mapping from internal integer node ids back to RDF
terms (:meth:`terms_for_ids`); this is the seam a richer validation report will
build on later.
"""
from __future__ import annotations

from typing import Iterable, List, Dict

import duckdb
from rdflib import URIRef, BNode, Literal, XSD
from rdflib.term import Identifier

from quackl import schema


class Store:
    """An RDF graph stored in DuckDB."""

    def __init__(self, connection: duckdb.DuckDBPyConnection):
        self._con = connection

    # -- construction ---------------------------------------------------------

    @classmethod
    def create(cls, path: str = ":memory:") -> "Store":
        """Open ``path`` (or in-memory) and create the empty quackl schema.

        Use this before loading data. Pass a file path to persist the store so
        it can be validated against later via :meth:`open`.
        """
        con = duckdb.connect(path)
        schema.create_schema(con)
        return cls(con)

    @classmethod
    def open(cls, path: str, read_only: bool = True) -> "Store":
        """Open an existing, already-loaded ``.duckdb`` file for validation."""
        con = duckdb.connect(path, read_only=read_only)
        if not schema.is_populated(con):
            con.close()
            raise ValueError(
                f"{path!r} does not contain a quackl schema; load data first."
            )
        return cls(con)

    # -- access ---------------------------------------------------------------

    @property
    def connection(self) -> duckdb.DuckDBPyConnection:
        """The live DuckDB connection (used by the validator)."""
        return self._con

    def close(self) -> None:
        self._con.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- node id <-> term mapping --------------------------------------------

    def terms_for_ids(self, ids: Iterable[int]) -> List[Identifier]:
        """Reconstruct RDF terms for the given internal node ids.

        Returns one term per distinct id, in ascending id order.
        """
        unique = sorted({int(i) for i in ids})
        if not unique:
            return []
        # Node ids are integers, so inlining them is safe and keeps this usable
        # on read-only connections (no temp tables needed).
        id_list = ",".join(str(i) for i in unique)
        rows = self._con.execute(f"""
            SELECT Node, 'iri' AS kind, Value AS v,
                   CAST(NULL AS VARCHAR) AS type, CAST(NULL AS VARCHAR) AS lang
            FROM IRIs WHERE Node IN ({id_list})
            UNION ALL
            SELECT Node, 'blank', Alias, CAST(NULL AS VARCHAR), CAST(NULL AS VARCHAR)
            FROM Blanks WHERE Node IN ({id_list})
            UNION ALL
            SELECT Node, 'literal', Value, Type, Lang
            FROM Literals WHERE Node IN ({id_list})
        """).fetchall()

        by_id: Dict[int, Identifier] = {}
        for node, kind, value, type_, lang in rows:
            by_id[node] = _build_term(kind, value, type_, lang)
        return [by_id[i] for i in unique if i in by_id]


def _build_term(kind: str, value: str, type_, lang) -> Identifier:
    if kind == "iri":
        return URIRef(value)
    if kind == "blank":
        return BNode(value)
    # literal
    if lang is not None:
        return Literal(value, lang=lang)
    if type_ is None or URIRef(type_) == XSD.string:
        return Literal(value)
    return Literal(value, datatype=URIRef(type_))
