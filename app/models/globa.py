import re
from typing import List,Literal,Optional
from pydantic import BaseModel , ConfigDict ,Field ,field_validator, model_validator

EQUIPMENT_TAG_PATTERN=r"^[A-Z0-9]+-[A-Z]+-[0-9]{2}[A-Z]?$"
_TAG_PARTS_PATTERN = re.compile(r"^(?P<area>[A-Z0-9]+)-(?P<type>[A-Z]+)-(?P<sequence>[0-9]{2}[A-Z]?)$")


def derive_tag_parts(tag: str) -> tuple[str, str, str]:
    """Découpe un tag valide AREA-TYPE-SEQUENCE en ses 3 composantes.
    Retourne ("", "", "") si le tag ne matche pas le pattern attendu."""
    match = _TAG_PARTS_PATTERN.match(tag)
    if not match:
        return "", "", ""
    return match.group("area"), match.group("type"), match.group("sequence")

class EquipmentLLM(BaseModel):
    """Schéma envoyé au LLM : uniquement les champs qu'il doit remplir."""
    model_config = ConfigDict(extra="forbid")

    tag: str = Field(..., pattern=EQUIPMENT_TAG_PATTERN, description="Equipment tag.")
    equipment_name: str = Field(..., description="Human-readable name of the equipment.")


class Equipment(EquipmentLLM):
    """Entité applicative complète, avec les champs dérivés en code."""
    area: str = ""
    equipment_type: str = ""
    sequence: str = ""

    @model_validator(mode="after")
    def _derive_fields_from_tag(self):
        if not (self.area and self.equipment_type and self.sequence):
            area, equipment_type, sequence = derive_tag_parts(self.tag)
            self.area = self.area or area
            self.equipment_type = self.equipment_type or equipment_type
            self.sequence = self.sequence or sequence
        return self

class Pipeline(BaseModel):
    """Entité finale, résolue, après fusion inter-chunks."""
    model_config = ConfigDict(extra="forbid")

    id: str
    from_equipment_tag: Optional[str] = Field(
            pattern=EQUIPMENT_TAG_PATTERN,
            description="Tag of the source equipment, null if not visible in this chunk."
        )
    to_equipment_tag: Optional[str] = Field(
            pattern=EQUIPMENT_TAG_PATTERN,
            description="Tag of the destination equipment, null if not visible in this chunk."
        )






class Instrument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tag: str
    attached_to_type: Literal["equipment", "pipeline", "instrument"]
    attached_to_equipment_tag: Optional[str] = None
    attached_to_instrument_tag: Optional[str] = None
    attached_to_pipeline_id: Optional[str] = None



class CoarseExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    equipment: List[EquipmentLLM]
    pipelines: List[Pipeline]