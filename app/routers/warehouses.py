from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.catalog import get_default_store, list_products
from app.services.common import DomainError
from app.services.stock import compute_stock
from app.services.warehouses import (
    archive_warehouse,
    create_warehouse,
    list_warehouses,
    rename_warehouse,
)

from .common import page_key, redirect, templates

router = APIRouter()


@router.get("/warehouses")
def warehouses_page(request: Request, db: Session = Depends(get_db)):
    store = get_default_store(db)
    products = list_products(db, store.id)
    warehouses = list_warehouses(db, store.id)
    state = compute_stock(db, store.id)

    rows = []
    for warehouse in warehouses:
        physical = sum(state.physical_of(p.id, warehouse.id) for p in products)
        reserved = sum(state.reserved_of(p.id, warehouse.id) for p in products)
        sku_count = sum(
            1
            for p in products
            if state.physical_of(p.id, warehouse.id) > 0
            or state.reserved_of(p.id, warehouse.id) > 0
        )
        rows.append(
            {
                "warehouse": warehouse,
                "physical": physical,
                "reserved": reserved,
                "available": physical - reserved,
                "sku_count": sku_count,
            }
        )

    return templates.TemplateResponse(
        request,
        "warehouses.html",
        {
            "store": store,
            "active_rows": [r for r in rows if not r["warehouse"].is_archived],
            "archived_rows": [r for r in rows if r["warehouse"].is_archived],
            "key": page_key(),
        },
    )


@router.post("/warehouses")
def create_warehouse_action(
    request: Request,
    name: str = Form(...),
    db: Session = Depends(get_db),
):
    store = get_default_store(db)
    try:
        warehouse = create_warehouse(db, store.id, name)
    except DomainError as exc:
        return redirect("/warehouses", err=str(exc))
    return redirect("/warehouses", msg=f"Склад «{warehouse.name}» добавлен.")


@router.post("/warehouses/{warehouse_id}/rename")
def rename_warehouse_action(
    request: Request,
    warehouse_id: int,
    name: str = Form(...),
    db: Session = Depends(get_db),
):
    store = get_default_store(db)
    try:
        warehouse = rename_warehouse(db, store.id, warehouse_id, name)
    except DomainError as exc:
        return redirect("/warehouses", err=str(exc))
    return redirect("/warehouses", msg=f"Склад переименован в «{warehouse.name}».")


@router.post("/warehouses/{warehouse_id}/archive")
def archive_warehouse_action(
    request: Request,
    warehouse_id: int,
    db: Session = Depends(get_db),
):
    store = get_default_store(db)
    try:
        warehouse, changed = archive_warehouse(db, store.id, warehouse_id)
    except DomainError as exc:
        return redirect("/warehouses", err=str(exc))
    if not changed:
        return redirect("/warehouses", msg=f"Склад «{warehouse.name}» уже в архиве.")
    return redirect(
        "/warehouses",
        msg=(
            f"Склад «{warehouse.name}» удалён. Остатки и история сохранены, "
            "товар виден в архиве."
        ),
    )
