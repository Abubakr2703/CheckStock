from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import EventType, Operation, OpKind, OpStatus
from app.models.base import utcnow

from .common import DomainError, clean_key, existing_operation, finish_operation
from .validation import (
    add_event,
    get_operation,
    get_product,
    get_warehouse,
    lock_product,
    require_positive,
    require_stock,
)


def ship_fbo(
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
    require_stock(db, store_id, product, warehouse, quantity)

    op = Operation(
        store_id=store_id,
        product_id=product.id,
        kind=OpKind.FBO_SHIP,
        status=OpStatus.IN_TRANSIT,
        quantity=quantity,
        from_warehouse_id=warehouse.id,
        idempotency_key=key,
        note=note,
    )
    db.add(op)
    db.flush()
    add_event(
        db,
        op,
        EventType.FBO_SENT,
        quantity,
        from_wh=warehouse,
        to_label="Маркетплейс (FBO)",
        note=note,
        product=product,
    )
    return finish_operation(db, op, key)


def receive_fbo(
    db: Session,
    store_id: int,
    operation_id: int,
    received_quantity: int,
    note: str | None,
    idempotency_key: str,
) -> tuple[Operation, bool]:
    key = clean_key(idempotency_key)
    if existing := existing_operation(db, key):
        return existing, False

    op = get_operation(db, store_id, operation_id, OpKind.FBO_SHIP, for_update=True)
    if op.status == OpStatus.COMPLETED:
        return op, False
    if op.status != OpStatus.IN_TRANSIT:
        raise DomainError("Эту поставку нельзя подтвердить: она не в пути.")

    if received_quantity is None or received_quantity < 0:
        raise DomainError("Принятое количество не может быть отрицательным.")
    if received_quantity > op.quantity:
        raise DomainError("Нельзя принять больше, чем было отправлено.")

    op.status = OpStatus.COMPLETED
    op.received_quantity = received_quantity
    op.completed_at = utcnow()
    op.note = note or op.note
    db.flush()

    add_event(
        db,
        op,
        EventType.FBO_RECEIVED,
        received_quantity,
        from_wh=op.from_warehouse,
        to_label="Маркетплейс (FBO)",
        note=note,
    )
    shortage = op.quantity - received_quantity
    if shortage > 0:
        add_event(
            db,
            op,
            EventType.FBO_SHORTAGE,
            shortage,
            from_wh=op.from_warehouse,
            to_label="Маркетплейс (FBO)",
            note=(
                f"Отправлено {op.quantity} ед., принято {received_quantity} ед. "
                f"Недостача {shortage} ед. списана."
            ),
        )
    return finish_operation(db, op, key)
