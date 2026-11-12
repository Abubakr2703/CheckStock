from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import OpKind, Operation, OpStatus
from app.services.catalog import get_default_store, list_products
from app.services.common import DomainError
from app.services.fbo import receive_fbo, ship_fbo
from app.services.fbs import (
    cancel_fbs_reserve,
    deliver_fbs_ship,
    reserve_fbs,
    ship_fbs_reserve,
)
from app.services.stock import compute_stock
from app.services.warehouses import list_warehouses

from .common import page_key, redirect, templates

router = APIRouter()


@router.get("/shipments")
def shipments_page(request: Request, db: Session = Depends(get_db)):
    store = get_default_store(db)
    products = list_products(db, store.id)
    warehouses = list_warehouses(db, store.id)
    active_warehouses = [w for w in warehouses if not w.is_archived]
    state = compute_stock(db, store.id)

    product_by_id = {p.id: p for p in products}
    wh_by_id = {w.id: w for w in warehouses}

    reserves = db.scalars(
        select(Operation)
        .where(
            Operation.store_id == store.id,
            Operation.kind == OpKind.FBS_RESERVE,
            Operation.status == OpStatus.ACTIVE,
        )
        .order_by(Operation.created_at, Operation.id)
    ).all()

    shipped = db.scalars(
        select(Operation)
        .where(
            Operation.store_id == store.id,
            Operation.kind == OpKind.FBS_SHIP,
            Operation.status == OpStatus.SHIPPED,
        )
        .order_by(Operation.created_at.desc(), Operation.id.desc())
    ).all()

    fbo_pending = db.scalars(
        select(Operation)
        .where(
            Operation.store_id == store.id,
            Operation.kind == OpKind.FBO_SHIP,
            Operation.status == OpStatus.IN_TRANSIT,
        )
        .order_by(Operation.created_at, Operation.id)
    ).all()

    def enrich(op: Operation) -> dict:
        return {
            "op": op,
            "product": product_by_id.get(op.product_id),
            "warehouse": wh_by_id.get(op.from_warehouse_id),
        }

    fbo_mp = [
        {"product": product_by_id[pid], "quantity": quantity}
        for pid, quantity in sorted(state.fbo_at_marketplace.items())
        if quantity > 0 and pid in product_by_id
    ]

    return templates.TemplateResponse(
        request,
        "shipments.html",
        {
            "store": store,
            "products": products,
            "active_warehouses": active_warehouses,
            "reserves": [enrich(op) for op in reserves],
            "shipped": [enrich(op) for op in shipped],
            "fbo_pending": [enrich(op) for op in fbo_pending],
            "fbo_mp": fbo_mp,
            "key": page_key(),
        },
    )


@router.post("/shipments/fbs/reserve")
def reserve_action(
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
        op, created = reserve_fbs(
            db,
            store.id,
            product_id,
            warehouse_id,
            quantity,
            note.strip() or None,
            idempotency_key,
        )
    except DomainError as exc:
        return redirect("/shipments", err=str(exc))
    if not created:
        return redirect("/shipments", msg="Этот резерв уже создан.")
    return redirect(
        "/shipments",
        msg=(
            f"Резерв FBS создан: {op.quantity} ед. заблокированы на складе "
            "до отправки или отмены."
        ),
    )


@router.post("/shipments/fbs/{operation_id}/cancel")
def cancel_reserve_action(
    request: Request,
    operation_id: int,
    db: Session = Depends(get_db),
):
    store = get_default_store(db)
    try:
        op, changed = cancel_fbs_reserve(db, store.id, operation_id)
    except DomainError as exc:
        return redirect("/shipments", err=str(exc))
    if not changed:
        return redirect("/shipments", msg="Резерв уже отменён.")
    return redirect(
        "/shipments",
        msg=f"Резерв отменён: {op.quantity} ед. снова доступны.",
    )


@router.post("/shipments/fbs/{operation_id}/ship")
def ship_reserve_action(
    request: Request,
    operation_id: int,
    note: str = Form(""),
    idempotency_key: str = Form(...),
    db: Session = Depends(get_db),
):
    store = get_default_store(db)
    try:
        op, created = ship_fbs_reserve(
            db, store.id, operation_id, note.strip() or None, idempotency_key
        )
    except DomainError as exc:
        return redirect("/shipments", err=str(exc))
    if not created:
        return redirect(
            "/shipments",
            msg="Отправка уже подтверждена — повторное подтверждение не списало товар дважды.",
        )
    return redirect(
        "/shipments",
        msg=f"Заказ FBS отправлен: {op.quantity} ед. едут к клиенту.",
    )


@router.post("/shipments/fbs/{operation_id}/deliver")
def deliver_action(
    request: Request,
    operation_id: int,
    db: Session = Depends(get_db),
):
    store = get_default_store(db)
    try:
        op, changed = deliver_fbs_ship(db, store.id, operation_id)
    except DomainError as exc:
        return redirect("/shipments", err=str(exc))
    if not changed:
        return redirect("/shipments", msg="Доставка уже подтверждена.")
    return redirect(
        "/shipments",
        msg=f"Доставка подтверждена: {op.quantity} ед. переданы клиенту.",
    )


@router.post("/shipments/fbo/ship")
def fbo_ship_action(
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
        op, created = ship_fbo(
            db,
            store.id,
            product_id,
            warehouse_id,
            quantity,
            note.strip() or None,
            idempotency_key,
        )
    except DomainError as exc:
        return redirect("/shipments", err=str(exc))
    if not created:
        return redirect("/shipments", msg="Эта отправка FBO уже создана.")
    return redirect(
        "/shipments",
        msg=(
            f"Отправка FBO создана: {op.quantity} ед. покинули склад и числятся "
            "в пути до приёмки маркетплейсом."
        ),
    )


@router.post("/shipments/fbo/{operation_id}/receive")
def fbo_receive_action(
    request: Request,
    operation_id: int,
    received_quantity: int = Form(...),
    note: str = Form(""),
    idempotency_key: str = Form(...),
    db: Session = Depends(get_db),
):
    store = get_default_store(db)
    try:
        op, created = receive_fbo(
            db,
            store.id,
            operation_id,
            received_quantity,
            note.strip() or None,
            idempotency_key,
        )
    except DomainError as exc:
        return redirect("/shipments", err=str(exc))
    if not created:
        return redirect(
            "/shipments",
            msg="Приёмка FBO уже подтверждена — повторное подтверждение не изменило остатки.",
        )
    return redirect(
        "/shipments",
        msg=f"FBO принято на маркетплейсе: {op.received_quantity} ед.",
    )
