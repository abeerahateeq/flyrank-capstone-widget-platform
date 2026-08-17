import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.submission import Submission


def create(
    db: Session,
    *,
    widget_id: uuid.UUID,
    tenant_id: uuid.UUID,
    data: dict,
    ip_address: str | None,
    geo_country: str | None,
    geo_city: str | None,
    geo_provider: str | None,
    spam_flag: bool,
    status: str,
) -> Submission:
    submission = Submission(
        widget_id=widget_id,
        tenant_id=tenant_id,
        data=data,
        ip_address=ip_address,
        geo_country=geo_country,
        geo_city=geo_city,
        geo_provider=geo_provider,
        spam_flag=spam_flag,
        status=status,
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)
    return submission


def list_for_widget(
    db: Session, tenant_id: uuid.UUID, widget_id: uuid.UUID, limit: int = 50, offset: int = 0
) -> list[Submission]:
    return (
        db.query(Submission)
        .filter(Submission.tenant_id == tenant_id, Submission.widget_id == widget_id)
        .order_by(Submission.created_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )


def stats_over_time(
    db: Session, tenant_id: uuid.UUID, widget_id: uuid.UUID, days: int = 7
) -> list[dict]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        db.query(func.date(Submission.created_at).label("day"), func.count(Submission.id))
        .filter(
            Submission.tenant_id == tenant_id,
            Submission.widget_id == widget_id,
            Submission.created_at >= since,
            Submission.status == "stored",
        )
        .group_by("day")
        .order_by("day")
        .all()
    )
    return [{"day": str(day), "count": count} for day, count in rows]


def geo_breakdown(db: Session, tenant_id: uuid.UUID) -> list[dict]:
    rows = (
        db.query(Submission.geo_country, func.count(Submission.id))
        .filter(Submission.tenant_id == tenant_id, Submission.status == "stored")
        .group_by(Submission.geo_country)
        .order_by(func.count(Submission.id).desc())
        .all()
    )
    return [{"country": country or "unknown", "count": count} for country, count in rows]
