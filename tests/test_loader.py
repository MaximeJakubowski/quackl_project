from rdflib import Graph, RDF, XSD

from quackl import Store, load_graph

DATA = """
@prefix ex:  <http://example.org/> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
ex:a ex:name "Alice" ;
     ex:label "Alicia"@es ;
     ex:age "30"^^xsd:integer ;
     ex:score "1.5"^^xsd:decimal ;
     ex:knows ex:b .
ex:b ex:name "Bob" .
"""


def _count(store, table):
    return store.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_triple_and_node_counts():
    store = Store.create()
    n = load_graph(store, Graph().parse(data=DATA, format="turtle"))
    assert n == 6  # number of triples in DATA

    # Distinct terms: ex:a, ex:b (predicates such as ex:name are not pooled),
    # "Alice", "Alicia"@es, 30, 1.5, "Bob" -> 2 IRIs + 5 literals = 7 nodes.
    assert _count(store, "IRIs") == 2          # ex:a, ex:b (predicates are not pooled)
    assert _count(store, "Literals") == 5      # Alice, Alicia@es, 30, 1.5, Bob
    assert _count(store, "Nodes") == 7
    assert _count(store, "Triples") == 6
    store.close()


def test_literal_type_defaults():
    store = Store.create()
    load_graph(store, Graph().parse(data=DATA, format="turtle"))

    rows = dict(store.connection.execute(
        "SELECT Value, Type FROM Literals WHERE Lang IS NULL"
    ).fetchall())
    # Plain string literal stores xsd:string.
    assert rows["Alice"] == str(XSD.string)
    assert rows["Bob"] == str(XSD.string)
    assert rows["30"] == str(XSD.integer)

    # Language-tagged literal stores rdf:langString and keeps the tag.
    lang = store.connection.execute(
        "SELECT Type, Lang FROM Literals WHERE Value = 'Alicia'"
    ).fetchone()
    assert lang == (str(RDF.langString), "es")
    store.close()


def test_numeric_extraction():
    store = Store.create()
    load_graph(store, Graph().parse(data=DATA, format="turtle"))

    numerics = dict(store.connection.execute(
        "SELECT l.Value, n.Value FROM Numerics n JOIN Literals l ON n.Node = l.Node"
    ).fetchall())
    assert numerics == {"30": 30.0, "1.5": 1.5}  # only numeric literals
    store.close()
