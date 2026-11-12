from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db import SessionLocal
from app.main import app
from app.models import Operation, OperationEvent
from app.services import (
    DomainError,
    InsufficientStock,
    add_receipt,
    archive_warehouse,
    cancel_fbs_reserve,
    compute_stock,
    create_transfer,
    deliver_fbs_ship,
    receive_fbo,
    receive_transfer,
    rename_warehouse,
    reserve_fbs,
    ship_fbo,
    ship_fbs_reserve,
)
from tests.conftest import refs

SEED_TOTAL = 25  # 10 + 6 + 5 + 4


def assert_conserved(state, expected_total: int = SEED_TOTAL) -> None:
    """Сумма по всем локациям + доставлено + недостачи = приход за всё время."""
    total = (
        state.grand_total()
        + sum(state.delivered.values())
        + sum(state.lost.values())
    )
    assert total == expected_total


def test_seed_matches_task_data(db):
    store, warehouses, products = refs(db)
    state = compute_stock(db, store.id)

    assert state.physical_of(products["SKU-101"].id, warehouses["Север"].id) == 10
    assert state.physical_of(products["SKU-101"].id, warehouses["Юг"].id) == 6
    assert state.physical_of(products["SKU-102"].id, warehouses["Север"].id) == 5
    assert state.physical_of(products["SKU-102"].id, warehouses["Юг"].id) == 0
    assert state.physical_of(products["SKU-103"].id, warehouses["Север"].id) == 0
    assert state.physical_of(products["SKU-103"].id, warehouses["Юг"].id) == 4
    assert state.grand_total() == SEED_TOTAL


def test_receipt_is_idempotent(db):
    store, warehouses, products = refs(db)
    product = products["SKU-102"]

    op, created = add_receipt(
        db, store.id, product.id, warehouses["Юг"].id, 7, "поставка", "receipt-1"
    )
    assert created is True

    duplicate, created = add_receipt(
        db, store.id, product.id, warehouses["Юг"].id, 7, "поставка", "receipt-1"
    )
    assert created is False
    assert duplicate.id == op.id

    state = compute_stock(db, store.id)
    assert state.physical_of(product.id, warehouses["Юг"].id) == 7
    assert_conserved(state, SEED_TOTAL + 7)


def test_transfer_send_and_receive(db):
    store, warehouses, products = refs(db)
    product = products["SKU-101"]
    north, south = warehouses["Север"], warehouses["Юг"]

    op, created = create_transfer(
        db, store.id, product.id, north.id, south.id, 4, "переброска", "transfer-1"
    )
    assert created is True

    state = compute_stock(db, store.id)
    assert state.physical_of(product.id, north.id) == 6
    assert state.physical_of(product.id, south.id) == 6
    assert state.transfers_in_transit[0].quantity == 4
    assert state.available_of(product.id, north.id) == 6
    assert_conserved(state)

    received, created = receive_transfer(
        db, store.id, op.id, 4, None, "transfer-receive-1"
    )
    assert created is True

    state = compute_stock(db, store.id)
    assert state.physical_of(product.id, north.id) == 6
    assert state.physical_of(product.id, south.id) == 10
    assert state.transfers_in_transit == []
    assert_conserved(state)

    # Повторное подтверждение с другим ключом не зачисляет товар дважды.
    duplicate, created = receive_transfer(
        db, store.id, op.id, 4, None, "transfer-receive-2"
    )
    assert created is False
    assert duplicate.id == op.id
    state = compute_stock(db, store.id)
    assert state.physical_of(product.id, south.id) == 10
    assert_conserved(state)


def test_shortage_at_selected_ff_with_stock_elsewhere(db):
    store, warehouses, products = refs(db)
    product = products["SKU-101"]
    north, south = warehouses["Север"], warehouses["Юг"]

    with pytest.raises(InsufficientStock) as exc_info:
        create_transfer(
            db, store.id, product.id, south.id, north.id, 8, None, "shortage-1"
        )

    message = str(exc_info.value)
    assert "«Юг»" in message
    assert "доступно 6 из 8" in message
    assert "«Север» — 10" in message
    assert db.scalar(
        select(func.count(Operation.id)).where(
            Operation.idempotency_key == "shortage-1"
        )
    ) == 0


def test_fbs_reserve_cancel_ship_deliver(db):
    store, warehouses, products = refs(db)
    product = products["SKU-101"]
    north = warehouses["Север"]

    reserve, _ = reserve_fbs(
        db, store.id, product.id, north.id, 3, None, "reserve-1"
    )
    state = compute_stock(db, store.id)
    assert state.physical_of(product.id, north.id) == 10
    assert state.reserved_of(product.id, north.id) == 3
    assert state.available_of(product.id, north.id) == 7
    assert_conserved(state)

    _, changed = cancel_fbs_reserve(db, store.id, reserve.id)
    assert changed is True
    state = compute_stock(db, store.id)
    assert state.reserved_of(product.id, north.id) == 0
    assert state.available_of(product.id, north.id) == 10
    assert_conserved(state)

    reserve2, _ = reserve_fbs(
        db, store.id, product.id, north.id, 3, None, "reserve-2"
    )
    ship, created = ship_fbs_reserve(db, store.id, reserve2.id, None, "ship-1")
    assert created is True

    state = compute_stock(db, store.id)
    assert state.physical_of(product.id, north.id) == 7
    assert state.reserved_of(product.id, north.id) == 0
    assert state.available_of(product.id, north.id) == 7
    assert len(state.fbs_to_customer) == 1
    assert state.fbs_to_customer[0].quantity == 3
    assert_conserved(state)

    # Повторная отправка того же резерва не списывает второй раз.
    again, created = ship_fbs_reserve(db, store.id, reserve2.id, None, "ship-2")
    assert created is False
    assert again.id == ship.id
    assert compute_stock(db, store.id).physical_of(product.id, north.id) == 7

    deliver_fbs_ship(db, store.id, ship.id)
    state = compute_stock(db, store.id)
    assert state.fbs_to_customer == []
    assert state.delivered[product.id] == 3
    assert_conserved(state)


def test_fbo_flow_with_partial_acceptance(db):
    store, warehouses, products = refs(db)
    product = products["SKU-101"]
    north = warehouses["Север"]

    op, _ = ship_fbo(
        db, store.id, product.id, north.id, 5, "FBO", "fbo-ship-1"
    )
    state = compute_stock(db, store.id)
    assert state.physical_of(product.id, north.id) == 5
    assert state.fbo_in_transit[0].quantity == 5
    assert state.fbo_at_marketplace == {}
    assert_conserved(state)

    received, created = receive_fbo(db, store.id, op.id, 4, None, "fbo-recv-1")
    assert created is True
    state = compute_stock(db, store.id)
    assert state.fbo_in_transit == []
    assert state.fbo_at_marketplace[product.id] == 4
    assert state.lost[product.id] == 1
    assert_conserved(state)

    duplicate, created = receive_fbo(db, store.id, op.id, 4, None, "fbo-recv-2")
    assert created is False
    assert compute_stock(db, store.id).fbo_at_marketplace[product.id] == 4


def test_archive_warehouse_keeps_stock_and_history(db):
    store, warehouses, products = refs(db)
    product = products["SKU-101"]
    north, south = warehouses["Север"], warehouses["Юг"]

    before = compute_stock(db, store.id).grand_total()
    archived, changed = archive_warehouse(db, store.id, south.id)
    assert changed is True
    assert archived.is_archived is True

    state = compute_stock(db, store.id)
    assert state.physical_of(product.id, south.id) == 6
    assert state.grand_total() == before

    # Новый приход в архив запрещён.
    with pytest.raises(DomainError):
        add_receipt(db, store.id, product.id, south.id, 1, None, "archive-receipt")

    # Но остаток можно вывезти с архивного склада.
    op, _ = create_transfer(
        db, store.id, product.id, south.id, north.id, 6, None, "archive-transfer"
    )
    receive_transfer(db, store.id, op.id, 6, None, "archive-receive")
    state = compute_stock(db, store.id)
    assert state.physical_of(product.id, south.id) == 0
    assert state.physical_of(product.id, north.id) == 16
    assert_conserved(state)


def test_history_keeps_warehouse_name_snapshot(db):
    store, warehouses, products = refs(db)
    product = products["SKU-101"]
    south = warehouses["Юг"]

    add_receipt(db, store.id, product.id, south.id, 3, None, "snapshot-receipt")
    event = db.scalar(
        select(OperationEvent)
        .where(OperationEvent.operation_id.is_not(None))
        .order_by(OperationEvent.id.desc())
    )
    assert event.to_label == "Юг"

    rename_warehouse(db, store.id, south.id, "Юг-новый")
    db.refresh(event)
    assert event.to_label == "Юг"


def test_http_double_submit_does_not_duplicate(db):
    store, warehouses, products = refs(db)
    product = products["SKU-102"]
    south = warehouses["Юг"]

    payload = {
        "product_id": str(product.id),
        "warehouse_id": str(south.id),
        "quantity": "7",
        "note": "double click",
        "idempotency_key": "http-receipt-1",
    }

    with TestClient(app) as client:
        first = client.post(
            "/movements/receipt", data=payload, follow_redirects=False
        )
        second = client.post(
            "/movements/receipt", data=payload, follow_redirects=True
        )

    assert first.status_code == 303
    assert second.status_code == 200
    assert "уже был проведён" in second.text

    with SessionLocal() as check:
        state = compute_stock(check, store.id)
        assert state.physical_of(product.id, south.id) == 7
        assert_conserved(state, SEED_TOTAL + 7)


def test_pages_and_api_render(db):
    with TestClient(app) as client:
        for path in ("/", "/warehouses", "/movements", "/shipments", "/history"):
            response = client.get(path)
            assert response.status_code == 200, path
            assert "CheckStock" in response.text

        api = client.get("/api/stock")
        assert api.status_code == 200
        payload = api.json()
        assert payload["totals"]["in_system"] == SEED_TOTAL
        assert len(payload["products"]) == 3
