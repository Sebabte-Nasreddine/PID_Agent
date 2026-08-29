import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from app.core.graph import build_graph
from app.core.chunking import make_document_id
from app.schemas.pid import (
    ExtractionResponse, ExtractionStatus,
    EquipmentOut, InstrumentOut, PipelineOut,
)

router = APIRouter(prefix="/extract", tags=["extraction"])

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# Stockage en mémoire des jobs asynchrones. Suffisant pour un MVP mono-
# processus ; à remplacer par Redis/une table Postgres dès qu'on veut
# plusieurs workers ou que le process peut redémarrer en cours de job.
_JOBS: dict[str, ExtractionStatus] = {}


def _save_upload(file: UploadFile) -> str:
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Seuls les fichiers .pdf sont acceptés.")
    dest = UPLOAD_DIR / f"{uuid.uuid4().hex}_{file.filename}"
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    return str(dest)


def _run_pipeline(pdf_path: str) -> ExtractionResponse:
    graph = build_graph()
    document_id = make_document_id(pdf_path)

    final_state = graph.invoke({
        "pdf_path": pdf_path,
        "document_id": document_id,
        "validation_attempt": 0,
        "chunks_to_reextract": [],
        "errors": [],
    })

    data = final_state.get("validated_data", {})
    return ExtractionResponse(
        document_id=document_id,
        equipment=[
            EquipmentOut(
                tag=e.kept_tag, equipment_name=e.equipment_name,
                area=e.area, equipment_type=e.equipment_type, sequence=e.sequence,
            )
            for e in data.get("equipment", [])
        ],
        instruments=[
            InstrumentOut(tag=i.kept_tag, attached_to_tag=i.attached_to_tag, attached_to_type=i.attached_to_type)
            for i in data.get("instruments", [])
        ],
        pipelines=[
            PipelineOut(from_equipment_tag=p.from_equipment_tag, to_equipment_tag=p.to_equipment_tag)
            for p in data.get("pipelines", [])
        ],
        needs_review=final_state.get("needs_review", []),
        errors=final_state.get("errors", []),
    )


@router.post("", response_model=ExtractionResponse)
def extract_sync(file: UploadFile) -> ExtractionResponse:
    """Lance le pipeline complet et attend le résultat avant de répondre.
    Simple pour un MVP, mais bloque la requête HTTP le temps de tous les
    appels LLM + l'insertion Postgres (peut prendre plusieurs minutes sur
    un P&ID réel). Pour un usage en production, préférer /extract/async."""
    pdf_path = _save_upload(file)
    try:
        return _run_pipeline(pdf_path)
    except Exception as exc:  # noqa: BLE001 — on remonte l'erreur telle quelle au client
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _run_job(job_id: str, pdf_path: str) -> None:
    _JOBS[job_id].status = "running"
    try:
        result = _run_pipeline(pdf_path)
        _JOBS[job_id].status = "done"
        _JOBS[job_id].result = result
    except Exception as exc:  # noqa: BLE001
        _JOBS[job_id].status = "failed"
        _JOBS[job_id].error = str(exc)


@router.post("/async", response_model=ExtractionStatus)
def extract_async(file: UploadFile, background_tasks: BackgroundTasks) -> ExtractionStatus:
    """Démarre le pipeline en tâche de fond et retourne immédiatement un
    job_id. Interroger GET /extract/status/{job_id} pour suivre l'avancement."""
    pdf_path = _save_upload(file)
    job_id = uuid.uuid4().hex
    _JOBS[job_id] = ExtractionStatus(job_id=job_id, status="pending")
    background_tasks.add_task(_run_job, job_id, pdf_path)
    return _JOBS[job_id]


@router.get("/status/{job_id}", response_model=ExtractionStatus)
def extract_status(job_id: str) -> ExtractionStatus:
    job = _JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job_id inconnu.")
    return job