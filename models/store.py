from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db import Base

from .base import utcnow

if TYPE_CHECKING:
    from .product import Product
    from .warehouse import Warehouse


class Store(Base):
    __tablename__ = "stores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    warehouses: Mapped[list["Warehouse"]] = relationship(back_populates="store")
    products: Mapped[list["Product"]] = relationship(back_populates="store")
