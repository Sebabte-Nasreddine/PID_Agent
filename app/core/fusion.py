"""
Logique déterministe exécutée en code, avant d'interroger le LLM cloud de
validation. Objectif : réduire au maximum ce que le LLM doit "deviner".

- dedup_equipment / dedup_instruments : les tags sont uniques dans tout le
  document (garanti par l'utilisateur), donc deux entrées avec le même tag
  dans deux chunks voisins sont forcément le même objet physique. Pas besoin
  de raisonnement LLM, un simple regroupement par tag suffit.

- prefuse_pipelines : un fragment de pipeline qui sort d'un chunk par un
  bord (exit_edge) doit se retrouver dans le chunk voisin partageant ce
  bord, avec l'exit_edge opposé. Si un seul candidat correspond côté
  voisin, la fusion est non-ambiguë -> résolue ici, sans LLM. Si plusieurs
  fragments ouverts se chevauchent sur le même bord partagé, c'est ambigu
  -> on laisse le LLM cloud arbitrer avec sa vue globale (coarse_pipelines).
"""

import uuid
from app.models.globa import Equipment, Pipeline
from app.models.chunk import ChunkResult, PipelineChunk, InstrumentChunk

NEIGHBOR_EDGE = {"top": "bottom", "bottom": "top", "left": "right", "right": "left"}
_DELTA = {"top": (-1, 0), "bottom": (1, 0), "left": (0, -1), "right": (0, 1)}


def dedup_equipment(chunk_results: list[ChunkResult]) -> list[Equipment]:
    seen: dict[str, Equipment] = {}
    for cr in chunk_results:
        for eq in cr.equipment:
            seen.setdefault(eq.tag, eq)
    return list(seen.values())


def dedup_instruments(chunk_results: list[ChunkResult]) -> list[InstrumentChunk]:
    seen: dict[str, InstrumentChunk] = {}
    for cr in chunk_results:
        for inst in cr.instruments:
            seen.setdefault(inst.tag, inst)
    return list(seen.values())


def _neighbor_chunk_id(row: int, col: int, edge: str, n_rows: int, n_cols: int) -> str | None:
    dr, dc = _DELTA[edge]
    nr, nc = row + dr, col + dc
    if 0 <= nr < n_rows and 0 <= nc < n_cols:
        return f"r{nr}_c{nc}"
    return None


def prefuse_pipelines(
    chunk_results: list[ChunkResult],
) -> tuple[list[Pipeline], list[tuple[str, PipelineChunk]]]:
    """Retourne (pipelines résolues sans ambiguïté, fragments encore ouverts).

    Les fragments ouverts sont retournés avec leur chunk_id d'origine, pour
    que le prompt de validation reste traçable.
    """
    resolved: list[Pipeline] = []
    open_ends: list[tuple[str, ChunkResult, PipelineChunk]] = []

    for cr in chunk_results:
        for p in cr.pipelines:
            if p.exit_edge is None:
                # Segment complet dans un seul chunk : rien à recoller.
                if p.from_equipment_tag and p.to_equipment_tag:
                    resolved.append(
                        Pipeline(
                            id=str(uuid.uuid4()),
                            from_equipment_tag=p.from_equipment_tag,
                            to_equipment_tag=p.to_equipment_tag,
                        )
                    )
                # from=to=None sans exit_edge : fragment inexploitable, ignoré
                # (remontera comme incohérence si jamais utile plus tard).
                continue
            open_ends.append((cr.metadata.chunk_id, cr, p))

    consumed: set[int] = set()
    unresolved: list[tuple[str, PipelineChunk]] = []

    for chunk_id, cr, p in open_ends:
        if id(p) in consumed:
            continue

        nb_id = _neighbor_chunk_id(
            cr.metadata.row, cr.metadata.col, p.exit_edge, cr.metadata.n_rows, cr.metadata.n_cols
        )
        nb_edge = NEIGHBOR_EDGE[p.exit_edge]

        candidates = [
            (c_id, q)
            for c_id, c_cr, q in open_ends
            if c_id == nb_id and q.exit_edge == nb_edge and id(q) not in consumed
        ]

        if len(candidates) == 1:
            _, q = candidates[0]
            from_tag = p.from_equipment_tag or q.from_equipment_tag
            to_tag = p.to_equipment_tag or q.to_equipment_tag
            if from_tag and to_tag:
                resolved.append(
                    Pipeline(id=str(uuid.uuid4()), from_equipment_tag=from_tag, to_equipment_tag=to_tag)
                )
                consumed.add(id(p))
                consumed.add(id(q))
                continue

        # Pas de candidat unique (0 ou plusieurs) -> ambigu, remonté au LLM cloud.
        unresolved.append((chunk_id, p))

    return resolved, unresolved