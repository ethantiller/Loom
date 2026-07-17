from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import ingest, query, graph, projects
from app.config import get_settings
from fastapi.middleware.cors import CORSMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_settings()  # raises ValidationError immediately if any required var is missing
    yield


app = FastAPI(title="Loom", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ingest.router)
app.include_router(query.router)
app.include_router(graph.router)
app.include_router(projects.router)


