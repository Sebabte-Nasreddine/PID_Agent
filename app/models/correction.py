from typing import List,Literal
from pydantic import BaseModel ,ConfigDict,Field, model_validator
from app.models.globa import EQUIPMENT_TAG_PATTERN, derive_tag_parts

class PipelineCorrection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_equipment_tag: str = Field(..., pattern=EQUIPMENT_TAG_PATTERN, description="Tag of the equipment at the start of the pipeline.")
    to_equipment_tag: str = Field(..., pattern=EQUIPMENT_TAG_PATTERN, description="Tag of the equipment at the end of the pipeline.")


class InstrumentCorrection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kept_tag: str
    attached_to_tag: str
    attached_to_type: Literal["equipment", "pipeline"]

class EquipmentCorrectionLLM(BaseModel):
    """Schéma envoyé au LLM : uniquement les champs qu'il doit remplir."""
    model_config = ConfigDict(extra="forbid")

    kept_tag: str = Field(..., pattern=EQUIPMENT_TAG_PATTERN, description="Equipment tag kept.")
    equipment_name: str = Field(..., description="Human-readable name of the equipment kept.")


class EquipmentCorrection(EquipmentCorrectionLLM):
    """Entité applicative complète, avec les champs dérivés en code."""
    area: str = ""
    equipment_type: str = ""
    sequence: str = ""

    @model_validator(mode="after")
    def _derive_fields_from_tag(self):
        if not (self.area and self.equipment_type and self.sequence):
            area, equipment_type, sequence = derive_tag_parts(self.kept_tag)
            self.area = self.area or area
            self.equipment_type = self.equipment_type or equipment_type
            self.sequence = self.sequence or sequence
        return self




class ValidationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resolved_pipelines: List[PipelineCorrection]
    resolved_instrument: List[InstrumentCorrection]
    resolved_equipment: List[EquipmentCorrectionLLM]
    chunks_to_reextract: List[str] = Field(..., description="Chunk ids to re-extract, empty list if none.")