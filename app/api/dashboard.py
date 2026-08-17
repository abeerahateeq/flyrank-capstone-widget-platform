import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.auth import get_current_tenant
from app.db.session import get_db
from app.models.tenant import Tenant
from app.repositories import submission_repo, widget_repo
from app.schemas.submission import SubmissionDetailOut

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/widgets/{widget_id}/submissions", response_model=list[SubmissionDetailOut])
def list_submissions(
    widget_id: uuid.UUID,
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    # Ownership check first — a widget_id belonging to another tenant must
    # 404, not silently return an empty list (which would leak "this ID
    # exists but isn't yours" vs "this ID doesn't exist").
    widget = widget_repo.get_owned(db, tenant.id, widget_id)
    if not widget:
        raise HTTPException(status_code=404, detail="widget not found")

    return submission_repo.list_for_widget(db, tenant.id, widget_id, limit=limit, offset=offset)


@router.get("/widgets/{widget_id}/stats")
def widget_stats(
    widget_id: uuid.UUID,
    days: int = Query(7, le=90),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    widget = widget_repo.get_owned(db, tenant.id, widget_id)
    if not widget:
        raise HTTPException(status_code=404, detail="widget not found")

    return {"widget_id": str(widget_id), "days": days, "series": submission_repo.stats_over_time(db, tenant.id, widget_id, days=days)}


@router.get("/stats/geo")
def geo_stats(
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    return {"breakdown": submission_repo.geo_breakdown(db, tenant.id)}
