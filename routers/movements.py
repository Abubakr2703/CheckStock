from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from db import get_db
from models import OpKind, Operation, OpStatus
from services.catalog import get_default_store, list_products
from services.common import DomainError
from services.receipts import add_receipt
from services.stock import compute_stock
from services.transfers import create_transfer, receive_transfer
from services.warehouses import list_warehouses

from .common import page_key, redirect, templates

router = APIRouter()


@router.get("/movements")
def movements_page(request: Request, db: Session = Depends(get_db)):
    store = get_default_store(db)
    products = list_products(db, store.id)
    warehouses = list_warehouses(db, store.id)
    active_warehouses = [w for w in warehouses if not w.is_archived]
    state = compute_stock(db, store.id)
    product_by_id = {p.id: p for p in products}
    wh_by_id = {w.id: w for w in warehouses}

    matrix_warehouses = [
        w
        for w in warehouses
        if not w.is_archived
        or any(state.physical_of(p.id, w.id) > 0 for p in products)
    ]

    matrix = [
        {
            "product": product,
            "cells": [
                {
                    "warehouse": warehouse,
                    "physical": state.physical_of(product.id, warehouse.id),
                    "reserved": state.reserved_of(product.id, warehouse.id),
                    "available": state.available_of(product.id, warehouse.id),
                }
                for warehouse in matrix_warehouses
            ],
        }
        for product in products
    ]

    pending = db.scalars(
        select(Operation)
        .where(
            Operation.store_id == store.id,
            Operation.kind == OpKind.TRANSFER,
            Operation.status == OpStatus.IN_TRANSIT,
        )
        .order_by(Operation.created_at, Operation.id)
    ).all()
    pending_transfers = [
        {
            "op": op,
            "product": product_by_id.get(op.product_id),
            "source": wh_by_id.get(op.from_warehouse_id),
            "destination": wh_by_id.get(op.to_warehouse_id),
        }
        for op in pending
    ]

    return templates.TemplateResponse(
        request,
        "movements.html",
        {
            "store": store,
            "products": products,
            "warehouses": warehouses,
            "active_warehouses": active_warehouses,
            "source_warehouses": [
                w
                for w in warehouses
                if not w.is_archived
                or any(state.physical_of(p.id, w.id) > 0 for p in products)
            ],
            "matrix": matrix,
            "matrix_warehouses": matrix_warehouses,
            "pending_transfers": pending_transfers,
            "key": page_key(),
        },
    )


@router.post("/movements/receipt")
def receipt_action(
    request: Request,
    product_id: int = Form(...),
    warehouse_id: int = Form(...),
    quantity: int = Form(...),
    note: str = Form(""),
    idempotency_key: str = Form(...),
    db: Session = Depends(get_db),
):
    store = get_default_store(db)
    try:
        op, created = add_receipt(
            db,
            store.id,
            product_id,
            warehouse_id,
            quantity,
            note.strip() or None,
            idempotency_key,
        )
    except DomainError as exc:
        return redirect("/movements", err=str(exc))
    if not created:
        return redirect(
            "/movements",
            msg="Этот приход уже был проведён — повторное подтверждение не изменило остатки.",
        )
    return redirect("/movements", msg=f"Приход проведён: +{op.quantity} ед. на склад.")


@router.post("/movements/transfer")
def transfer_action(
    request: Request,
    product_id: int = Form(...),
    from_warehouse_id: int = Form(...),
    to_warehouse_id: int = Form(...),
    quantity: int = Form(...),
    note: str = Form(""),
    idempotency_key: str = Form(...),
    db: Session = Depends(get_db),
):
    store = get_default_store(db)
    try:
        op, created = create_transfer(
            db,
            store.id,
            product_id,
            from_warehouse_id,
            to_warehouse_id,
            quantity,
            note.strip() or None,
            idempotency_key,
        )
    except DomainError as exc:
        return redirect("/movements", err=str(exc))
    if not created:
        return redirect("/movements", msg="Это перемещение уже отправлено.")
    return redirect(
        "/movements",
        msg=(
            f"Перемещение отправлено: {op.quantity} ед. в пути. "
            "Остаток на складе-отправителе уменьшен."
        ),
    )


@router.post("/movements/transfer/{operation_id}/receive")
def receive_transfer_action(
    request: Request,
    operation_id: int,
    received_quantity: int = Form(...),
    note: str = Form(""),
    idempotency_key: str = Form(...),
    db: Session = Depends(get_db),
):
    store = get_default_store(db)
    try:
        op, created = receive_transfer(
            db,
            store.id,
            operation_id,
            received_quantity,
            note.strip() or None,
            idempotency_key,
        )
    except DomainError as exc:
        return redirect("/movements", err=str(exc))
    if not created:
        return redirect(
            "/movements",
            msg="Приёмка уже подтверждена — повторное подтверждение не изменило остатки.",
        )
    return redirect(
        "/movements",
        msg=f"Перемещение принято: {op.received_quantity} ед. зачислено на склад.",
    )
