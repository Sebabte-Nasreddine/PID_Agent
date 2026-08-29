from pydantic import BaseModel  ,ConfigDict ,Field
from typing import Optional ,Literal ,List
from app.models.globa import Equipment,EQUIPMENT_TAG_PATTERN


class PipelineChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_equipment_tag: Optional[str] = Field(
        default=None, pattern=EQUIPMENT_TAG_PATTERN,
        description="Tag of the source equipment, null if not visible in this chunk."
    )
    to_equipment_tag: Optional[str] = Field(
        default=None, pattern=EQUIPMENT_TAG_PATTERN,
        description="Tag of the destination equipment, null if not visible in this chunk."
    )
    exit_edge: Optional[Literal["top", "bottom", "left", "right"]] = None

class InstrumentChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tag: str
    attached_to_type: Literal["equipment", "pipeline", "instrument"]
    attached_to_equipment_tag: Optional[str] = None
    attached_to_instrument_tag: Optional[str] = None
    attached_to_pipeline_from: Optional[str] = None
    attached_to_pipeline_to: Optional[str] = None
 

class ChunkMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    row: int
    col: int
    n_rows: int
    n_cols: int
    bbox_px: tuple[float, float, float, float]
    core_bbox_px: tuple[float, float, float, float]



class Chunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: ChunkMetadata
    image_path: str


class ChunkExtraction(BaseModel):
    """Schéma soumis au LLM local — jamais de metadata, jamais d'id."""
    model_config = ConfigDict(extra="forbid")

    equipment: List[Equipment]
    instruments: List[InstrumentChunk]
    pipelines: List[PipelineChunk]


class ChunkResult(BaseModel):
    """Ce qui vit dans le State — extraction + metadata réattachée en code."""
    model_config = ConfigDict(extra="forbid")

    metadata: ChunkMetadata
    equipment: List[Equipment]
    instruments: List[InstrumentChunk]
    pipelines: List[PipelineChunk]