import asyncio
from contextlib import asynccontextmanager

from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.api.v1.router import router as api_router
from app.core.config import settings
from app.web.routes import router as web_router


def run_migrations() -> None:
    command.upgrade(Config("alembic.ini"), "head")


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.auto_migrate:
        await asyncio.to_thread(run_migrations)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        https_only=settings.secure_cookies,
        same_site="lax",
        max_age=settings.session_max_age_seconds,
    )
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    app.include_router(api_router, prefix="/api/v1")
    app.include_router(web_router)
    app.mount("/static", StaticFiles(directory="app/web/static"), name="static")

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
