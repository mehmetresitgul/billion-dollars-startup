from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class RunCreate(BaseModel):
    agent_id: str = "default"
    user_id: Optional[str] = None
    initial_message: str


class RunResponse(BaseModel):
    id: str
    agent_id: str
    user_id: Optional[str]
    status: str
    created_at: datetime
    result: Optional[str] = None
    error: Optional[str] = None
