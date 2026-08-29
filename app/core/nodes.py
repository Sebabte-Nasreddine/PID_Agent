import io
import base64
import uuid
from json import JSONDecodeError

from pydantic import ValidationError

from app.models.globa import Equipment, EquipmentLLM, Pipeline, Instrument, CoarseExtraction
from app.models.chunk import Chunk, ChunkExtraction, ChunkResult
from app.models.correction import ValidationOutput, EquipmentCorrection
from app.core.chunking import chunk_pdf, render_pdf_to_image
from app.core.llm_client import (
    call_local_llm_structured, call_cloud_llm_structured,
    call_cloud_llm_structured_vision, encode_image,
)
from app.core.prompts import (
    build_chunk_extraction_prompt, build_coarse_extraction_prompt, build_validation_prompt,
)
from app.core.fusion import dedup_equipment, dedup_instruments, prefuse_pipelines

MAX_ATTEMPTS = 3
MAX_VALIDATION_ATTEMPTS = 2


def cloud_coarse_extraction(state: dict) -> dict:
    image = render_pdf_to_image(state["pdf_path"], dpi=150)
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    image_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

    result: CoarseExtraction = call_cloud_llm_structured_vision(
        build_coarse_extraction_prompt(), image_b64, CoarseExtraction
    )
    # Les ids générés par le LLM sont ignorés au profit d'ids stables générés
    # en code : plus fiable, pas de risque de collision ou de format instable.
    pipelines = [
        p.model_copy(update={"id": str(uuid.uuid4())}) for p in result.pipelines
    ]
    # result.equipment est du EquipmentLLM (tag + equipment_name uniquement) :
    # on complète avec les champs dérivés du tag pour obtenir des Equipment.
    equipment = [Equipment(**eq.model_dump()) for eq in result.equipment]
    return {"coarse_equipment": equipment, "coarse_pipelines": pipelines}


def deterministic_chunking(state: dict) -> dict:
    chunks, errors = chunk_pdf(state["pdf_path"], state["document_id"])
    return {"chunks": chunks, "errors": errors}


def _extract_chunk(chunk: Chunk, attempt: int = 0) -> tuple[ChunkResult | None, str | None]:
    image_b64 = encode_image(chunk.image_path)
    prompt = build_chunk_extraction_prompt(chunk.metadata)

    try:
        result: ChunkExtraction = call_local_llm_structured(prompt, image_b64, ChunkExtraction)
    except (ValidationError, JSONDecodeError) as e:
        if attempt + 1 >= MAX_ATTEMPTS:
            return None, f"{type(e).__name__}: {e}"
        return _extract_chunk(chunk, attempt + 1)

    return ChunkResult(
        metadata=chunk.metadata,
        equipment=result.equipment,
        instruments=result.instruments,
        pipelines=result.pipelines,
    ), None


def local_batch_extraction(state: dict) -> dict:
    target_ids = state.get("chunks_to_reextract")
    chunks_to_process = (
        [c for c in state["chunks"] if c.metadata.chunk_id in target_ids]
        if target_ids else state["chunks"]
    )

    new_results: list[ChunkResult] = []
    errors: list[str] = []
    needs_review: list[str] = []

    for chunk in chunks_to_process:
        result, error_detail = _extract_chunk(chunk)
        if result is None:
            errors.append(f"Chunk {chunk.metadata.chunk_id} failed after {MAX_ATTEMPTS} attempts: {error_detail}")
            needs_review.append(chunk.metadata.chunk_id)
        else:
            new_results.append(result)

    if target_ids:
        # remplace uniquement les chunk_results des chunks reextraits
        kept = [cr for cr in state["chunk_results"] if cr.metadata.chunk_id not in target_ids]
        chunk_results = kept + new_results
    else:
        chunk_results = new_results

    return {
        "chunk_results": chunk_results,
        "errors": errors,
        "needs_review": needs_review,
        "chunks_to_reextract": [],  # consommé
    }


def cloud_validation(state: dict) -> dict:
    deduped_equipment = dedup_equipment(state["chunk_results"])
    deduped_instruments = dedup_instruments(state["chunk_results"])
    resolved_pipelines, unresolved_fragments = prefuse_pipelines(state["chunk_results"])

    prompt = build_validation_prompt(
        state["coarse_equipment"],
        state["coarse_pipelines"],
        deduped_equipment,
        deduped_instruments,
        resolved_pipelines,
        unresolved_fragments,
    )
    result: ValidationOutput = call_cloud_llm_structured(prompt, ValidationOutput)

    attempt = state.get("validation_attempt", 0)
    if result.chunks_to_reextract and attempt < MAX_VALIDATION_ATTEMPTS:
        return {
            "chunks_to_reextract": result.chunks_to_reextract,
            "validation_attempt": attempt + 1,
        }

    # result.resolved_equipment est du EquipmentCorrectionLLM (kept_tag +
    # equipment_name uniquement) : on complète avec les champs dérivés du tag.
    resolved_equipment = [
        EquipmentCorrection(**eq.model_dump()) for eq in result.resolved_equipment
    ]

    return {
        "validated_data": {
            "equipment": resolved_equipment,
            "instruments": result.resolved_instrument,
            "pipelines": result.resolved_pipelines,
        },
        "needs_review": result.chunks_to_reextract,
    }


def insert_postgres(state: dict) -> dict:
    import psycopg
    from app.config import settings

    data = state["validated_data"]
    with psycopg.connect(settings.postgres_dsn) as conn:
        with conn.cursor() as cur:
            for eq in data["equipment"]:
                cur.execute(
                    """
                    INSERT INTO equipment (tag, name, area, type, sequence)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (tag) DO UPDATE SET
                        name = EXCLUDED.name,
                        area = EXCLUDED.area,
                        type = EXCLUDED.type,
                        sequence = EXCLUDED.sequence
                    """,
                    (eq.kept_tag, eq.equipment_name, eq.area, eq.equipment_type, eq.sequence),
                )
            for p in data["pipelines"]:
                cur.execute(
                    """
                    INSERT INTO pipeline (from_tag, to_tag)
                    VALUES (%s, %s)
                    ON CONFLICT (from_tag, to_tag) DO NOTHING
                    """,
                    (p.from_equipment_tag, p.to_equipment_tag),
                )
            for i in data["instruments"]:
                cur.execute(
                    """
                    INSERT INTO instrument (tag, attached_to_tag, attached_to_type)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (tag) DO UPDATE SET
                        attached_to_tag = EXCLUDED.attached_to_tag,
                        attached_to_type = EXCLUDED.attached_to_type
                    """,
                    (i.kept_tag, i.attached_to_tag, i.attached_to_type),
                )
        conn.commit()
    return {}


def insert_neo4j(state: dict) -> dict:
    from neo4j import GraphDatabase
    from app.config import settings

    data = state["validated_data"]
    driver = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )
    try:
        with driver.session() as session:
            for eq in data["equipment"]:
                session.run(
                    "MERGE (e:Equipment {tag: $tag}) SET e.name = $name, "
                    "e.area = $area, e.type = $type, e.sequence = $sequence",
                    tag=eq.kept_tag, name=eq.equipment_name,
                    area=eq.area, type=eq.equipment_type, sequence=eq.sequence,
                )
            for p in data["pipelines"]:
                session.run(
                    "MATCH (a:Equipment {tag: $from_tag}), (b:Equipment {tag: $to_tag}) "
                    "MERGE (a)-[:CONNECTS_TO]->(b)",
                    from_tag=p.from_equipment_tag, to_tag=p.to_equipment_tag,
                )
            for i in data["instruments"]:
                session.run(
                    "MATCH (n {tag: $parent}) "
                    "MERGE (inst:Instrument {tag: $tag}) "
                    "MERGE (inst)-[:ATTACHED_TO]->(n)",
                    parent=i.attached_to_tag, tag=i.kept_tag,
                )
    finally:
        driver.close()
    return {}