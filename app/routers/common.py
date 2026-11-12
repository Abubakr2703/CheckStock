from __future__ import annotations

from datetime import datetime
from urllib.parse import urlencode
from uuid import uuid4

from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import BASE_DIR
from app.models import EventType

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

EVENT_LABELS = {
    EventType.RECEIPT: "Приход",
    EventType.TRANSFER_SENT: "Перемещение отправлено",
    EventType.TRANSFER_RECEIVED: "Перемещение принято",
    EventType.TRANSFER_SHORTAGE: "Недостача при перемещении",
    EventType.FBS_RESERVED: "Резерв FBS",
    EventType.FBS_CANCELLED: "Резерв FBS отменён",
    EventType.FBS_SHIPPED: "Отправка FBS",
    EventType.FBS_DELIVERED: "FBS доставлено клиенту",
    EventType.FBO_SENT: "Отправка FBO",
    EventType.FBO_RECEIVED: "FBO принято на маркетплейсе",
    EventType.FBO_SHORTAGE: "Недостача FBO",
}

EVENT_BADGES = {
    EventType.RECEIPT: "in",
    EventType.TRANSFER_SENT: "out",
    EventType.TRANSFER_RECEIVED: "in",
    EventType.TRANSFER_SHORTAGE: "danger",
    EventType.FBS_RESERVED: "hold",
    EventType.FBS_CANCELLED: "neutral",
    EventType.FBS_SHIPPED: "out",
    EventType.FBS_DELIVERED: "done",
    EventType.FBO_SENT: "out",
    EventType.FBO_RECEIVED: "in",
    EventType.FBO_SHORTAGE: "danger",
}


def page_key() -> str:
    return uuid4().hex


def redirect(path: str, *, msg: str | None = None, err: str | None = None):
    params = {}
    if msg:
        params["msg"] = msg
    if err:
        params["err"] = err
    url = path
    if params:
        url += "?" + urlencode(params)
    return RedirectResponse(url, status_code=303)


def label_for(mapping: dict, key: int | None) -> str:
    if key is None:
        return "—"
    value = mapping.get(key)
    return value.name if value else "—"


def fmt_dt(value: datetime | None) -> str:
    if value is None:
        return "—"
    return value.strftime("%d.%m.%Y %H:%M")


templates.env.filters["dt"] = fmt_dt
