from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Важно: переменные должны быть выставлены до импорта app.*
os.environ["DATABASE_URL"] = f"sqlite:///{(ROOT / 'test_checkstock.db').as_posix()}"
os.environ["AUTO_SEED"] = "false"

import pytest  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.models import Product, Store, Warehouse  # noqa: E402
from app.seed import seed_demo  # noqa: E402


@pytest.fixture()
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        seed_demo(session)
        yield session


def refs(db):
    store = db.scalar(select(Store).order_by(Store.id))
    warehouses = {
        warehouse.name: warehouse
        for warehouse in db.scalars(select(Warehouse).order_by(Warehouse.id)).all()
    }
    products = {
        product.sku: product
        for product in db.scalars(select(Product).order_by(Product.id)).all()
    }
    return store, warehouses, products
