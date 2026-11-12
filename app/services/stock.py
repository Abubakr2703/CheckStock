from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import OpKind, Operation, OpStatus


@dataclass
class TransitItem:
    operation_id: int
    product_id: int
    quantity: int
    from_warehouse_id: int | None
    to_warehouse_id: int | None
    created_at: datetime
    note: str | None = None


@dataclass
class StockState:
    physical: dict[tuple[int, int], int] = field(default_factory=dict)
    reserved: dict[tuple[int, int], int] = field(default_factory=dict)
    transfers_in_transit: list[TransitItem] = field(default_factory=list)
    fbo_in_transit: list[TransitItem] = field(default_factory=list)
    fbs_to_customer: list[TransitItem] = field(default_factory=list)
    fbo_at_marketplace: dict[int, int] = field(default_factory=dict)
    delivered: dict[int, int] = field(default_factory=dict)
    lost: dict[int, int] = field(default_factory=dict)

    def physical_of(self, product_id: int, warehouse_id: int) -> int:
        return self.physical.get((product_id, warehouse_id), 0)

    def reserved_of(self, product_id: int, warehouse_id: int) -> int:
        return self.reserved.get((product_id, warehouse_id), 0)

    def available_of(self, product_id: int, warehouse_id: int) -> int:
        return self.physical_of(product_id, warehouse_id) - self.reserved_of(
            product_id, warehouse_id
        )

    def product_total(self, product_id: int) -> int:
        """Сколько единиц товара сейчас числится в системе."""
        total = sum(
            qty for (pid, _wid), qty in self.physical.items() if pid == product_id
        )
        total += sum(
            item.quantity
            for item in self.transfers_in_transit
            if item.product_id == product_id
        )
        total += sum(
            item.quantity
            for item in self.fbo_in_transit
            if item.product_id == product_id
        )
        total += self.fbo_at_marketplace.get(product_id, 0)
        total += sum(
            item.quantity
            for item in self.fbs_to_customer
            if item.product_id == product_id
        )
        return total

    def grand_total(self) -> int:
        return (
            sum(self.physical.values())
            + sum(item.quantity for item in self.transfers_in_transit)
            + sum(item.quantity for item in self.fbo_in_transit)
            + sum(self.fbo_at_marketplace.values())
            + sum(item.quantity for item in self.fbs_to_customer)
        )

    def in_transit_total(self) -> int:
        return sum(item.quantity for item in self.transfers_in_transit) + sum(
            item.quantity for item in self.fbo_in_transit
        )

    def customer_total(self) -> int:
        return sum(item.quantity for item in self.fbs_to_customer)

    def marketplace_total(self) -> int:
        return sum(self.fbo_at_marketplace.values())


def _add(bucket: dict, key, quantity: int) -> None:
    bucket[key] = bucket.get(key, 0) + quantity


def compute_stock(db: Session, store_id: int) -> StockState:
    """Считает остатки и «где сейчас товар» из журнала операций."""
    state = StockState()
    operations = db.scalars(
        select(Operation)
        .where(Operation.store_id == store_id)
        .order_by(Operation.created_at, Operation.id)
    ).all()

    for op in operations:
        px = op.product_id

        if op.kind == OpKind.RECEIPT and op.status == OpStatus.COMPLETED:
            if op.to_warehouse_id is not None:
                _add(state.physical, (px, op.to_warehouse_id), op.quantity)

        elif op.kind == OpKind.TRANSFER:
            if op.status not in {OpStatus.IN_TRANSIT, OpStatus.COMPLETED}:
                continue
            if op.from_warehouse_id is not None:
                _add(state.physical, (px, op.from_warehouse_id), -op.quantity)

            if op.status == OpStatus.IN_TRANSIT:
                state.transfers_in_transit.append(
                    TransitItem(
                        operation_id=op.id,
                        product_id=px,
                        quantity=op.quantity,
                        from_warehouse_id=op.from_warehouse_id,
                        to_warehouse_id=op.to_warehouse_id,
                        created_at=op.created_at,
                        note=op.note,
                    )
                )
            else:
                received = (
                    op.received_quantity
                    if op.received_quantity is not None
                    else op.quantity
                )
                if op.to_warehouse_id is not None:
                    _add(state.physical, (px, op.to_warehouse_id), received)
                shortage = op.quantity - received
                if shortage > 0:
                    _add(state.lost, px, shortage)

        elif op.kind == OpKind.FBS_RESERVE and op.status == OpStatus.ACTIVE:
            if op.from_warehouse_id is not None:
                _add(state.reserved, (px, op.from_warehouse_id), op.quantity)

        elif op.kind == OpKind.FBS_SHIP and op.status in {
            OpStatus.SHIPPED,
            OpStatus.DELIVERED,
        }:
            if op.from_warehouse_id is not None:
                _add(state.physical, (px, op.from_warehouse_id), -op.quantity)
            if op.status == OpStatus.SHIPPED:
                state.fbs_to_customer.append(
                    TransitItem(
                        operation_id=op.id,
                        product_id=px,
                        quantity=op.quantity,
                        from_warehouse_id=op.from_warehouse_id,
                        to_warehouse_id=None,
                        created_at=op.created_at,
                        note=op.note,
                    )
                )
            else:
                _add(state.delivered, px, op.quantity)

        elif op.kind == OpKind.FBO_SHIP and op.status in {
            OpStatus.IN_TRANSIT,
            OpStatus.COMPLETED,
        }:
            if op.from_warehouse_id is not None:
                _add(state.physical, (px, op.from_warehouse_id), -op.quantity)

            if op.status == OpStatus.IN_TRANSIT:
                state.fbo_in_transit.append(
                    TransitItem(
                        operation_id=op.id,
                        product_id=px,
                        quantity=op.quantity,
                        from_warehouse_id=op.from_warehouse_id,
                        to_warehouse_id=None,
                        created_at=op.created_at,
                        note=op.note,
                    )
                )
            else:
                received = (
                    op.received_quantity
                    if op.received_quantity is not None
                    else op.quantity
                )
                _add(state.fbo_at_marketplace, px, received)
                shortage = op.quantity - received
                if shortage > 0:
                    _add(state.lost, px, shortage)

    return state
