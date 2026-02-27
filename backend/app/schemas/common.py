from pydantic import BaseModel, ConfigDict
from typing import Optional, Any


class ErrorResponse(BaseModel):
    """Canonical error response schema."""
    model_config = ConfigDict(extra="forbid")
    
    error: str
    detail: Optional[str] = None
    code: Optional[str] = None
    request_id: Optional[str] = None


class SuccessResponse(BaseModel):
    """Generic success response."""
    model_config = ConfigDict(extra="forbid")
    
    success: bool = True
    message: Optional[str] = None
    data: Optional[Any] = None
