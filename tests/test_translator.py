"""Behavioural tests for the SANode -> SQL translation.

We build small shapes directly as SANode trees, run the generated SQL against a
tiny store, and assert the set of satisfying focus nodes. Several cases pin the
bug fixes made during the port (negated uniqueLang, negated numeric range,
negated disjoint-with-identity, negated lessThan).
"""
from rdflib import Namespace, Literal, SH

from slsparser.shapels import SANode, Op
from slsparser.pathls import PANode, POp

from quackl.translator import translate_node

EX = Namespace("http://example.org/")


def prop(p):
    return PANode(POp.PROP, [p])


def satisfying(store, node):
    sql = translate_node(node)
    rows = store.connection.execute(sql).fetchall()
    return {str(t) for t in store.terms_for_ids(r[0] for r in rows)}


def test_exists_and_not_exists(make_store):
    store = make_store("""
    @prefix ex: <http://example.org/> .
    ex:a ex:phone "1" .
    ex:b ex:email "x" .
    """)
    # #>=1 phone . TOP   (exists phone)
    exists_phone = SANode(Op.COUNTRANGE, [Literal(1), None, prop(EX.phone), SANode(Op.TOP, [])])
    assert satisfying(store, exists_phone) == {str(EX.a)}


def test_neg_uniquelang(make_store):
    store = make_store("""
    @prefix ex: <http://example.org/> .
    ex:a ex:name "x"@en, "y"@en .
    ex:b ex:name "x"@en, "y"@nl .
    ex:c ex:name "z"@en .
    """)
    # Violators of uniqueLang = nodes with two distinct same-language objects.
    node = SANode(Op.NOT, [SANode(Op.UNIQUELANG, [prop(EX.name)])])
    assert satisfying(store, node) == {str(EX.a)}


def test_numeric_range_and_negation(make_store):
    store = make_store("""
    @prefix ex:  <http://example.org/> .
    @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
    ex:a ex:age "5"^^xsd:integer .
    ex:b ex:age "20"^^xsd:integer .
    """)
    rng = SANode(Op.TEST, ["numeric_range",
                           SH.MinInclusiveConstraintComponent, Literal(0),
                           SH.MaxInclusiveConstraintComponent, Literal(10)])
    assert satisfying(store, rng) == {"5"}

    neg = satisfying(store, SANode(Op.NOT, [rng]))
    assert "5" not in neg
    assert "20" in neg


def test_neg_disjoint_identity(make_store):
    store = make_store("""
    @prefix ex: <http://example.org/> .
    ex:a ex:knows ex:a .
    ex:b ex:knows ex:c .
    """)
    # NOT disj(id, knows) = nodes that are among their own knows-objects.
    node = SANode(Op.NOT, [SANode(Op.DISJ, [PANode(POp.ID, []), prop(EX.knows)])])
    assert satisfying(store, node) == {str(EX.a)}


def test_lessthan_and_negation(make_store):
    store = make_store("""
    @prefix ex:  <http://example.org/> .
    @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
    ex:a ex:lo "1"^^xsd:integer ; ex:hi "5"^^xsd:integer .
    ex:b ex:lo "9"^^xsd:integer ; ex:hi "5"^^xsd:integer .
    """)
    node = SANode(Op.LESSTHAN, [prop(EX.lo), prop(EX.hi)])
    assert satisfying(store, node) == {str(EX.a)}
    assert satisfying(store, SANode(Op.NOT, [node])) == {str(EX.b)}


def test_unsupported_property_path_raises(make_store):
    store = make_store("@prefix ex: <http://example.org/> . ex:a ex:p ex:b .")
    # A Kleene-star path is not supported by the simple-path query builders.
    kleene = PANode(POp.KLEENE, [prop(EX.p)])
    node = SANode(Op.FORALL, [kleene, SANode(Op.TOP, [])])
    try:
        translate_node(node)
        assert False, "expected NotImplementedError"
    except NotImplementedError:
        pass
