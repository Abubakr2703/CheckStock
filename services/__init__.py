"""Сервисный слой: бизнес-правила, отдельный модуль на сценарий."""

from .catalog import get_default_store, list_events, list_products
from .common import DomainError, InsufficientStock
from .fbo import receive_fbo, ship_fbo
from .fbs import (
    cancel_fbs_reserve,
    deliver_fbs_ship,
    reserve_fbs,
    ship_fbs_reserve,
)
from .receipts import add_receipt
from .stock import StockState, TransitItem, compute_stock
from .transfers import create_transfer, receive_transfer
from .warehouses import (
    archive_warehouse,
    create_warehouse,
    list_warehouses,
    rename_warehouse,
)

__all__ = [
    "DomainError",
    "InsufficientStock",
    "StockState",
    "TransitItem",
    "add_receipt",
    "archive_warehouse",
    "cancel_fbs_reserve",
    "compute_stock",
    "create_transfer",
    "create_warehouse",
    "deliver_fbs_ship",
    "get_default_store",
    "list_events",
    "list_products",
    "list_warehouses",
    "receive_fbo",
    "receive_transfer",
    "rename_warehouse",
    "reserve_fbs",
    "ship_fbo",
    "ship_fbs_reserve",
]
