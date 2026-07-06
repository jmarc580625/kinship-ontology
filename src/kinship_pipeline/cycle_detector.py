"""
Generational cycle detection via directed graph algorithm.

Replaces the depth-limited SPARQL CIR2 query with an arbitrary-length cycle
detector.  The properties to extract and their edge directions are derived
from the ontology (``kin:generationalDirection`` annotations), so no
predicate list is hardcoded.

Algorithm:
    1. Query the data graph for all triples whose predicate has a
       ``generationalDirection`` annotation in the target assertion set.
    2. Build a ``networkx.DiGraph`` where every edge points in the
       *ascending* direction (child -> parent).  Descending predicates
       (hasChild-family) have their edge direction flipped.
    3. Run ``nx.simple_cycles()`` to enumerate all simple cycles.

This approach has no depth limit and produces the actual node sequence of
each cycle, giving the user directly actionable root-cause information.
"""

from typing import Any, Dict, List

import networkx as nx

from .backends.base import KinshipBackend
from .query_generator import QueryGenerator


_KIN = "http://example.org/kinship#"


def _canonicalise_cycle(cycle: List[str]) -> List[str]:
    """Rotate a cycle so the lexicographically smallest node is first."""
    if not cycle:
        return cycle
    min_idx = cycle.index(min(cycle))
    return cycle[min_idx:] + cycle[:min_idx]


def detect_generational_cycles(
    backend: KinshipBackend,
    query_generator: QueryGenerator,
    data_graph: str,
    assertion_set: str,
) -> Dict[str, Any]:
    """
    Detect generational cycles in *data_graph*.

    Parameters
    ----------
    backend:
        Pipeline backend with ``execute_query()``.
    query_generator:
        Provides the ascending/descending property lists from the TBox cache.
    data_graph:
        Named graph to scan (``urn:kinship:mats`` or ``urn:kinship:oats``).
    assertion_set:
        ``"MATS"`` or ``"OATS"`` -- selects the property lists from the cache.

    Returns
    -------
    Gate-compatible report dict::

        {
            "query":  "Q-CIR2",
            "count":  <number of distinct cycles>,
            "cycles": [ [node, node, ...], ... ],   # canonical form
        }
    """
    set_key = assertion_set.lower()
    ascending  = query_generator._cache.get(f"{set_key}_asc", [])
    descending = query_generator._cache.get(f"{set_key}_desc", [])

    all_props = ascending + descending
    if not all_props:
        return {"query": "Q-CIR2", "count": 0, "cycles": []}

    descending_set = frozenset(descending)

    # Build a single extraction query for all directional properties.
    qnames = " ".join(
        f"kin:{uri[len(_KIN):]}" if uri.startswith(_KIN) else f"<{uri}>"
        for uri in all_props
    )
    sparql = (
        f"PREFIX kin: <{_KIN}>\n"
        f"SELECT ?s ?p ?o WHERE {{\n"
        f"  GRAPH <{data_graph}> {{\n"
        f"    VALUES ?p {{ {qnames} }}\n"
        f"    ?s ?p ?o .\n"
        f"  }}\n"
        f"}}"
    )
    rows = backend.execute_query(sparql)

    # Build digraph: every edge goes child -> parent (ascending direction).
    G = nx.DiGraph()
    for row in rows:
        s, p, o = row["s"], row["p"], row["o"]
        if p in descending_set:
            # Descending (hasChild-like): subject is parent, object is child.
            G.add_edge(o, s)
        else:
            # Ascending (hasParent-like): subject is child, object is parent.
            G.add_edge(s, o)

    cycles = [_canonicalise_cycle(c) for c in nx.simple_cycles(G)]
    # Sort for deterministic output.
    cycles.sort()

    return {
        "query":  "Q-CIR2",
        "count":  len(cycles),
        "cycles": cycles,
    }
