"""Helpers for mapping RDF terms onto the relational representation.

These are shared by the loader (which writes the ``Literals``/``Numerics`` rows)
and ``querylib`` (which generates SQL comparing against those rows), so that the
two always agree on, e.g., the datatype stored for a plain string literal.
"""
from __future__ import annotations

from typing import Optional

from rdflib import Literal, URIRef, BNode, RDF, XSD
from rdflib.term import Identifier

# xsd numeric datatypes whose literals get a row in the Numerics table.
NUMERIC_DATATYPES = frozenset({
    XSD.integer, XSD.decimal, XSD.float, XSD.double,
    XSD.nonPositiveInteger, XSD.negativeInteger, XSD.long, XSD.int,
    XSD.short, XSD.byte, XSD.nonNegativeInteger, XSD.unsignedLong,
    XSD.unsignedInt, XSD.unsignedShort, XSD.unsignedByte, XSD.positiveInteger,
})


def sparql_datatype(term: Literal) -> URIRef:
    """The effective datatype IRI stored in ``Literals.Type`` for ``term``.

    Follows the SPARQL/SHACL convention: a language-tagged literal has type
    ``rdf:langString``; an untyped, language-less literal has type
    ``xsd:string``; otherwise the declared datatype.
    """
    if term.language:
        return RDF.langString
    if term.datatype is None:
        return XSD.string
    return term.datatype


def numeric_value(term: Literal) -> Optional[float]:
    """Return the ``double`` value for a numeric literal, else ``None``."""
    if term.datatype not in NUMERIC_DATATYPES:
        return None
    try:
        return float(term.toPython())
    except (ValueError, TypeError):
        return None


def escape_singlequote(value: str) -> str:
    """Escape single quotes for inlining into a SQL string literal."""
    return value.replace("'", "''")


def term_kind(term: Identifier) -> str:
    """Classify an RDF term as ``'iri'``, ``'blank'`` or ``'literal'``."""
    if isinstance(term, URIRef):
        return "iri"
    if isinstance(term, BNode):
        return "blank"
    if isinstance(term, Literal):
        return "literal"
    raise TypeError(f"Unsupported RDF term type: {type(term)!r}")
