"""Модели домена.

Пакет импортирует все модели, чтобы SQLAlchemy зарегистрировал их в metadata
до вызова create_all / configure_mappers.
"""

from .enums import EventType, OpKind, OpStatus
from .event import OperationEvent
from .operation import Operation
from .product import Product
from .store import Store
from .warehouse import Warehouse

__all__ = [
    "EventType",
    "OpKind",
    "OpStatus",
    "Operation",
    "OperationEvent",
    "Product",
    "Store",
    "Warehouse",
]
