"""Translate a SHACL Logical Syntax tree (slsparser ``SANode``) into SQL.

The input shape is assumed to be *expanded* (no ``HASSHAPE``) and in *negation
normal form*, so that ``Op.NOT`` only ever wraps an atomic constraint. That lets
us drive positive and negative translation from one place: structural operators
(AND/OR/COUNTRANGE/FORALL/TOP/BOT) are handled in :func:`translate_node`, and
every atom is handled by :func:`_translate_atom` with a ``negated`` flag that
selects the ``_get_*`` vs ``_get_neg_*`` builder.

Only simple paths (a property or an inverse property) are supported; general
property paths are out of scope (as in the prototype and the paper).
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from rdflib import Literal, SH, RDF
from rdflib.term import IdentifiedNode

from slsparser.shapels import SANode, Op
from slsparser.pathls import PANode, POp
from slsparser.utilities import expand_shape, negation_normal_form

from quackl import querylib as ql


# -- public translation -----------------------------------------------------

def translate_node(node: SANode) -> str:
    """Translate an expanded, NNF shape ``node`` into a unary SQL query."""
    op = node.op

    if op == Op.TOP:
        return ql._get_top()
    if op == Op.BOT:
        return ql._get_bot()

    if op == Op.AND:
        return ql._get_and([translate_node(c) for c in node.children])
    if op == Op.OR:
        return ql._get_or([translate_node(c) for c in node.children])

    if op == Op.COUNTRANGE:
        lower = int(node.children[0])
        upper = None if node.children[1] is None else int(node.children[1])
        pred = node.children[2]
        _require_simple_path(pred)
        subshape = node.children[3]
        istop = subshape.op == Op.TOP
        subquery = "" if istop else translate_node(subshape)
        return ql._get_countrange(lower, upper, pred, subquery, top=istop)

    if op == Op.FORALL:
        pred = node.children[0]
        _require_simple_path(pred)
        return ql._get_forall(pred, translate_node(node.children[1]))

    if op == Op.NOT:
        # NNF guarantees the child is an atom.
        return _translate_atom(node.children[0], negated=True)

    return _translate_atom(node, negated=False)


# -- atoms ------------------------------------------------------------------

def _translate_atom(node: SANode, negated: bool) -> str:
    op = node.op

    if op == Op.TOP:
        return ql._get_bot() if negated else ql._get_top()
    if op == Op.BOT:
        return ql._get_top() if negated else ql._get_bot()

    if op == Op.HASVALUE:
        builder = ql._get_neg_hasvalue if negated else ql._get_hasvalue
        return builder(node.children[0])

    if op == Op.EQ:
        return _translate_eq(node, negated)
    if op == Op.DISJ:
        return _translate_disj(node, negated)

    if op == Op.CLOSED:
        builder = ql._get_neg_closed if negated else ql._get_closed
        return builder(node.children)

    if op == Op.LESSTHAN:
        _require_simple_path(node.children[0])
        builder = ql._get_neg_lessthan if negated else ql._get_lessthan
        return builder(node.children[0], node.children[1])
    if op == Op.LESSTHANEQ:
        _require_simple_path(node.children[0])
        builder = ql._get_neg_lessthaneq if negated else ql._get_lessthaneq
        return builder(node.children[0], node.children[1])

    if op == Op.UNIQUELANG:
        _require_simple_path(node.children[0])
        builder = ql._get_neg_uniquelang if negated else ql._get_uniquelang
        return builder(node.children[0])

    if op == Op.TEST:
        return _translate_test(node, negated)

    raise NotImplementedError(
        f"SA operation {op} (negated={negated}) is not supported"
    )


def _translate_eq(node: SANode, negated: bool) -> str:
    pred_p, pred_q = node.children[0], node.children[1]
    if pred_p.pop == POp.ID:
        builder = ql._get_neg_eq_id if negated else ql._get_eq_id
        return builder(pred_q)
    _require_simple_path(pred_p)
    builder = ql._get_neg_eq_pq if negated else ql._get_eq_pq
    return builder(pred_p, pred_q)


def _translate_disj(node: SANode, negated: bool) -> str:
    pred_p, pred_q = node.children[0], node.children[1]
    if pred_p.pop == POp.ID:
        builder = ql._get_neg_disj_id if negated else ql._get_disj_id
        return builder(pred_q)
    _require_simple_path(pred_p)
    builder = ql._get_neg_disj_pq if negated else ql._get_disj_pq
    return builder(pred_p, pred_q)


def _translate_test(node: SANode, negated: bool) -> str:
    cc = node.children[0]

    if cc == SH.NodeKindConstraintComponent:
        return _translate_nodekind(node.children[1], negated)

    if cc == SH.DatatypeConstraintComponent:
        builder = ql._get_neg_test_datatype if negated else ql._get_test_datatype
        return builder(node.children[1])

    if cc == "numeric_range":
        min_, minincl, max_, maxincl = _parse_numeric_range(node.children)
        builder = ql._get_neg_test_numeric_range if negated else ql._get_test_numeric_range
        return builder(min_, minincl, max_, maxincl)

    if cc == "length_range":
        min_, max_ = _parse_length_range(node.children)
        builder = ql._get_neg_test_length_range if negated else ql._get_test_length_range
        return builder(min_, max_)

    if cc == SH.PatternConstraintComponent:
        pattern = str(node.children[1])
        flags = node.children[2] if len(node.children) > 2 else []
        builder = ql._get_neg_test_pattern if negated else ql._get_test_pattern
        return builder(pattern, flags)

    if cc == SH.LanguageInConstraintComponent:
        builder = ql._get_neg_test_languagein if negated else ql._get_test_languagein
        return builder(node.children[1])

    raise NotImplementedError(f"Test constraint {cc} is not supported")


_NODEKIND_POS = {
    SH.IRI: ql._get_test_nodekind_iri,
    SH.BlankNode: ql._get_test_nodekind_blank,
    SH.Literal: ql._get_test_nodekind_literal,
}
_NODEKIND_NEG = {
    SH.IRI: ql._get_neg_test_nodekind_iri,
    SH.BlankNode: ql._get_neg_test_nodekind_blank,
    SH.Literal: ql._get_neg_test_nodekind_literal,
}
# The three composite kinds are unions of the basic ones.
_NODEKIND_COMPOSITE = {
    SH.IRIOrLiteral: (SH.IRI, SH.Literal),
    SH.BlankNodeOrIRI: (SH.IRI, SH.BlankNode),
    SH.BlankNodeOrLiteral: (SH.Literal, SH.BlankNode),
}


def _translate_nodekind(kind, negated: bool) -> str:
    table = _NODEKIND_NEG if negated else _NODEKIND_POS
    if kind in table:
        return table[kind]()
    if kind in _NODEKIND_COMPOSITE:
        # NOT(a OR b) == NOT a INTERSECT NOT b; (a OR b) == a UNION b.
        parts = [table[k]() for k in _NODEKIND_COMPOSITE[kind]]
        joiner = " INTERSECT " if negated else " UNION "
        return joiner.join(f"({p})" for p in parts)
    raise ValueError(f"Unknown nodeKind: {kind!r}")


# -- TEST argument parsing --------------------------------------------------

def _parse_numeric_range(children: list) -> Tuple[Optional[float], bool, Optional[float], bool]:
    min_, minincl = _range_bound(children, SH.MinInclusiveConstraintComponent,
                                 SH.MinExclusiveConstraintComponent)
    max_, maxincl = _range_bound(children, SH.MaxInclusiveConstraintComponent,
                                 SH.MaxExclusiveConstraintComponent)
    min_ = None if min_ is None else float(min_)
    max_ = None if max_ is None else float(max_)
    return min_, minincl, max_, maxincl


def _parse_length_range(children: list) -> Tuple[Optional[int], Optional[int]]:
    min_, _ = _range_bound(children, SH.MinLengthConstraintComponent, None)
    max_, _ = _range_bound(children, SH.MaxLengthConstraintComponent, None)
    min_ = None if min_ is None else int(min_)
    max_ = None if max_ is None else int(max_)
    return min_, max_


def _range_bound(children: list, inclusive_cc, exclusive_cc):
    """Return ``(value, is_inclusive)`` for a bound, or ``(None, False)``.

    The value follows its constraint-component marker in ``children``.
    """
    if inclusive_cc in children:
        return children[children.index(inclusive_cc) + 1], True
    if exclusive_cc is not None and exclusive_cc in children:
        return children[children.index(exclusive_cc) + 1], False
    return None, False


# -- paths ------------------------------------------------------------------

def _require_simple_path(pred: PANode) -> None:
    if pred.pop == POp.PROP:
        return
    if pred.pop == POp.INV and pred.children[0].pop == POp.PROP:
        return
    raise NotImplementedError(
        "Only simple paths (a property or an inverse property) are supported; "
        "general property paths are out of scope."
    )


# -- conformance / validation queries ---------------------------------------

def translate_conformance_shapes(
    definitions: Dict[IdentifiedNode, SANode],
    targets: Dict[IdentifiedNode, SANode],
) -> Dict[IdentifiedNode, str]:
    """Per shape with a target, the SQL for ``(targets) EXCEPT (conformers)``.

    Returned keyed by shape name, so callers can later attribute each violation
    to the shape that produced it (the seam for a full validation report).
    Shapes whose target is empty (``Op.BOT``) are skipped: they can never have a
    violation.
    """
    conformance: Dict[IdentifiedNode, str] = {}
    for name, target in targets.items():
        if target.op == Op.BOT:
            continue
        target_sql = translate_node(_replace_classconstraint(target))
        shape = negation_normal_form(expand_shape(definitions, definitions[name]))
        shape_sql = translate_node(_replace_classconstraint(shape))
        conformance[name] = f"({target_sql})\nEXCEPT\n({shape_sql})"
    return conformance


def translate_conformance_all(
    definitions: Dict[IdentifiedNode, SANode],
    targets: Dict[IdentifiedNode, SANode],
) -> Optional[str]:
    """A single query unioning every shape's violations, or ``None`` if none."""
    conformance = translate_conformance_shapes(definitions, targets)
    if not conformance:
        return None
    return " UNION ".join(f"({sql})" for sql in conformance.values())


def _replace_classconstraint(node: SANode) -> SANode:
    """Rewrite the ``rdf:type/rdfs:subClassOf*`` targetClass path into a direct
    ``rdf:type`` step, matching the prototype/paper's simplification to direct
    type declarations (so the simple-path query builders apply)."""
    if (node.op == Op.COUNTRANGE
            and int(node.children[0]) == 1
            and node.children[1] is None
            and node.children[2].pop == POp.COMP
            and node.children[2].children[1].pop == POp.KLEENE):
        return SANode(Op.COUNTRANGE,
                      [Literal(1), None, PANode(POp.PROP, [RDF.type]), node.children[3]])

    new_children: List = []
    for child in node.children:
        if isinstance(child, SANode):
            new_children.append(_replace_classconstraint(child))
        else:
            new_children.append(child)
    return SANode(node.op, new_children)
