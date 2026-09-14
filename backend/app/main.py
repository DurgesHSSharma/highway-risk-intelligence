from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db.base import create_all
from app.ml.registry import load_models
from app.rag.retrieval import get_retrieval_service
from app.routers import documents, predictions, projects


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Table creation is idempotent and never touches existing data -- the
    # actual project/snapshot rows come from scripts/load_db.py, not here.
    create_all()
    # Fails loudly (raises, aborting startup) if a required Phase 4/5 model
    # artifact is missing -- see app/ml/registry.py. Models are loaded once
    # here, never per-request.
    load_models()
    # Phase 8: loads the FAISS index + embedding model once (see
    # app/rag/retrieval.py). Fails loudly if the index hasn't been built yet
    # (run `python -m scripts.build_rag_index` first).
    get_retrieval_service()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router)
app.include_router(predictions.router)
app.include_router(documents.router)


@app.get("/")
def read_root():
    return {"service": settings.app_name, "status": "ok"}


@app.get("/health")
def health_check():
    return {"status": "ok", "env": settings.app_env}
