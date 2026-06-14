"""SQL fragment builders for atomic and structural shape constraints.

Each function returns a SQL ``SELECT`` returning a ``Node`` column: the set of
nodes satisfying (``_get_*``) or violating (``_get_neg_*``) the constraint,
against the schema in :mod:`quackl.schema`.

Ported from the ``shuq`` prototype, with bug fixes (see module history / the
package README): the ``Tripples`` typo in negated uniqueLang, unbalanced
parentheses and an ``AND``/operator mistake in the negated numeric range, the
``Subject AS NODE`` alias casing, and an ``AND``-should-be-``OR`` in the negated
length range.
"""
from __future__ import annotations

from typing import List, Optional

from rdflib import URIRef, BNode, Literal

from slsparser.pathls import PANode, POp
from quackl.rdfterms import sparql_datatype, escape_singlequote


# -- structural -------------------------------------------------------------

def _get_top() -> str:
    return "SELECT Node FROM Nodes"


def _get_bot() -> str:
    return "SELECT Node FROM Nodes WHERE false"


def _get_and(subqueries: List[str]) -> str:
    return " INTERSECT ".join(f"({q})" for q in subqueries)


def _get_or(subqueries: List[str]) -> str:
    return " UNION ".join(f"({q})" for q in subqueries)


# -- path helpers -----------------------------------------------------------

def _pred_iri(pred: PANode) -> str:
    """The predicate IRI of a PROP step or an INV-of-PROP step."""
    if pred.pop == POp.INV:
        return str(pred.children[0].children[0])
    return str(pred.children[0])


def _is_inverse(pred: PANode) -> bool:
    return pred.pop == POp.INV


# -- equality / disjointness ------------------------------------------------

def _get_eq_pq(pred_p: PANode, pred_q: PANode) -> str:
    p_iri = _pred_iri(pred_p)
    q_iri = str(pred_q.children[0])
    p_inv = _is_inverse(pred_p)
    p_src = "Subject" if not p_inv else "Object"
    p_tgt = "Object" if not p_inv else "Subject"
    return f"""
        SELECT Node FROM Nodes WHERE NOT EXISTS (
            ((  SELECT {p_tgt}
                FROM Triples
                WHERE Predicate = '{p_iri}'
                    AND {p_src} = Node
             ) EXCEPT (
                SELECT Object
                FROM Triples
                WHERE Predicate = '{q_iri}'
                    AND Subject = Node
             )) UNION ((
                SELECT Object
                FROM Triples
                WHERE Predicate = '{q_iri}'
                    AND Subject = Node
             ) EXCEPT (
                SELECT {p_tgt}
                FROM Triples
                WHERE Predicate = '{p_iri}'
                    AND {p_src} = Node )))
        """


def _get_eq_id(pred: PANode) -> str:
    p_iri = str(pred.children[0])
    return f"""
        SELECT Subject AS Node
        FROM Triples AS T1
        WHERE Predicate = '{p_iri}'
            AND Subject = Object
            AND NOT EXISTS (
                SELECT *
                FROM Triples AS T2 WHERE Predicate = '{p_iri}'
                    AND T2.Subject = T1.Subject
                    AND T2.Object <> T1.Object )
        """


def _get_disj_pq(pred_p: PANode, pred_q: PANode) -> str:
    return f"SELECT Node FROM Nodes EXCEPT ({_get_neg_disj_pq(pred_p, pred_q)})"


def _get_disj_id(pred: PANode) -> str:
    return f"SELECT Node FROM Nodes EXCEPT ({_get_neg_disj_id(pred)})"


# -- closed -----------------------------------------------------------------

def _get_closed(preds: List[PANode]) -> str:
    return f"SELECT Node FROM Nodes EXCEPT ({_get_neg_closed(preds)})"


# -- lessThan / lessThanEq --------------------------------------------------

def _get_lessthan(pred_p: PANode, pred_q: PANode, eq: bool = False) -> str:
    p_iri = _pred_iri(pred_p)
    q_iri = str(pred_q.children[0])
    p_inv = _is_inverse(pred_p)
    p_src = "Subject" if not p_inv else "Object"
    p_tgt = "Object" if not p_inv else "Subject"
    return f"""
        SELECT Node FROM Nodes WHERE (
            SELECT MAX(N.Value)
            FROM Triples AS T, Numerics AS N
            WHERE T.{p_src} = Nodes.Node
                AND T.Predicate = '{p_iri}'
                AND T.{p_tgt} = N.Node
                ) {'<' if not eq else '<='} (
            SELECT MIN(N.Value)
            FROM Triples AS T, Numerics AS N
            WHERE T.Subject = Nodes.Node
                AND T.Predicate = '{q_iri}'
                AND T.Object = N.Node )
    """


def _get_lessthaneq(pred_p: PANode, pred_q: PANode) -> str:
    return _get_lessthan(pred_p, pred_q, eq=True)


# -- uniqueLang -------------------------------------------------------------

def _get_uniquelang(pred: PANode) -> str:
    p_iri = _pred_iri(pred)
    p_inv = _is_inverse(pred)
    p_src = "Subject" if not p_inv else "Object"
    p_tgt = "Object" if not p_inv else "Subject"
    return f"""
      SELECT Node FROM Nodes WHERE NOT EXISTS (
            SELECT L.Lang
            FROM Triples AS T, Literals AS L
            WHERE T.{p_src} = Nodes.Node
                AND T.Predicate = '{p_iri}'
                AND T.{p_tgt} = L.Node
                AND L.Lang IS NOT NULL
                GROUP BY L.Lang
                HAVING COUNT(*) > 1 )
    """


# -- countrange / forall ----------------------------------------------------

def _get_countrange(lower: int, upper: Optional[int], pred: PANode,
                    subquery: str, top: bool = False) -> str:
    p_iri = _pred_iri(pred)
    p_inv = _is_inverse(pred)
    p_src = "Subject" if not p_inv else "Object"
    p_tgt = "Object" if not p_inv else "Subject"

    # lower 0, no upper: every node qualifies.
    if lower == 0 and upper is None:
        return _get_top()

    # qualified max-count: complement of "at least upper+1".
    if lower == 0 and upper is not None:
        return f"""
        SELECT Node FROM Nodes
        WHERE Node NOT IN ({_get_countrange(upper + 1, None, pred, subquery, top=top)})
        """

    group_clause = "" if upper is None and lower == 1 else f"""
        GROUP BY {p_src}
        HAVING COUNT(*) >= {lower} {f"AND COUNT(*) <= {upper}" if upper is not None else ""}"""

    if lower == upper:
        group_clause = f"""
            GROUP BY {p_src}
            HAVING COUNT(*) = {lower}
        """

    return f"""
        SELECT {p_src} AS Node
        FROM Triples{f", ({subquery}) AS Q(Node)" if not top else ""}
        WHERE Predicate = '{p_iri}'
            {f"AND {p_tgt} = Q.Node" if not top else ""}
            {group_clause}
        """


def _get_forall(pred: PANode, subquery: str) -> str:
    p_iri = _pred_iri(pred)
    p_inv = _is_inverse(pred)
    p_src = "Subject" if not p_inv else "Object"
    p_tgt = "Object" if not p_inv else "Subject"
    return f"""
        SELECT Node FROM Nodes WHERE NOT EXISTS (
            SELECT *
            FROM Triples
            WHERE Predicate = '{p_iri}'
                AND {p_src} = Node
                AND {p_tgt} NOT IN ({subquery}) )
    """


# -- hasValue ---------------------------------------------------------------

def _get_hasvalue(term) -> str:
    if isinstance(term, URIRef):
        return f"SELECT Node FROM IRIs WHERE Value = '{escape_singlequote(str(term))}'"

    if isinstance(term, BNode):
        return f"SELECT Node FROM Blanks WHERE Alias = '{escape_singlequote(str(term))}'"

    if isinstance(term, Literal):
        datatype = sparql_datatype(term)
        return f"""
            SELECT Node
            FROM Literals
            WHERE Value = '{escape_singlequote(str(term))}'
                AND Type = '{datatype}'
                AND Lang {f"= '{term.language}'" if term.language is not None else "IS NULL"}
        """
    raise TypeError(f"hasValue with unsupported term type: {type(term)!r}")


def _get_neg_hasvalue(term) -> str:
    if isinstance(term, URIRef):
        return f"""
            SELECT Node FROM Literals
            UNION
            SELECT Node FROM Blanks
            UNION
            SELECT Node FROM IRIs WHERE Value <> '{escape_singlequote(str(term))}'
        """

    if isinstance(term, BNode):
        return f"""
            SELECT Node FROM Literals
            UNION
            SELECT Node FROM IRIs
            UNION
            SELECT Node FROM Blanks
            WHERE Alias <> '{escape_singlequote(str(term))}'
        """

    if isinstance(term, Literal):
        datatype = sparql_datatype(term)
        return f"""
            SELECT Node FROM IRIs
            UNION
            SELECT Node FROM Blanks
            UNION
            SELECT Node FROM Literals
            WHERE Value <> '{escape_singlequote(str(term))}'
                OR Type <> '{datatype}'
                {"OR Lang IS NOT NULL" if term.language is None else
                 f"OR Lang <> '{term.language}'"}
        """
    raise TypeError(f"hasValue with unsupported term type: {type(term)!r}")


# -- node tests -------------------------------------------------------------

def _get_test_nodekind_iri() -> str:
    return "SELECT Node FROM IRIs"


def _get_test_nodekind_blank() -> str:
    return "SELECT Node FROM Blanks"


def _get_test_nodekind_literal() -> str:
    return "SELECT Node FROM Literals"


def _get_test_datatype(d: URIRef) -> str:
    return f"SELECT Node FROM Literals WHERE Type = '{d}'"


def _numeric_range_condition(min_: Optional[int], minincl: bool,
                             max_: Optional[int], maxincl: bool) -> str:
    parts = []
    if min_ is not None:
        parts.append(f"Value {'>=' if minincl else '>'} {min_}")
    if max_ is not None:
        parts.append(f"Value {'<=' if maxincl else '<'} {max_}")
    return " AND ".join(parts)


def _get_test_numeric_range(min_, minincl, max_, maxincl) -> str:
    if min_ is None and max_ is None:
        raise ValueError("Both min and max are None!")
    return f"""
    SELECT Node FROM Numerics
    WHERE {_numeric_range_condition(min_, minincl, max_, maxincl)}
    """


def _length_condition(min_: Optional[int], max_: Optional[int], negate: bool) -> str:
    parts = []
    if negate:
        if min_ is not None:
            parts.append(f"length(Value) < {min_}")
        if max_ is not None:
            parts.append(f"length(Value) > {max_}")
        return " OR ".join(parts)
    if min_ is not None:
        parts.append(f"length(Value) >= {min_}")
    if max_ is not None:
        parts.append(f"length(Value) <= {max_}")
    return " AND ".join(parts)


def _get_test_length_range(min_, max_) -> str:
    cond = _length_condition(min_, max_, negate=False)
    return f"""
    (SELECT Node FROM Literals WHERE {cond})
    UNION
    (SELECT Node FROM IRIs WHERE {cond})
    """


def _pattern_match(pattern: str, flags: str, negate: bool = False) -> str:
    args = f"'{pattern}'" + (f", '{flags[0]}'" if len(flags) > 0 else "")
    call = f"regexp_full_match(Value, {args})"
    return f"NOT {call}" if negate else call


def _get_test_pattern(pattern: str, flags: str) -> str:
    cond = _pattern_match(pattern, flags)
    return f"""
    (SELECT Node FROM Literals WHERE {cond})
    UNION
    (SELECT Node FROM IRIs WHERE {cond})
    """


def _get_test_languagein(langs: List[str]) -> str:
    langliststr = ",".join(f"'{lang}'" for lang in langs)
    return f"SELECT Node FROM Literals WHERE Lang IN ({langliststr})"


# -- negated equality / disjointness ----------------------------------------

def _get_neg_eq_pq(pred_p: PANode, pred_q: PANode) -> str:
    p_iri = _pred_iri(pred_p)
    q_iri = str(pred_q.children[0])
    p_inv = _is_inverse(pred_p)
    p_src = "Subject" if not p_inv else "Object"
    p_tgt = "Object" if not p_inv else "Subject"
    return f"""
    SELECT Node FROM Nodes WHERE EXISTS ((
        SELECT * FROM Triples
        WHERE Predicate = '{p_iri}'
            AND {p_tgt} NOT IN (
                SELECT Object From Triples
                WHERE Subject = Node
                    AND Predicate = '{q_iri}' )
        ) UNION (
        SELECT * FROM Triples
        WHERE Predicate = '{q_iri}'
            AND Object NOT IN (
                SELECT {p_tgt} From Triples
                WHERE {p_src} = Node
                    AND Predicate = '{p_iri}' )))
    """


def _get_neg_eq_id(pred: PANode) -> str:
    p_iri = str(pred.children[0])
    return f"""
        SELECT Node FROM Nodes
        WHERE Node NOT IN (
            SELECT * FROM Triples
            WHERE Subject = Node
                AND Predicate = '{p_iri}'
            ) OR EXISTS (
            SELECT * FROM Triples
            WHERE Predicate = '{p_iri}'
                AND Object <> Node )
        """


def _get_neg_disj_pq(pred_p: PANode, pred_q: PANode) -> str:
    p_iri = _pred_iri(pred_p)
    q_iri = str(pred_q.children[0])
    p_inv = _is_inverse(pred_p)
    p_src = "Subject" if not p_inv else "Object"
    p_tgt = "Object" if not p_inv else "Subject"
    return f"""
        SELECT T1.{p_src} AS Node
        FROM Triples AS T1, Triples AS T2
        WHERE T1.{p_src} = T2.Subject
            AND T1.Predicate = '{p_iri}'
            AND T2.Predicate = '{q_iri}'
            AND T1.{p_tgt} = T2.Object
    """


def _get_neg_disj_id(pred: PANode) -> str:
    p_iri = str(pred.children[0])
    return f"""
        SELECT Subject AS Node
        FROM Triples
        WHERE Predicate = '{p_iri}'
              AND Subject = Object
    """


def _get_neg_closed(preds: List[PANode]) -> str:
    predliststr = ",".join(f"'{p.children[0]}'" for p in preds)
    return f"""
        SELECT Subject AS Node
        FROM Triples
        WHERE Predicate NOT IN ({predliststr})
    """


# -- negated lessThan / uniqueLang ------------------------------------------

def _get_neg_lessthan(pred_p: PANode, pred_q: PANode, eq: bool = False) -> str:
    p_iri = _pred_iri(pred_p)
    q_iri = str(pred_q.children[0])
    p_inv = _is_inverse(pred_p)
    p_src = "Subject" if not p_inv else "Object"
    p_tgt = "Object" if not p_inv else "Subject"
    return f"""
        SELECT T1.{p_src} AS Node
        FROM Triples AS T1, Triples AS T2,
            Numerics AS N1, Numerics AS N2
        WHERE T1.{p_src} = T2.Subject
            AND T1.Predicate = '{p_iri}'
            AND T2.Predicate = '{q_iri}'
            AND T1.{p_tgt} = N1.Node
            AND T2.Object = N2.Node
            AND N1.Value {'>=' if not eq else '>'} N2.Value
    """


def _get_neg_lessthaneq(pred_p: PANode, pred_q: PANode) -> str:
    return _get_neg_lessthan(pred_p, pred_q, eq=True)


def _get_neg_uniquelang(pred: PANode) -> str:
    p_iri = _pred_iri(pred)
    p_inv = _is_inverse(pred)
    p_src = "Subject" if not p_inv else "Object"
    p_tgt = "Object" if not p_inv else "Subject"
    return f"""
        SELECT T1.{p_src} AS Node
        FROM Triples AS T1, Triples AS T2,
            Literals AS L1, Literals AS L2
        WHERE T1.{p_src} = T2.{p_src}
            AND T1.Predicate = '{p_iri}'
            AND T2.Predicate = '{p_iri}'
            AND T1.{p_tgt} = L1.Node
            AND T2.{p_tgt} = L2.Node
            AND L1.Lang = L2.Lang
            AND L1.Lang IS NOT NULL
            AND L1.Node <> L2.Node
    """


# -- negated node tests -----------------------------------------------------

def _get_neg_test_nodekind_iri() -> str:
    return """
    SELECT Node FROM Blanks
    UNION
    SELECT Node FROM Literals
    """


def _get_neg_test_nodekind_blank() -> str:
    return """
    SELECT Node FROM IRIs
    UNION
    SELECT Node FROM Literals
    """


def _get_neg_test_nodekind_literal() -> str:
    return """
    SELECT Node FROM Blanks
    UNION
    SELECT Node FROM IRIs
    """


def _get_neg_test_datatype(d: URIRef) -> str:
    return f"""
        SELECT Node FROM IRIs
        UNION
        SELECT Node FROM Blanks
        UNION
        SELECT Node FROM Literals
        WHERE Type <> '{d}'
    """


def _get_neg_test_numeric_range(min_, minincl, max_, maxincl) -> str:
    if min_ is None and max_ is None:
        raise ValueError("Both min and max are None!")
    cond = _numeric_range_condition(min_, minincl, max_, maxincl)
    return f"""
        SELECT Node FROM IRIs
        UNION
        SELECT Node FROM Blanks
        UNION (
            SELECT Node FROM Literals
            EXCEPT (
                SELECT Node FROM Numerics
                WHERE {cond} ) )
    """


def _get_neg_test_length_range(min_, max_) -> str:
    cond = _length_condition(min_, max_, negate=True)
    return f"""
        SELECT Node FROM Blanks
        UNION
        (SELECT Node FROM Literals WHERE {cond})
        UNION
        (SELECT Node FROM IRIs WHERE {cond})
    """


def _get_neg_test_pattern(pattern: str, flags: str) -> str:
    cond = _pattern_match(pattern, flags, negate=True)
    return f"""
        SELECT Node FROM Blanks
        UNION
        (SELECT Node FROM Literals WHERE {cond})
        UNION
        (SELECT Node FROM IRIs WHERE {cond})
    """


def _get_neg_test_languagein(langs: List[str]) -> str:
    langliststr = ",".join(f"'{lang}'" for lang in langs)
    return f"""
        SELECT Node FROM IRIs
        UNION
        SELECT Node FROM Blanks
        UNION
        SELECT Node FROM Literals
        WHERE Lang NOT IN ({langliststr})
            OR Lang IS NULL
    """
