from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

from .base import utcnow

if TYPE_CHECKING:
    from .product import Product
    from .warehouse import Warehouse


class Operation(Base):
    """Текущее состояние складской операции.

    Остатки не хранятся отдельными полями: они выводятся из операций.
    Это даёт сходимость и полную историю, а повторный запрос с тем же
    idempotency_key не создаёт вторую операцию.
    """

    __tablename__ = "operations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, index=True)

    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    received_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)

    from_warehouse_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouses.id"), nullable=True, index=True
    )
    to_warehouse_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouses.id"), nullable=True, index=True
    )

    # Для FBS-отправки: ссылка на резерв, который она закрывает.
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("operations.id"), nullable=True, index=True
    )

    idempotency_key: Mapped[str] = mapped_column(
        String(96), nullable=False, unique=True, index=True
    )
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    product: Mapped["Product"] = relationship(lazy="joined")
    from_warehouse: Mapped["Warehouse | None"] = relationship(
        foreign_keys=[from_warehouse_id], lazy="joined"
    )
    to_warehouse: Mapped["Warehouse | None"] = relationship(
        foreign_keys=[to_warehouse_id], lazy="joined"
    )

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_operations_quantity_positive"),
        CheckConstraint(
            "received_quantity IS NULL OR received_quantity >= 0",
            name="ck_operations_received_non_negative",
        ),
        Index("ix_operations_store_kind", "store_id", "kind"),
    )
