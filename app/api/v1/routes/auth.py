from datetime import timedelta

from fastapi import APIRouter
from fastpasskey import FastPasskey, PasskeyRouterConfig, create_passkey_router

from app.api.deps import get_current_user
from app.core.config import settings
from app.services.passkey_repository import get_passkey_repository


def passkey_service() -> FastPasskey:
    return FastPasskey(
        rp_name=settings.app_name,
        rp_id=settings.webauthn_rp_id,
        origin=settings.app_base_url,
        flow_ttl=timedelta(seconds=settings.auth_flow_expire_seconds),
    )


SAFE_ROUTE_PATHS = frozenset(
    {
        "/auth/assets/fastpasskey.css",
        "/auth/assets/fastpasskey.js",
        "/auth/login",
        "/auth/login/options",
        "/auth/login/verify",
        "/auth/logout",
        "/auth/me",
        "/auth/passkeys",
        "/auth/passkeys/{passkey_id}/delete/options",
        "/auth/passkeys/{passkey_id}/delete/verify",
        "/auth/passkeys/{passkey_id}/rename/options",
        "/auth/passkeys/{passkey_id}/rename/verify",
        "/auth/register",
        "/auth/register/options",
        "/auth/register/verify",
    }
)


def passkey_router() -> APIRouter:
    generated = create_passkey_router(
        PasskeyRouterConfig(
            service_factory=passkey_service,
            repository_dependency=get_passkey_repository,
            current_user_dependency=get_current_user,
            enable_add_link_routes=False,
            initial_passkey_name="Gym passkey",
        )
    )
    generated.routes[:] = [
        route for route in generated.routes if getattr(route, "path", None) in SAFE_ROUTE_PATHS
    ]
    return generated


router = passkey_router()
