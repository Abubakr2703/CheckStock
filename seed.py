from __future__ import annotations

import argparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from db import Base, SessionLocal, engine
from models import Product, Store, Warehouse
from services.receipts import add_receipt

STORE_NAME = "Демо-магазин"

# Тестовые данные из задания: один магазин и два ФФ.
SEED_STOCK: dict[str, dict[str, int]] = {
    "SKU-101": {"Север": 10, "Юг": 6},
    "SKU-102": {"Север": 5, "Юг": 0},
    "SKU-103": {"Север": 0, "Юг": 4},
}

PRODUCT_NAMES = {
    "SKU-101": "Органайзер",
    "SKU-102": "Контейнер",
    "SKU-103": "Корзина",
}


def seed_demo(db: Session, *, reset: bool = False) -> tuple[Store, bool]:
    """Создаёт демо-данные. Возвращает (магазин, были_ли_созданы_данные)."""
    if reset:
        Base.metadata.drop_all(bind=db.get_bind())
        Base.metadata.create_all(bind=db.get_bind())

    existing = db.scalar(select(Store).order_by(Store.id))
    if existing is not None:
        return existing, False

    store = Store(name=STORE_NAME)
    db.add(store)
    db.flush()

    warehouses = {
        name: Warehouse(store_id=store.id, name=name) for name in ("Север", "Юг")
    }
    db.add_all(warehouses.values())

    products = {
        sku: Product(store_id=store.id, sku=sku, name=name)
        for sku, name in PRODUCT_NAMES.items()
    }
    db.add_all(products.values())
    db.commit()

    for sku, by_warehouse in SEED_STOCK.items():
        for warehouse_name, quantity in by_warehouse.items():
            if quantity <= 0:
                continue
            add_receipt(
                db,
                store.id,
                products[sku].id,
                warehouses[warehouse_name].id,
                quantity,
                note="Демо-данные из тестового задания",
                idempotency_key=f"seed-receipt-{sku}-{warehouse_name}",
            )

    return store, True


def main() -> None:
    parser = argparse.ArgumentParser(description="Загрузить демо-данные CheckStock")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Удалить все таблицы и создать демо-данные заново",
    )
    args = parser.parse_args()

    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        store, created = seed_demo(db, reset=args.reset)
        if created:
            print(f"Демо-данные созданы: магазин «{store.name}».")
        else:
            print("Данные уже есть. Для пересоздания запустите с флагом --reset.")


if __name__ == "__main__":
    main()
