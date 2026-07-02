"""
Filiation cycle detection via NetworkX directed graph.

Extracts filiation assertions from the ABox (no inference) and builds a
directed graph where every edge points from child to parent.  Inverse
properties (hasBloodChild, hasAdoptiveChild, hasChild) are normalised by
reversing the edge direction.

Usage with any backend that exposes ``execute_abox_query(sparql)``:

    from lib.cycle_detector import detect_cycles, report_all_cycles

    cycles = report_all_cycles(backend)
    if cycles:
        for c in cycles:
            print(c)
"""

from typing import List, Optional, Tuple, Dict, Any

import networkx as nx

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_KIN_NS = "http://example.org/kinship#"

# Properties whose edge direction means "subject is parent of object"
# (i.e. the inverse of the canonical child→parent direction).
_INVERSE_PROPERTIES = frozenset([
    f"{_KIN_NS}hasBloodChild",
    f"{_KIN_NS}hasAdoptiveChild",
    f"{_KIN_NS}hasChild",
])

# SPARQL query: retrieve all filiation triples from the ABox (no inference).
_FILIATION_QUERY = """\
PREFIX kin: <http://example.org/kinship#>
SELECT ?s ?p ?o WHERE {
    VALUES ?p {
        kin:hasBloodParent kin:hasBloodChild
        kin:hasAdoptiveParent kin:hasAdoptiveChild
        kin:hasParent kin:hasChild
    }
    ?s ?p ?o .
}
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_filiation_digraph(backend) -> nx.DiGraph:
    """
    Query the backend's ABox for filiation triples and return a NetworkX
    DiGraph where every edge goes child → parent.

    Parameters
    ----------
    backend:
        Any object exposing ``execute_abox_query(sparql: str)`` that returns
        ``List[Dict[str, str]]``.

    Returns
    -------
    nx.DiGraph with node labels as full URIs (strings).
    """
    rows: List[Dict[str, Any]] = backend.execute_abox_query(_FILIATION_QUERY)
    G = nx.DiGraph()
    for row in rows:
        s = row["s"]
        p = row["p"]
        o = row["o"]
        if p in _INVERSE_PROPERTIES:
            # hasChild-like: object is child, subject is parent → edge o→s
            G.add_edge(o, s)
        else:
            # hasParent-like: subject is child, object is parent → edge s→o
            G.add_edge(s, o)
    return G


def detect_cycle(backend) -> Optional[List[Tuple[str, str, str]]]:
    """
    Return the first cycle found, or None if acyclic.

    Returns
    -------
    A list of edges ``[(u, v, direction), ...]`` as returned by
    ``nx.find_cycle``, or None.
    """
    G = extract_filiation_digraph(backend)
    try:
        return nx.find_cycle(G, orientation="original")
    except nx.NetworkXNoCycle:
        return None


def report_all_cycles(backend) -> List[List[str]]:
    """
    Return all simple cycles (any length) in the filiation graph.

    Returns
    -------
    List of cycles, where each cycle is a list of node URIs forming the loop.
    """
    G = extract_filiation_digraph(backend)
    return list(nx.simple_cycles(G))


def short_name(uri: str) -> str:
    """Utility: strip the kinship namespace for display."""
    if uri.startswith(_KIN_NS):
        return ":" + uri[len(_KIN_NS):]
    return uri


def report_all_cycles_for_test(backend) -> List[Dict[str, Any]]:
    """
    Return all simple cycles in test-runner compatible format.

    Returns List[Dict] with full URIs (no canonicalization - the runner
    handles normalization and comparison). Each cycle is wrapped in a dict
    with key "cycle".

    Parameters
    ----------
    backend:
        Any object exposing ``execute_abox_query(sparql: str)`` that returns
        ``List[Dict[str, str]]``.

    Returns
    -------
    List[Dict] where each dict has key "cycle" with value List[str] of node URIs.
    """
    cycles = report_all_cycles(backend)
    return [{"cycle": cycle} for cycle in cycles]
