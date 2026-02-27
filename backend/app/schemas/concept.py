from typing import List
from pydantic import BaseModel, Field, ConfigDict


class ConceptScope(BaseModel):
    """Defines the multi-concept scope for an objective or turn."""
    model_config = ConfigDict(extra="forbid")
    
    primary: List[str] = Field(..., min_length=1, description="1-3 concepts that are the explicit learning targets")
    support: List[str] = Field(default_factory=list, description="Related concepts that help explain/solve")
    prereq: List[str] = Field(default_factory=list, description="Prerequisite concepts that may need remediation")
