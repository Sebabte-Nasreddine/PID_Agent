from typing import TypedDict, Annotated
import operator
from app.models.globa import Equipment, Pipeline
from app.models.chunk import Chunk, ChunkResult

class PIDState(TypedDict):
    pdf_path: str
    document_id: str

    coarse_equipment: list[Equipment]
    coarse_pipelines: list[Pipeline]

    chunks: list[Chunk]
    chunk_results: Annotated[list[ChunkResult], operator.add]  # accumulation entre boucles

    chunks_to_reextract: list[str]
    validation_attempt: int

    validated_data: dict
    needs_review: list[str]
    errors: Annotated[list[str], operator.add]