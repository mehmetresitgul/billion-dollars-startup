from typing import Optional
from pydantic import BaseModel


class AuditEntryResponse(BaseModel):
    id: int
    run_id: str
    agent_id: str
    node_name: str
    action: str
    outcome: str
    user_id: Optional[str]
    payload_hash: Optional[str]
    timestamp: str
