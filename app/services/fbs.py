from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import EventType, Operation, OpKind, OpStatus
from app.models.base import utcnow

from .common import DomainError, clean_key, existing_operation, finish_operation
from .stock import compute_stock
from .validation import (
    add_event,
    get_operation,
    get_product,
    get_warehouse,
    lock_product,
    require_positive,
    require_stock,
)


def reserve_fbs(
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
        kind=OpKind.FBS_RESERVE,
        status=OpStatus.ACTIVE,
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
        EventType.FBS_RESERVED,
        quantity,
        from_wh=warehouse,
        note=note,
        product=product,
    )
    return finish_operation(db, op, key)


def cancel_fbs_reserve(
    db: Session, store_id: int, operation_id: int
) -> tuple[Operation, bool]:
    op = get_operation(db, store_id, operation_id, OpKind.FBS_RESERVE, for_update=True)
    if op.status == OpStatus.CANCELLED:
        return op, False
    if op.status == OpStatus.FULFILLED:
        raise DomainError("Резерв уже отправлен клиенту, отменить его нельзя.")
    if op.status != OpStatus.ACTIVE:
        raise DomainError("Резерв не активен.")

    op.status = OpStatus.CANCELLED
    op.cancelled_at = utcnow()
    db.flush()
    add_event(
        db,
        op,
        EventType.FBS_CANCELLED,
        op.quantity,
        from_wh=op.from_warehouse,
    )
    db.commit()
    return op, True


def ship_fbs_reserve(
    db: Session,
    store_id: int,
    reserve_id: int,
    note: str | None,
    idempotency_key: str,
) -> tuple[Operation, bool]:
    key = clean_key(idempotency_key)
    if existing := existing_operation(db, key):
        return existing, False

    reserve = get_operation(db, store_id, reserve_id, OpKind.FBS_RESERVE, for_update=True)
    if reserve.status == OpStatus.FULFILLED:
        child = db.scalar(
            select(Operation).where(
                Operation.parent_id == reserve.id,
                Operation.kind == OpKind.FBS_SHIP,
            )
        )
        if child is not None:
            return child, False
    if reserve.status == OpStatus.CANCELLED:
        raise DomainError("Резерв отменён — отправлять нечего.")
    if reserve.status != OpStatus.ACTIVE:
        raise DomainError("Резерв не активен.")

    lock_product(db, reserve.product_id)
    state = compute_stock(db, store_id)
    if state.physical_of(reserve.product_id, reserve.from_warehouse_id) < reserve.quantity:
        raise DomainError("Физического остатка на складе не хватает для отправки резерва.")

    op = Operation(
        store_id=store_id,
        product_id=reserve.product_id,
        kind=OpKind.FBS_SHIP,
        status=OpStatus.SHIPPED,
        quantity=reserve.quantity,
        from_warehouse_id=reserve.from_warehouse_id,
        parent_id=reserve.id,
        idempotency_key=key,
        note=note,
        completed_at=utcnow(),
    )
    db.add(op)
    reserve.status = OpStatus.FULFILLED
    reserve.completed_at = utcnow()
    db.flush()
    add_event(
        db,
        op,
        EventType.FBS_SHIPPED,
        op.quantity,
        from_wh=reserve.from_warehouse,
        to_label="Клиент (FBS)",
        note=note,
    )
    return finish_operation(db, op, key)


def deliver_fbs_ship(db: Session, store_id: int, operation_id: int) -> tuple[Operation, bool]:
    op = get_operation(db, store_id, operation_id, OpKind.FBS_SHIP, for_update=True)
    if op.status == OpStatus.DELIVERED:
        return op, False
    if op.status != OpStatus.SHIPPED:
        raise DomainError("Отправка не находится в пути.")

    op.status = OpStatus.DELIVERED
    op.completed_at = utcnow()
    db.flush()
    add_event(
        db,
        op,
        EventType.FBS_DELIVERED,
        op.quantity,
        from_wh=op.from_warehouse,
        to_label="Клиент (FBS)",
    )
    db.commit()
    return op, True
