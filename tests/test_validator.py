"""End-to-end validation tests: data + a SHACL shapes graph -> violating nodes."""
from rdflib import Graph

from quackl import Validator

EX = "http://example.org/"


def violations(store, shapes_ttl):
    shapes = Graph().parse(data=shapes_ttl, format="turtle")
    return {str(t) for t in Validator(store).validate(shapes)}


def test_phone_and_not_email(make_store):
    # Paper Shape 1: a Person must have a phone and must not have an email.
    store = make_store("""
    @prefix ex: <http://example.org/> .
    ex:alice a ex:Person ; ex:phone "111" .
    ex:bob   a ex:Person ; ex:phone "222" ; ex:email "b" .
    ex:carol a ex:Person ; ex:email "c" .
    """)
    result = violations(store, """
    @prefix sh: <http://www.w3.org/ns/shacl#> .
    @prefix ex: <http://example.org/> .
    ex:S a sh:NodeShape ; sh:targetClass ex:Person ;
        sh:property [ sh:path ex:phone ; sh:minCount 1 ] ;
        sh:not [ sh:property [ sh:path ex:email ; sh:minCount 1 ] ] .
    """)
    assert result == {EX + "bob", EX + "carol"}


def test_min_count(make_store):
    store = make_store("""
    @prefix ex: <http://example.org/> .
    ex:a a ex:T ; ex:p ex:x1, ex:x2 .
    ex:b a ex:T ; ex:p ex:x1 .
    ex:c a ex:T .
    """)
    result = violations(store, """
    @prefix sh: <http://www.w3.org/ns/shacl#> .
    @prefix ex: <http://example.org/> .
    ex:S a sh:NodeShape ; sh:targetClass ex:T ;
        sh:property [ sh:path ex:p ; sh:minCount 2 ] .
    """)
    assert result == {EX + "b", EX + "c"}


def test_closed(make_store):
    store = make_store("""
    @prefix ex: <http://example.org/> .
    ex:a ex:p ex:x .
    ex:b ex:p ex:x ; ex:q ex:y .
    """)
    result = violations(store, """
    @prefix sh:  <http://www.w3.org/ns/shacl#> .
    @prefix ex:  <http://example.org/> .
    @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
    ex:S a sh:NodeShape ;
        sh:targetNode ex:a, ex:b ;
        sh:closed true ;
        sh:ignoredProperties ( rdf:type ) ;
        sh:property [ sh:path ex:p ] .
    """)
    assert result == {EX + "b"}


def test_unique_lang(make_store):
    store = make_store("""
    @prefix ex: <http://example.org/> .
    ex:a a ex:T ; ex:name "x"@en, "y"@en .
    ex:b a ex:T ; ex:name "x"@en, "y"@nl .
    """)
    result = violations(store, """
    @prefix sh: <http://www.w3.org/ns/shacl#> .
    @prefix ex: <http://example.org/> .
    ex:S a sh:NodeShape ; sh:targetClass ex:T ;
        sh:property [ sh:path ex:name ; sh:uniqueLang true ] .
    """)
    assert result == {EX + "a"}


def test_no_targets_means_no_violations(make_store):
    store = make_store("@prefix ex: <http://example.org/> . ex:a ex:p ex:b .")
    # A shape without any target can never produce a violation.
    result = violations(store, """
    @prefix sh: <http://www.w3.org/ns/shacl#> .
    @prefix ex: <http://example.org/> .
    ex:S a sh:NodeShape ; sh:property [ sh:path ex:p ; sh:minCount 5 ] .
    """)
    assert result == set()
