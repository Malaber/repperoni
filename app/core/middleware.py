import logging
from collections.abc import Sequence

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import Settings

logger = logging.getLogger("uvicorn.error")
UNSAFE_METHODS = {"DELETE", "PATCH", "POST", "PUT"}
STRICT_CSP = (
    "default-src 'none'; "
    "base-uri 'none'; "
    "connect-src 'self'; "
    "font-src 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'; "
    "img-src 'self' data:; "
    "manifest-src 'self'; "
    "object-src 'none'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "worker-src 'self'"
)
API_CSP = "default-src 'none'; base-uri 'none'; frame-ancestors 'none'"
DEVELOPMENT_DOCS_CSP = (
    "default-src 'none'; "
    "base-uri 'none'; "
    "frame-ancestors 'none'; "
    "img-src 'self' data: https://fastapi.tiangolo.com; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net"
)


async def _json_error(
    scope: Scope, receive: Receive, send: Send, *, status_code: int, detail: str
) -> None:
    await JSONResponse({"detail": detail}, status_code=status_code)(scope, receive, send)


class RequestBodyLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] not in UNSAFE_METHODS:
            await self.app(scope, receive, send)
            return

        content_length = Headers(scope=scope).get("content-length")
        if content_length:
            try:
                declared_length = int(content_length)
            except ValueError:
                await _json_error(
                    scope, receive, send, status_code=400, detail="Invalid Content-Length"
                )
                return
            if declared_length < 0:
                await _json_error(
                    scope, receive, send, status_code=400, detail="Invalid Content-Length"
                )
                return
            if declared_length > self.max_bytes:
                await _json_error(
                    scope, receive, send, status_code=413, detail="Request body too large"
                )
                return

        messages: list[Message] = []
        received = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            if message["type"] != "http.request":
                messages.append(message)
                continue
            received += len(message.get("body", b""))
            if received > self.max_bytes:
                await _json_error(
                    scope, receive, send, status_code=413, detail="Request body too large"
                )
                return
            messages.append(message)
            if not message.get("more_body", False):
                break

        message_index = 0

        async def replay_receive() -> Message:
            nonlocal message_index
            if message_index < len(messages):
                message = messages[message_index]
                message_index += 1
                return message
            return await receive()

        await self.app(scope, replay_receive, send)


class OriginProtectionMiddleware:
    def __init__(self, app: ASGIApp, trusted_origins: Sequence[str]) -> None:
        self.app = app
        self.trusted_origins = frozenset(trusted_origins)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] in UNSAFE_METHODS:
            headers = Headers(scope=scope)
            origin = headers.get("origin")
            has_bearer = headers.get("authorization", "").lower().startswith("bearer ")
            has_csrf_proof = headers.get("x-repperoni-csrf") == "1"
            if (
                not has_bearer
                and origin not in self.trusted_origins
                and not (origin in {None, "", "null"} and has_csrf_proof)
            ):
                logger.warning("Blocked unsafe request from untrusted origin %r", origin)
                await _json_error(
                    scope, receive, send, status_code=403, detail="Untrusted request origin"
                )
                return
        await self.app(scope, receive, send)


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")

        async def send_with_security_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["Content-Security-Policy"] = self._content_security_policy(path)
                headers["Cross-Origin-Opener-Policy"] = "same-origin"
                headers["Cross-Origin-Resource-Policy"] = "same-origin"
                headers["Permissions-Policy"] = (
                    "camera=(), geolocation=(), microphone=(), payment=(), usb=()"
                )
                headers["Referrer-Policy"] = "no-referrer"
                headers["X-Content-Type-Options"] = "nosniff"
                headers["X-Frame-Options"] = "DENY"
                headers["X-XSS-Protection"] = "0"
                if path in {"/", "/login"} or path.startswith("/api/"):
                    headers["Cache-Control"] = "private, no-store"
                if self.settings.secure_cookies:
                    headers["Strict-Transport-Security"] = "max-age=31536000"
            await send(message)

        await self.app(scope, receive, send_with_security_headers)

    @staticmethod
    def _content_security_policy(path: str) -> str:
        if path in {"/docs", "/redoc"}:
            return DEVELOPMENT_DOCS_CSP
        if path.startswith("/api/") or path == "/openapi.json":
            return API_CSP
        return STRICT_CSP
