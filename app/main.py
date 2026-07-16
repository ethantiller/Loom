from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import ingest, query
from app.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_settings()  # raises ValidationError immediately if any required var is missing
    yield


app = FastAPI(title="Loom", lifespan=lifespan)

app.include_router(ingest.router)
app.include_router(query.router)
