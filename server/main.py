"""FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import config
from .api import glossary, jobs, papers, settings
from .jobs import manager


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    manager.shutdown()


app = FastAPI(
    title=config.APP_NAME,
    version=config.APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jobs.router, prefix="/api")
app.include_router(papers.router, prefix="/api")
app.include_router(settings.router, prefix="/api")
app.include_router(glossary.router, prefix="/api")


@app.get("/api/health", tags=["meta"])
async def health() -> dict:
    return {
        "ok": True,
        "name": config.APP_NAME,
        "version": config.APP_VERSION,
        "mock": config.MOCK,
        "data_dir": str(config.DATA_DIR),
    }


app.mount("/files", StaticFiles(directory=config.OUTPUT_DIR), name="files")

if config.WEB_OUT.exists():
    app.mount("/", StaticFiles(directory=config.WEB_OUT, html=True), name="web")
else:

    @app.get("/")
    async def index() -> dict:
        return {
            "name": config.APP_NAME,
            "docs": "/docs",
            "health": "/api/health",
            "hint": "web/out 不存在，当前仅提供 API；开发时请运行 web/ 的 npm run dev",
        }
