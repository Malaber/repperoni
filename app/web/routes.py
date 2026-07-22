import hashlib
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_optional_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models import User
from app.services.auth_sessions import revoke_auth_session


router = APIRouter(tags=["web"])
templates = Jinja2Templates(directory="app/web/templates")
static_root = Path("app/web/static")


@lru_cache(maxsize=1)
def asset_version() -> str:
    digest = hashlib.sha256()
    for filename in ("app.css", "app.js", "helpers.js", "service-worker.js"):
        path = static_root / filename
        if path.exists():
            digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, user: User | None = Depends(get_optional_current_user)):
    if user is None:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(
        request,
        "index.html",
        {"user": user, "app_name": settings.app_name, "asset_version": asset_version()},
    )


@router.get("/login", response_class=HTMLResponse)
async def login(request: Request, user: User | None = Depends(get_optional_current_user)):
    if user is not None:
        return RedirectResponse("/", status_code=303)
    next_url = request.query_params.get("next", "/")
    if not next_url.startswith("/") or next_url.startswith("//"):
        next_url = "/"
    return templates.TemplateResponse(
        request,
        "login.html",
        {"app_name": settings.app_name, "asset_version": asset_version(), "next_url": next_url},
    )


@router.post("/logout")
async def logout(request: Request, db: AsyncSession = Depends(get_db)):
    await revoke_auth_session(request, db)
    return RedirectResponse("/login", status_code=303)


@router.get("/manifest.webmanifest", include_in_schema=False)
async def manifest():
    return FileResponse(
        static_root / "manifest.webmanifest", media_type="application/manifest+json"
    )


@router.get("/service-worker.js", include_in_schema=False)
async def service_worker():
    return FileResponse(
        static_root / "service-worker.js",
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache"},
    )


@router.get("/.well-known/apple-app-site-association", include_in_schema=False)
@router.get("/apple-app-site-association", include_in_schema=False)
async def apple_app_site_association():
    if not settings.webcredentials_apps:
        raise HTTPException(status_code=404, detail="Apple app site association is not configured")
    return JSONResponse({"webcredentials": {"apps": settings.webcredentials_apps}})
