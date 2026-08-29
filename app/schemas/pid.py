from pydantic import BaseModel, ConfigDict


class EquipmentOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tag: str
    equipment_name: str
    area: str
    equipment_type: str
    sequence: str


class PipelineOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    from_equipment_tag: str
    to_equipment_tag: str


class InstrumentOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tag: str
    attached_to_tag: str
    attached_to_type: str


class ExtractionResponse(BaseModel):
    """Réponse renvoyée par POST /extract une fois le pipeline terminé."""
    model_config = ConfigDict(extra="forbid")

    document_id: str
    equipment: list[EquipmentOut]
    instruments: list[InstrumentOut]
    pipelines: list[PipelineOut]
    needs_review: list[str] = []
    errors: list[str] = []


class ExtractionStatus(BaseModel):
    """Réponse d'un job asynchrone (voir POST /extract/async)."""
    model_config = ConfigDict(extra="forbid")

    job_id: str
    status: str  # "pending" | "running" | "done" | "failed"
    result: ExtractionResponse | None = None
    error: str | None = None