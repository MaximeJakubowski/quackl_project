"""The relational representation of an RDF graph used by quackl.

This is the single source of truth for the schema that the SQL generated in
:mod:`quackl.querylib` runs against. It mirrors the "pooling" representation of
the *Compiling SHACL into SQL* paper: every RDF term gets a unique integer
``Node`` id, used in the central ``Triples`` relation. The representation is
intentionally unoptimized (no extra indexes); DuckDB maintains min-max indexes
automatically.
"""
from __future__ import annotations

import duckdb

# Names of every table in the schema, handy for resetting/inspecting a store.
TABLES = ("Nodes", "IRIs", "Blanks", "Literals", "Numerics", "Triples")

_DDL = """
CREATE TABLE IF NOT EXISTS Nodes (
    Node BIGINT
);
CREATE TABLE IF NOT EXISTS IRIs (
    Node BIGINT,
    Value VARCHAR
);
CREATE TABLE IF NOT EXISTS Blanks (
    Node BIGINT,
    Alias VARCHAR
);
CREATE TABLE IF NOT EXISTS Literals (
    Node BIGINT,
    Value VARCHAR,
    Type VARCHAR,
    Lang VARCHAR
);
CREATE TABLE IF NOT EXISTS Numerics (
    Node BIGINT,
    Value DOUBLE
);
CREATE TABLE IF NOT EXISTS Triples (
    Subject BIGINT,
    Predicate VARCHAR,
    Object BIGINT
);
"""


def create_schema(con: duckdb.DuckDBPyConnection) -> None:
    """Create the (empty) quackl tables on ``con`` if they do not yet exist."""
    con.execute(_DDL)


def is_populated(con: duckdb.DuckDBPyConnection) -> bool:
    """Whether the schema tables exist on ``con``."""
    rows = con.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_name IN ('Nodes','IRIs','Blanks','Literals','Numerics','Triples')"
    ).fetchall()
    return len(rows) == len(TABLES)
