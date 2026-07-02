"""
ontology_loader.py
==================
Generic utility for resolving and ordering TTL ontology module files
for backends that do not natively follow ``owl:imports``.

Public API
----------
scan_folder(folder)
    Scan every .ttl file in *folder* and return an ``{IRI: Path}`` map
    derived from each file's ``owl:Ontology`` declaration.

resolve_import_chain(entry_file, iri_to_file)
    Depth-first traversal of ``owl:imports`` starting at *entry_file*.
    Returns an ordered ``List[Path]`` - imports first, entry last.
    Diamond dependencies are handled correctly (each file loaded once).

load_chain_for(entry_file, folder)
    Convenience wrapper: ``scan_folder`` + ``resolve_import_chain``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Set

log = logging.getLogger(__name__)

_OWL_ONTOLOGY   = "http://www.w3.org/2002/07/owl#Ontology"
_OWL_IMPORTS    = "http://www.w3.org/2002/07/owl#imports"
_RDF_TYPE       = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"


def _parse_ttl(file_path: str) -> "rdflib.Graph":
    """Parse a Turtle file, falling back to stripping RDF-star if needed."""
    import re
    import warnings
    from io import StringIO
    import rdflib

    g = rdflib.Graph()
    _rdflib_logger = logging.getLogger("rdflib.term")
    _prev_level = _rdflib_logger.level
    try:
        _rdflib_logger.setLevel(logging.ERROR)
        g.parse(file_path, format="turtle")
        return g
    except Exception as orig_exc:
        pass
    finally:
        _rdflib_logger.setLevel(_prev_level)

    # Check for RDF-star syntax and retry without it
    with open(file_path, "r", encoding="utf-8") as f:
        raw = f.read()
    if "<<" not in raw:
        raise orig_exc

    # Strip RDF-star quoted-triple statements
    out_lines = []
    inside_star = False
    for line in raw.splitlines(keepends=True):
        if inside_star:
            if re.search(r"\.\s*$", line):
                inside_star = False
            continue
        if re.match(r"\s*<<", line):
            if not re.search(r"\.\s*$", line):
                inside_star = True
            continue
        out_lines.append(line)

    cleaned = "".join(out_lines)
    g.parse(StringIO(cleaned), format="turtle")
    log.info("_parse_ttl: %s parsed with RDF-star annotations stripped",
             Path(file_path).name)
    return g


def scan_folder(folder: Path) -> Dict[str, Path]:
    """
    Scan all ``.ttl`` files in *folder* (non-recursive) and return a
    mapping ``{ontology_IRI: absolute_path}``.

    The IRI is taken from the first ``?s rdf:type owl:Ontology`` triple
    found in each file.  Files with no ``owl:Ontology`` declaration are
    silently skipped.
    """
    import rdflib

    iri_to_file: Dict[str, Path] = {}
    for ttl in sorted(folder.glob("*.ttl")):
        try:
            g = _parse_ttl(str(ttl))
        except Exception as exc:
            log.warning("scan_folder: could not parse %s - %s", ttl.name, exc)
            continue

        owl_onto = rdflib.URIRef(_OWL_ONTOLOGY)
        rdf_type = rdflib.URIRef(_RDF_TYPE)
        for subj, _, _ in g.triples((None, rdf_type, owl_onto)):
            iri_str = str(subj)
            if iri_str in iri_to_file:
                log.warning(
                    "Duplicate ontology IRI <%s>: already mapped to %s, "
                    "ignoring %s",
                    iri_str, iri_to_file[iri_str].name, ttl.name,
                )
            else:
                iri_to_file[iri_str] = ttl.resolve()
                log.debug("scan_folder: <%s> → %s", iri_str, ttl.name)

    return iri_to_file


def resolve_import_chain(
    entry_file: Path,
    iri_to_file: Dict[str, Path],
    _visited: Optional[Set[str]] = None,
) -> List[Path]:
    """
    Depth-first traversal of ``owl:imports`` declarations.

    Starting from *entry_file*, follow every ``owl:imports`` arc into the
    IRI→file map recursively and return the fully-ordered ``List[Path]``
    with imports before the file that imports them (post-order DFS).

    Parameters
    ----------
    entry_file:
        Absolute path to the top-level TTL file to resolve.
    iri_to_file:
        Mapping built by :func:`scan_folder` (or supplied manually).
    _visited:
        Internal cycle-guard; callers should not set this.

    Returns
    -------
    Ordered list of absolute ``Path`` objects, dependencies first.
    """
    import rdflib

    entry_str = str(entry_file.resolve())
    if _visited is None:
        _visited = set()
    if entry_str in _visited:
        return []
    _visited.add(entry_str)

    try:
        g = _parse_ttl(entry_str)
    except Exception as exc:
        log.warning("resolve_import_chain: cannot parse %s - %s", entry_file.name, exc)
        return [entry_file.resolve()]

    owl_imports = rdflib.URIRef(_OWL_IMPORTS)
    chain: List[Path] = []

    for _, _, imported_iri in g.triples((None, owl_imports, None)):
        iri_str = str(imported_iri)
        mapped = iri_to_file.get(iri_str)
        if mapped is None:
            log.warning(
                "resolve_import_chain: no file for <%s> imported by %s",
                iri_str, entry_file.name,
            )
            continue
        chain.extend(
            resolve_import_chain(mapped, iri_to_file, _visited)
        )

    chain.append(entry_file.resolve())
    return chain


def scan_folders(folders: List[Path]) -> Dict[str, Path]:
    """
    Scan multiple directories and merge their IRI→file maps.

    Duplicate IRIs are kept from the first folder that declares them
    (earlier entries take priority).  A warning is logged for conflicts.
    """
    merged: Dict[str, Path] = {}
    for folder in folders:
        if not folder.is_dir():
            log.warning("scan_folders: %s is not a directory - skipped", folder)
            continue
        for iri, path in scan_folder(folder).items():
            if iri not in merged:
                merged[iri] = path
            else:
                log.warning(
                    "scan_folders: duplicate IRI <%s> in %s - keeping %s",
                    iri, folder.name, merged[iri].name,
                )
    return merged


def load_chain_for(entry_file: Path, folder_or_folders) -> List[Path]:
    """
    Convenience wrapper: scan *folder_or_folders* to build the IRI→file
    map, then return the DFS-ordered list of TTL files needed to fully
    load *entry_file* and all its transitive ``owl:imports``.

    Parameters
    ----------
    entry_file:
        Path to the module whose full import chain is desired.
    folder_or_folders:
        A single ``Path`` directory, or a ``List[Path]`` of directories
        to scan (merged with :func:`scan_folders`).

    Returns
    -------
    Ordered ``List[Path]`` - base modules first, *entry_file* last.
    """
    if isinstance(folder_or_folders, list):
        iri_to_file = scan_folders(folder_or_folders)
    else:
        iri_to_file = scan_folder(folder_or_folders)
    return resolve_import_chain(entry_file.resolve(), iri_to_file)
