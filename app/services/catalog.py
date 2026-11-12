from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import OperationEvent, Product, Store

from .common import DomainError


def get_default_store(db: Session) -> Store:
    store = db.scalar(select(Store).order_by(Store.id))
    if store is None:
        raise DomainError(
            "Магазин не найден. Загрузите демо-данные: python -m app.seed"
        )
    return store


def list_products(db: Session, store_id: int) -> list[Product]:
    return list(
        db.scalars(
            select(Product)
            .where(Product.store_id == store_id)
            .order_by(Product.sku)
        ).all()
    )


def list_events(
    db: Session,
    store_id: int,
    *,
    product_id: int | None = None,
    warehouse_id: int | None = None,
    event_type: str | None = None,
    limit: int = 300,
) -> list[OperationEvent]:
    query = select(OperationEvent).where(OperationEvent.store_id == store_id)
    if product_id:
        query = query.where(OperationEvent.product_id == product_id)
    if warehouse_id:
        query = query.where(
            (OperationEvent.from_warehouse_id == warehouse_id)
            | (OperationEvent.to_warehouse_id == warehouse_id)
        )
    if event_type:
        query = query.where(OperationEvent.event_type == event_type)
    query = query.order_by(
        OperationEvent.created_at.desc(), OperationEvent.id.desc()
    )
    return list(db.scalars(query.limit(limit)).all())
