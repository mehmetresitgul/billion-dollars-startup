from typing import Optional
from fastapi import APIRouter, Query, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pacifor.api.deps import db_session
from pacifor.api.schemas.audit import AuditEntryResponse
from pacifor.models.audit_entry import AuditEntry

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=list[AuditEntryResponse])
async def list_audit(
    run_id: Optional[str] = Query(None),
    node_name: Optional[str] = Query(None),
    limit: int = Query(50, le=500),
    db: AsyncSession = Depends(db_session),
):
    stmt = select(AuditEntry).order_by(AuditEntry.id.desc()).limit(limit)
    if run_id:
        stmt = stmt.where(AuditEntry.run_id == run_id)
    if node_name:
        stmt = stmt.where(AuditEntry.node_name == node_name)
    result = await db.execute(stmt)
    return result.scalars().all()
