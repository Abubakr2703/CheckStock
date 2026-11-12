from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models import Operation


class DomainError(Exception):
    """Ожидаемая ошибка бизнес-правила. Показывается пользователю."""


class InsufficientStock(DomainError):
    def __init__(
        self,
        warehouse_name: str,
        available: int,
        required: int,
        elsewhere: list[tuple[str, int]],
    ) -> None:
        self.available = available
        self.required = required
        self.elsewhere = elsewhere

        total_elsewhere = sum(qty for _, qty in elsewhere)
        if total_elsewhere >= required:
            details = ", ".join(f"«{name}» — {qty}" for name, qty in elsewhere if qty > 0)
            message = (
                f"На складе «{warehouse_name}» доступно {available} из {required} ед. "
                f"Но на других складах есть: {details}. "
                "Сначала оформите перемещение или выберите другой склад."
            )
        else:
            message = (
                f"Недостаточно товара на складе «{warehouse_name}»: "
                f"доступно {available}, нужно {required}. "
                f"Всего на других складах: {total_elsewhere} ед."
            )
        super().__init__(message)


def clean_key(key: str) -> str:
    key = (key or "").strip()
    if not key:
        raise DomainError("Не передан ключ идемпотентности операции.")
    if len(key) > 96:
        raise DomainError("Ключ идемпотентности слишком длинный.")
    return key


def existing_operation(db: Session, key: str) -> Operation | None:
    return db.scalar(select(Operation).where(Operation.idempotency_key == key))


def finish_operation(db: Session, op: Operation, key: str) -> tuple[Operation, bool]:
    """Коммитит операцию; гонку по одному ключу превращает в повторный ответ."""
    try:
        db.commit()
        return op, True
    except IntegrityError:
        db.rollback()
        existing = existing_operation(db, key)
        if existing is None:
            raise
        return existing, False
