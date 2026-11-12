from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from db import get_db
from services.catalog import get_default_store, list_products
from services.stock import compute_stock
from services.warehouses import list_warehouses

from .common import label_for, templates

router = APIRouter()


@router.get("/")
def dashboard(request: Request, db: Session = Depends(get_db)):
    store = get_default_store(db)
    products = list_products(db, store.id)
    warehouses = list_warehouses(db, store.id)
    state = compute_stock(db, store.id)

    wh_by_id = {w.id: w for w in warehouses}
    product_by_id = {p.id: p for p in products}

    product_rows = []
    for product in products:
        rows = []
        for warehouse in warehouses:
            physical = state.physical_of(product.id, warehouse.id)
            reserved = state.reserved_of(product.id, warehouse.id)
            if warehouse.is_archived and physical == 0 and reserved == 0:
                continue
            rows.append(
                {
                    "warehouse": warehouse,
                    "physical": physical,
                    "reserved": reserved,
                    "available": physical - reserved,
                }
            )
        product_rows.append(
            {
                "product": product,
                "total": state.product_total(product.id),
                "warehouses": rows,
            }
        )

    transfers = []
    for item in state.transfers_in_transit:
        transfers.append(
            {
                "product": label_for(product_by_id, item.product_id),
                "quantity": item.quantity,
                "route": (
                    f"{label_for(wh_by_id, item.from_warehouse_id)} → "
                    f"{label_for(wh_by_id, item.to_warehouse_id)}"
                ),
                "created_at": item.created_at,
            }
        )

    fbo_transit = [
        {
            "product": label_for(product_by_id, item.product_id),
            "quantity": item.quantity,
            "route": (
                f"{label_for(wh_by_id, item.from_warehouse_id)} → Маркетплейс"
            ),
            "created_at": item.created_at,
        }
        for item in state.fbo_in_transit
    ]

    fbs_customer = [
        {
            "product": label_for(product_by_id, item.product_id),
            "quantity": item.quantity,
            "route": f"{label_for(wh_by_id, item.from_warehouse_id)} → Клиент",
            "created_at": item.created_at,
        }
        for item in state.fbs_to_customer
    ]

    fbo_mp = [
        {"product": product_by_id[pid], "quantity": quantity}
        for pid, quantity in sorted(state.fbo_at_marketplace.items())
        if quantity > 0 and pid in product_by_id
    ]

    stats = {
        "on_ff": sum(state.physical.values()),
        "in_transit": state.in_transit_total(),
        "marketplace": state.marketplace_total(),
        "customer": state.customer_total(),
        "total": state.grand_total(),
        "lost": sum(state.lost.values()),
        "delivered": sum(state.delivered.values()),
    }

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "store": store,
            "products": products,
            "warehouses": warehouses,
            "product_rows": product_rows,
            "stats": stats,
            "transfers": transfers,
            "fbo_transit": fbo_transit,
            "fbs_customer": fbs_customer,
            "fbo_mp": fbo_mp,
        },
    )
