from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.catalog import get_default_store, list_events, list_products
from app.services.warehouses import list_warehouses

from .common import EVENT_BADGES, EVENT_LABELS, templates

router = APIRouter()


@router.get("/history")
def history_page(
    request: Request,
    product_id: int | None = Query(None),
    warehouse_id: int | None = Query(None),
    event_type: str | None = Query(None),
    db: Session = Depends(get_db),
):
    store = get_default_store(db)
    products = list_products(db, store.id)
    warehouses = list_warehouses(db, store.id)
    events = list_events(
        db,
        store.id,
        product_id=product_id,
        warehouse_id=warehouse_id,
        event_type=event_type,
    )

    rows = []
    for event in events:
        direction = "—"
        if event.from_label and event.to_label:
            direction = f"{event.from_label} → {event.to_label}"
        elif event.from_label:
            direction = f"из «{event.from_label}»"
        elif event.to_label:
            direction = f"на «{event.to_label}»"

        rows.append(
            {
                "event": event,
                "label": EVENT_LABELS.get(event.event_type, event.event_type),
                "badge": EVENT_BADGES.get(event.event_type, "neutral"),
                "direction": direction,
            }
        )

    return templates.TemplateResponse(
        request,
        "history.html",
        {
            "store": store,
            "products": products,
            "warehouses": warehouses,
            "rows": rows,
            "event_types": EVENT_LABELS,
            "selected_product": product_id,
            "selected_warehouse": warehouse_id,
            "selected_type": event_type,
        },
    )
