from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from config import APP_TITLE, AUTO_SEED, BASE_DIR
from db import Base, SessionLocal, engine
from models import Store
from routers import routers
from seed import seed_demo


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
