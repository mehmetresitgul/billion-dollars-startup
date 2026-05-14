from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel


class HITLDecision(BaseModel):
    approved: bool
    reason: Optional[str] = None
    decided_by: Optional[str] = None


class HITLPendingResponse(BaseModel):
    id: str
    run_id: str
    node_name: str
    payload: dict[str, Any]
    status: str
    created_at: datetime
