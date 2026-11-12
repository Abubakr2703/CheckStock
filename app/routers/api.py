from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.catalog import get_default_store, list_products
from app.services.stock import compute_stock
from app.services.warehouses import list_warehouses

router = APIRouter()


@router.get("/healthz")
def healthz():
    return {"status": "ok"}


@router.get("/api/stock")
def api_stock(db: Session = Depends(get_db)):
    """Read-only срез остатков: удобно для проверки и демонстрации API."""
    store = get_default_store(db)
    products = list_products(db, store.id)
    warehouses = list_warehouses(db, store.id)
    state = compute_stock(db, store.id)

    return {
        "store": {"id": store.id, "name": store.name},
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "totals": {
            "on_ff": sum(state.physical.values()),
            "in_transit": state.in_transit_total(),
            "marketplace": state.marketplace_total(),
            "customer": state.customer_total(),
            "in_system": state.grand_total(),
            "lost": sum(state.lost.values()),
            "delivered": sum(state.delivered.values()),
        },
        "products": [
            {
                "sku": product.sku,
                "name": product.name,
                "in_system": state.product_total(product.id),
                "warehouses": [
                    {
                        "id": warehouse.id,
                        "name": warehouse.name,
                        "archived": warehouse.is_archived,
                        "physical": state.physical_of(product.id, warehouse.id),
                        "reserved_fbs": state.reserved_of(product.id, warehouse.id),
                        "available": state.available_of(product.id, warehouse.id),
                    }
                    for warehouse in warehouses
                ],
            }
            for product in products
        ],
        "outside": {
            "transfers_in_transit": [
                {
                    "operation_id": item.operation_id,
                    "product_id": item.product_id,
                    "quantity": item.quantity,
                    "from_warehouse_id": item.from_warehouse_id,
                    "to_warehouse_id": item.to_warehouse_id,
                }
                for item in state.transfers_in_transit
            ],
            "fbo_in_transit": [
                {
                    "operation_id": item.operation_id,
                    "product_id": item.product_id,
                    "quantity": item.quantity,
                    "from_warehouse_id": item.from_warehouse_id,
                }
                for item in state.fbo_in_transit
            ],
            "fbo_at_marketplace": state.fbo_at_marketplace,
            "fbs_to_customer": [
                {
                    "operation_id": item.operation_id,
                    "product_id": item.product_id,
                    "quantity": item.quantity,
                    "from_warehouse_id": item.from_warehouse_id,
                }
                for item in state.fbs_to_customer
            ],
        },
    }
