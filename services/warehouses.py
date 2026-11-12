from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import Warehouse
from models.base import utcnow

from .common import DomainError
from .validation import get_warehouse


def _clean_name(name: str) -> str:
    name = (name or "").strip()
    if not name:
        raise DomainError("Название склада не может быть пустым.")
    if len(name) > 120:
        raise DomainError("Название склада длиннее 120 символов.")
    return name


def create_warehouse(db: Session, store_id: int, name: str) -> Warehouse:
    name = _clean_name(name)
    duplicate = db.scalar(
        select(Warehouse).where(
            Warehouse.store_id == store_id,
            Warehouse.is_archived.is_(False),
            func.lower(Warehouse.name) == name.lower(),
        )
    )
    if duplicate is not None:
        raise DomainError(f"Активный склад «{name}» уже существует.")
    warehouse = Warehouse(store_id=store_id, name=name)
    db.add(warehouse)
    db.commit()
    return warehouse


def rename_warehouse(
    db: Session, store_id: int, warehouse_id: int, name: str
) -> Warehouse:
    name = _clean_name(name)
    warehouse = get_warehouse(db, store_id, warehouse_id, allow_archived=True)
    duplicate = db.scalar(
        select(Warehouse).where(
            Warehouse.store_id == store_id,
            Warehouse.is_archived.is_(False),
            Warehouse.id != warehouse.id,
            func.lower(Warehouse.name) == name.lower(),
        )
    )
    if duplicate is not None:
        raise DomainError(f"Активный склад «{name}» уже существует.")
    warehouse.name = name
    db.commit()
    return warehouse


def archive_warehouse(
    db: Session, store_id: int, warehouse_id: int
) -> tuple[Warehouse, bool]:
    warehouse = get_warehouse(db, store_id, warehouse_id, allow_archived=True)
    if warehouse.is_archived:
        return warehouse, False
    warehouse.is_archived = True
    warehouse.archived_at = utcnow()
    db.commit()
    return warehouse, True


def list_warehouses(db: Session, store_id: int) -> list[Warehouse]:
    return list(
        db.scalars(
            select(Warehouse)
            .where(Warehouse.store_id == store_id)
            .order_by(Warehouse.is_archived, Warehouse.id)
        ).all()
    )
