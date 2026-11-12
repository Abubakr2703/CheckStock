from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

from .base import utcnow


class OperationEvent(Base):
    """Неизменяемый аудит-лог: история операций.

    Подписи складов и товара сохраняются снимком, поэтому переименование
    или архивирование склада не переписывает историю.
    """

    __tablename__ = "operation_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    operation_id: Mapped[int] = mapped_column(
        ForeignKey("operations.id"), nullable=False, index=True
    )
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    from_warehouse_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    to_warehouse_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    product_label: Mapped[str] = mapped_column(String(280), nullable=False)
    from_label: Mapped[str | None] = mapped_column(String(140), nullable=True)
    to_label: Mapped[str | None] = mapped_column(String(140), nullable=True)

    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    __table_args__ = (
        Index("ix_events_store_created", "store_id", "created_at"),
        Index("ix_events_store_type", "store_id", "event_type"),
    )
