from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from app.config import APP_TITLE, AUTO_SEED, BASE_DIR
from app.db import Base, SessionLocal, engine
from app.models import Store
from app.routers import routers
from app.seed import seed_demo


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)

    if AUTO_SEED:
        with SessionLocal() as db:
            if db.scalar(select(Store.id).limit(1)) is None:
                seed_demo(db)

    yield


app = FastAPI(
    title=APP_TITLE,
    description="Прототип учёта остатков на складах фулфилмента",
    version="1.0.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

for router in routers:
    app.include_router(router)
