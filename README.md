# QuackL

Bare-bones SHACL validation by **compilation into SQL**. 
`quackl` validates an RDF graph against a SHACL shapes graph by storing
the graph using a simple relational schema in [DuckDB](https://duckdb.org/). 
It translates each shape into a SQL query, following the approach of [Compiling SHACL into SQL](https://vdbuss.github.io/ISWC-2024-shacl-sql.pdf)

It builds on [`slsparser`](https://github.com/MaximeJakubowski/sls_project), which parses
SHACL into a logical syntax tree; `quackl` translates that tree into SQL.

## Pronounciation
A duck _quacks_, add an "l" to "quack" and it sounds a bit like SHACL: "quackl".

## Installation

Requires Python 3.9 or up. Dependencies: `rdflib`, `duckdb`, `slsparser`.

## Library usage

Loading data into DuckDB is the current bottleneck. So, it is kept separate
from validation. Load once (optionally into a `.duckdb` file) and validate many times:

```python
from rdflib import Graph
from quackl import Store, load_graph, Validator

# Load once (in-memory here; pass a path to Store.create to persist)
store = Store.create()
load_graph(store, Graph().parse("data.ttl"))

# Validate any number of shapes graphs against the loaded store
violations = Validator(store).validate(Graph().parse("shapes.ttl"))
for term in violations:
    print(term) # violating focus nodes, as rdflib terms
```

`quackl` currently does not support validation reports, it simply prints all targeted 
nodes from the data graph that violate at least one shape in the shapes graph.

To load once and validate later (e.g. in a different process), back the store
with a file:

```python
# load data into duckdb (file)
store = Store.create("graph.duckdb")
load_graph(store, Graph().parse("data.ttl"))
store.close()

# validate data stored in duckdb (file)
store = Store.open("graph.duckdb")
violations = Validator(store).validate_file("shapes.ttl")
```

A one-shot convenience that loads into a fresh in-memory store and validates:

```python
from quackl import validate
violations = validate(Graph().parse("data.ttl"), Graph().parse("shapes.ttl"))
```

## Command line

```bash
# Load RDF into a persistent DuckDB store.
quackl load data.ttl --db graph.duckdb

# Validate shapes against an already-loaded store.
quackl validate shapes.ttl --db graph.duckdb

# Load (in-memory) and validate in one step.
quackl run data.ttl shapes.ttl
# shorthand:
quackl data.ttl shapes.ttl
```

Violating focus nodes are printed (one per line); the exit status is `0` when
the data conforms and `1` when there are violations.

## Relational representation

An RDF graph is stored with the "pooling" technique: every term gets a unique
integer `Node` id, used in the central `Triples` relation.

| Table | Columns |
| --- | --- |
| `Nodes` | `Node` |
| `IRIs` | `Node`, `Value` |
| `Blanks` | `Node`, `Alias` |
| `Literals` | `Node`, `Value`, `Type`, `Lang` |
| `Numerics` | `Node`, `Value` (double; numeric literals only) |
| `Triples` | `Subject`, `Predicate`, `Object` (predicate kept as an IRI string) |

## Scope and purpose

The intention of `quackl` is to show that SHACL validation using relational technologies
is not only theoretically feasible, but also performant. While `quackl` itself might 
not immediately become a W3C-compliant SHACL validator, the ideas behind it are being 
developed furter (eventually working towards a RDF-SPARQL-SHACL compliant relational-based
technology stack).

At the moment, `quackl` covers the SHACL core constraint components (cardinality, logical
operators, value/node-kind/datatype/range/length/pattern/languageIn tests, `equals`, 
`disjoint`, `closed`, `lessThan(OrEquals)`, `uniqueLang`, `hasValue`) over simple paths 
(a property or an inverse property).

Out of scope (for now):

- **Validation report.** Validation returns a flat list of violating focus nodes, not a full SHACL validation report. The per-shape SQL in `quackl.translator` and `Store.terms_for_ids` are kept as seams so a report (constraint component, path, value, severity, message) can be added later.
- **General property paths** only IRIs and the `sh:inversePath`, others (sequence, alternative, zero-or-more, etc.) are not supported.
- **Comparisons between datatypes** is only supported for numeric values (integers, etc.) not for others (like datatime). This applies to `sh:minInclusive`, `sh:lessThan`, etc.

## Relation to the prototype

`quackl` is based on the `shuq` prototype [found in our paper repository](https://github.com/MaximeJakubowski/shaclsql-supplementary/tree/main/sqltools/shuq). The SQL builders were ported from it
with bug fixes.

## Why does this exist?
I like it.
