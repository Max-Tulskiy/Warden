"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from warden_server.api import agents, audit, auth, policy, reports, requests
from warden_server.config import get_settings
from warden_server.db import SessionLocal
from warden_server.services.bootstrap import ensure_seed_operator

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    if settings.seed_admin_username and settings.seed_admin_password:
        db = SessionLocal()
        try:
            ensure_seed_operator(
                db,
                username=settings.seed_admin_username,
                password=settings.seed_admin_password,
            )
            db.commit()
        finally:
            db.close()
    yield


app = FastAPI(
    title="Warden",
    description="Insider-activity monitoring complex server",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agents.router)
app.include_router(requests.router)
app.include_router(auth.router)
app.include_router(reports.router)
app.include_router(policy.router)
app.include_router(audit.router)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
