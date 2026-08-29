from app.models.chunk import ChunkMetadata


def build_chunk_extraction_prompt(meta: ChunkMetadata) -> str:
    return (
        f"You are extracting equipment, instruments, and pipelines from patch "
        f"{meta.chunk_id} of a P&ID diagram. Only report what is visibly present "
        f"in THIS image. Do not infer or guess content outside the visible boundaries.\n\n"
        f"Equipment tags follow the pattern AREA-TYPE-SEQUENCE (e.g. 100-PU-01A).\n\n"
        f"For each pipeline segment: if it visibly runs off one of the four edges "
        f"of this image without reaching a labeled equipment, set exit_edge to that "
        f"edge and leave the corresponding endpoint tag null.\n\n"
        f"For each instrument: report whether it is attached to an equipment, a "
        f"pipeline (give the equipment tags at both ends of that pipeline segment "
        f"as visible in this image), or another instrument."
    )


def build_coarse_extraction_prompt() -> str:
    return (
        "You are an expert at reading P&ID (Piping and Instrumentation "
        "Diagram) drawings. You are performing a GLOBAL OVERVIEW pass on a "
        "full P&ID page, seen as a whole (not a zoomed-in patch). This pass "
        "is later treated as authoritative when it conflicts with detailed "
        "per-region extractions, so precision matters more than "
        "completeness: it is far better to omit an equipment or pipeline "
        "you are not confident about than to report one that is wrong or "
        "guessed.\n\n"
        "Equipment: report only major process equipment — vessels, tanks, "
        "drums, pumps, compressors, heat exchangers, reactors, columns, "
        "and similar. Do NOT report instruments (transmitters, control "
        "valves, gauges, sensors) or any other annotation.\n\n"
        "Only report a tag if the printed text exactly matches this "
        "pattern:\n\n"
        "    [A-Z0-9]+-[A-Z]+-[0-9]{2}[A-Z]?\n\n"
        "    e.g. AREA (letters/digits) - TYPE (letters) - SEQUENCE (2 "
        "digits + optional letter)\n"
        "    valid:   999AA-RC-01\n"
        "    valid:   110LG-ST-01A\n"
        "    invalid: RC-01 (missing area)\n\n"
        "For each equipment, report its tag and its human-readable name "
        "exactly as labeled on the drawing (e.g. tag=999AA-RC-01, "
        "equipment_name=Reclaimer). Do not report area, type, or sequence "
        "separately — those are derived from the tag in code, not by you.\n\n"
        "If a tag is blurry, cut off, or you are not confident you are "
        "reading it correctly, do not guess or auto-correct it — omit that "
        "equipment entirely rather than invent a plausible-looking tag.\n\n"
        "For pipelines: report a connection only between two equipment "
        "tags you have both already reported above, and only when you can "
        "visually trace a continuous line between them with reasonable "
        "confidence (e.g. from_equipment_tag=110LG-RC-01, "
        "to_equipment_tag=110LG-ST-01). Do not infer a connection from "
        "proximity or typical process flow — report only what the drawn "
        "lines actually show. If a pipeline's source or destination is not "
        "clearly legible or traceable, omit that pipeline. The pipeline id "
        "value does not matter and will be discarded — any placeholder is "
        "fine.\n\n"
        "Output only equipment and the pipelines between them. Do not "
        "output explanations."
    )


def build_validation_prompt(
    coarse_equipment: list,
    coarse_pipelines: list,
    deduped_equipment: list,
    deduped_instruments: list,
    resolved_pipelines: list,
    unresolved_fragments: list,
) -> str:
    coarse_section = (
        "Global overview pass (authoritative in case of conflict):\n"
        + "\n".join(f"- Equipment: {e.tag}" for e in coarse_equipment)
        + "\n"
        + "\n".join(f"- Pipeline: {p.from_equipment_tag} -> {p.to_equipment_tag}" for p in coarse_pipelines)
    )

    equipment_section = "Deduplicated equipment (tags are unique across the document):\n" + "\n".join(
        f"- {e.tag}: {e.equipment_name}" for e in deduped_equipment
    )

    instrument_lines = []
    for i in deduped_instruments:
        if i.attached_to_type == "equipment":
            instrument_lines.append(f"- {i.tag} attached to equipment {i.attached_to_equipment_tag}")
        elif i.attached_to_type == "instrument":
            instrument_lines.append(f"- {i.tag} attached to instrument {i.attached_to_instrument_tag}")
        else:
            instrument_lines.append(
                f"- {i.tag} attached to pipeline segment "
                f"{i.attached_to_pipeline_from} -> {i.attached_to_pipeline_to}"
            )
    instrument_section = "Deduplicated instruments:\n" + "\n".join(instrument_lines)

    resolved_section = "Pipelines already unambiguously reconstructed in code (accept as-is unless they contradict the global overview):\n" + "\n".join(
        f"- {p.from_equipment_tag} -> {p.to_equipment_tag}" for p in resolved_pipelines
    )

    unresolved_section = "Pipeline fragments still ambiguous (multiple candidates crossed the same shared edge between chunks — use the global overview to decide, or list the chunk_ids in chunks_to_reextract if truly unresolvable):\n" + "\n".join(
        f"- chunk {chunk_id}: from={p.from_equipment_tag}, to={p.to_equipment_tag}, exit_edge={p.exit_edge}"
        for chunk_id, p in unresolved_fragments
    )

    return (
        "You are reconciling a global overview extraction with detailed, "
        "already-deduplicated per-patch extractions of a P&ID diagram, to "
        "produce the final validated equipment, instrument, and pipeline "
        "lists.\n\n"
        f"{coarse_section}\n\n{equipment_section}\n\n{instrument_section}\n\n"
        f"{resolved_section}\n\n{unresolved_section}\n\n"
        "Only the unresolved fragments need your judgement for pipelines. "
        "Use the global overview as authoritative when fragments conflict. "
        "If a pipeline's endpoints remain unresolvable even after "
        "cross-referencing the overview, list the contributing chunk_ids in "
        "chunks_to_reextract with a note on what to verify."
    )