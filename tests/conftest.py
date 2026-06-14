import pytest
from rdflib import Graph

from quackl import Store, load_graph


@pytest.fixture
def make_store():
    """Factory yielding in-memory Stores loaded from inline Turtle."""
    created = []

    def _make(turtle: str) -> Store:
        store = Store.create()
        load_graph(store, Graph().parse(data=turtle, format="turtle"))
        created.append(store)
        return store

    yield _make
    for store in created:
        store.close()
