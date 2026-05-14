from fastapi import APIRouter, HTTPException
from pacifor.api.schemas.hitl import HITLDecision, HITLPendingResponse
from pacifor.services.hitl_service import hitl_service

router = APIRouter(prefix="/hitl", tags=["hitl"])


@router.get("/pending", response_model=list[HITLPendingResponse])
async def list_pending():
    return await hitl_service.list_pending()


@router.post("/{review_id}/approve")
async def approve(review_id: str, body: HITLDecision):
    try:
        await hitl_service.decide(review_id=review_id, approved=True, body=body)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Review {review_id!r} not found")
    return {"status": "approved", "review_id": review_id}


@router.post("/{review_id}/reject")
async def reject(review_id: str, body: HITLDecision):
    try:
        await hitl_service.decide(review_id=review_id, approved=False, body=body)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Review {review_id!r} not found")
    return {"status": "rejected", "review_id": review_id}
