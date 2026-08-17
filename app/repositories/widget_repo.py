import uuid

from sqlalchemy.orm import Session

from app.models.widget import Widget
from app.schemas.widget import WidgetCreate, WidgetUpdate


def create(db: Session, tenant_id: uuid.UUID, payload: WidgetCreate) -> Widget:
    widget = Widget(
        tenant_id=tenant_id,
        type=payload.type,
        title=payload.title,
        description=payload.description,
        fields=[f.model_dump() for f in payload.fields],
        button_text=payload.button_text,
        display_options=payload.display_options,
    )
    db.add(widget)
    db.commit()
    db.refresh(widget)
    return widget


def list_for_tenant(db: Session, tenant_id: uuid.UUID) -> list[Widget]:
    return db.query(Widget).filter(Widget.tenant_id == tenant_id).all()


def get_owned(db: Session, tenant_id: uuid.UUID, widget_id: uuid.UUID) -> Widget | None:
    """Returns None (→ 404) if the widget doesn't exist OR belongs to a
    different tenant. Callers must never be able to distinguish the two —
    that distinction itself would leak information across tenants."""
    return (
        db.query(Widget)
        .filter(Widget.id == widget_id, Widget.tenant_id == tenant_id)
        .first()
    )


def get_public(db: Session, widget_id: uuid.UUID) -> Widget | None:
    """For the public config/delivery endpoints — no tenant filter (there's
    no authenticated tenant on this path), but only active widgets are
    servable."""
    return (
        db.query(Widget)
        .filter(Widget.id == widget_id, Widget.is_active.is_(True))
        .first()
    )


def update(db: Session, widget: Widget, payload: WidgetUpdate) -> Widget:
    updates = payload.model_dump(exclude_unset=True)
    if "fields" in updates and updates["fields"] is not None:
        updates["fields"] = [f if isinstance(f, dict) else f.model_dump() for f in updates["fields"]]
    for key, value in updates.items():
        setattr(widget, key, value)
    if updates:
        # bump cache-bust key whenever config-affecting fields change
        widget.bundle_version = str(int(widget.bundle_version) + 1)
    db.commit()
    db.refresh(widget)
    return widget


def delete(db: Session, widget: Widget) -> None:
    db.delete(widget)
    db.commit()
