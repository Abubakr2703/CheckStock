from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import EventType, Operation, OpKind, OpStatus
from app.models.base import utcnow

from .common import clean_key, existing_operation, finish_operation
from .validation import (
    add_event,
    get_product,
    get_warehouse,
    lock_product,
    require_positive,
)


def add_receipt(
    db: Session,
    store_id: int,
    product_id: int,
    warehouse_id: int,
    quantity: int,
    note: str | None,
    idempotency_key: str,
) -> tuple[Operation, bool]:
    key = clean_key(idempotency_key)
    if existing := existing_operation(db, key):
        return existing, False

    quantity = require_positive(quantity)
    product = get_product(db, store_id, product_id)
    warehouse = get_warehouse(db, store_id, warehouse_id)
    lock_product(db, product.id)

    op = Operation(
        store_id=store_id,
        product_id=product.id,
        kind=OpKind.RECEIPT,
        status=OpStatus.COMPLETED,
        quantity=quantity,
        to_warehouse_id=warehouse.id,
        idempotency_key=key,
        note=note,
        completed_at=utcnow(),
    )
    db.add(op)
    db.flush()
    add_event(
        db,
        op,
        EventType.RECEIPT,
        quantity,
        to_wh=warehouse,
        note=note,
        product=product,
    )
    return finish_operation(db, op, key)
