from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Operation, OperationEvent, Product, Warehouse

from .common import DomainError, InsufficientStock
from .stock import compute_stock


def require_positive(quantity: int) -> int:
    if quantity is None or quantity <= 0:
        raise DomainError("Количество должно быть больше нуля.")
    return quantity


def get_product(db: Session, store_id: int, product_id: int) -> Product:
    product = db.scalar(
        select(Product).where(Product.id == product_id, Product.store_id == store_id)
    )
    if product is None:
        raise DomainError("Товар не найден.")
    return product


def get_warehouse(
    db: Session,
    store_id: int,
    warehouse_id: int,
    *,
    allow_archived: bool = False,
) -> Warehouse:
    warehouse = db.scalar(
        select(Warehouse).where(
            Warehouse.id == warehouse_id, Warehouse.store_id == store_id
        )
    )
    if warehouse is None:
        raise DomainError("Склад не найден.")
    if warehouse.is_archived and not allow_archived:
        raise DomainError(
            f"Склад «{warehouse.name}» в архиве. "
            "Переместите остаток на активный склад, чтобы продолжить."
        )
    return warehouse


def get_operation(
    db: Session,
    store_id: int,
    operation_id: int,
    kind: str | None = None,
    *,
    for_update: bool = False,
) -> Operation:
    query = select(Operation).where(
        Operation.id == operation_id, Operation.store_id == store_id
    )
    if kind is not None:
        query = query.where(Operation.kind == kind)
    if for_update:
        # Блокируем только строку операции, а не nullable-стороны joined load:
        # PostgreSQL не разрешает FOR UPDATE по nullable side outer join.
        query = query.with_for_update(of=Operation)
    operation = db.scalar(query)
    if operation is None:
        raise DomainError("Операция не найдена.")
    return operation


def lock_product(db: Session, product_id: int) -> None:
    """Сериализует изменения остатков одного товара (в PostgreSQL)."""
    db.execute(select(Product.id).where(Product.id == product_id).with_for_update()).first()


def require_stock(
    db: Session,
    store_id: int,
    product: Product,
    warehouse: Warehouse,
    quantity: int,
) -> None:
    state = compute_stock(db, store_id)
    available = state.available_of(product.id, warehouse.id)
    if quantity <= available:
        return

    elsewhere: list[tuple[str, int]] = []
    other_warehouses = db.scalars(
        select(Warehouse)
        .where(
            Warehouse.store_id == store_id,
            Warehouse.is_archived.is_(False),
            Warehouse.id != warehouse.id,
        )
        .order_by(Warehouse.id)
    ).all()
    for other in other_warehouses:
        qty = state.available_of(product.id, other.id)
        if qty > 0:
            elsewhere.append((other.name, qty))
    raise InsufficientStock(warehouse.name, available, quantity, elsewhere)


def add_event(
    db: Session,
    op: Operation,
    event_type: str,
    quantity: int,
    *,
    from_wh: Warehouse | None = None,
    to_wh: Warehouse | None = None,
    from_label: str | None = None,
    to_label: str | None = None,
    note: str | None = None,
    product: Product | None = None,
) -> OperationEvent:
    product = product or op.product
    event = OperationEvent(
        operation_id=op.id,
        store_id=op.store_id,
        product_id=op.product_id,
        event_type=event_type,
        quantity=quantity,
        from_warehouse_id=from_wh.id if from_wh else None,
        to_warehouse_id=to_wh.id if to_wh else None,
        product_label=f"{product.sku} · {product.name}",
        from_label=from_label if from_label is not None else (from_wh.name if from_wh else None),
        to_label=to_label if to_label is not None else (to_wh.name if to_wh else None),
        note=note,
    )
    db.add(event)
    return event
