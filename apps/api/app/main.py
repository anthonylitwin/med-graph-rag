from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.admin import router as admin_router
from app.routes.health import router as health_router
from app.routes.chat import router as chat_router
from app.routes.graph import router as graph_router
from app.routes.ingestion import router as ingestion_router
from app.services.ingestion_service import get_ingestion_queue_service

app = FastAPI(
    title="MedGraphRAG API",
    version="0.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

app.include_router(health_router, tags=["health"])
app.include_router(chat_router, prefix="/chat", tags=["chat"])
app.include_router(graph_router, prefix="/graph", tags=["graph"])
app.include_router(ingestion_router, prefix="/ingestion", tags=["ingestion"])
app.include_router(admin_router, prefix="/admin", tags=["admin"])


@app.on_event("startup")
def start_ingestion_worker() -> None:
    get_ingestion_queue_service().start()


@app.on_event("shutdown")
def stop_ingestion_worker() -> None:
    get_ingestion_queue_service().stop()
