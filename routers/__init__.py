"""HTTP-слой: отдельный роутер на экран/сценарий."""

from . import api, dashboard, history, movements, shipments, warehouses

routers = [
    dashboard.router,
    warehouses.router,
    movements.router,
    shipments.router,
    history.router,
    api.router,
]

__all__ = ["routers"]
