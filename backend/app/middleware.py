"""HTTP hardening middleware: security headers + per-IP rate limiting."""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config import settings
from app.ratelimit import limiter

# Auth endpoints get the tighter (brute-force) limit.
_LOGIN_PATHS = ("/api/auth/login", "/api/auth/refresh")


def _client_ip(request: Request) -> str:
    """Best-effort client IP, honoring a single reverse proxy (Caddy)."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach standard security response headers to every response."""

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        if not settings.security_headers_enabled:
            return response
        headers = response.headers
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("X-Frame-Options", "DENY")
        headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        headers.setdefault("X-XSS-Protection", "0")
        headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        if settings.hsts_enabled:
            headers.setdefault(
                "Strict-Transport-Security",
                f"max-age={settings.hsts_max_age}; includeSubDomains",
            )
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Fixed-window per-IP rate limiting for the JSON API.

    Only ``/api/*`` requests are limited (health probes, the WebSocket handshake,
    and static assets are exempt). CORS preflight (``OPTIONS``) is never counted.
    """

    async def dispatch(self, request: Request, call_next):
        if not settings.rate_limit_enabled:
            return await call_next(request)

        path = request.url.path
        if request.method == "OPTIONS" or not path.startswith("/api/"):
            return await call_next(request)

        is_login = path in _LOGIN_PATHS
        limit = (
            settings.rate_limit_login_per_minute
            if is_login
            else settings.rate_limit_per_minute
        )
        window = settings.rate_limit_window_seconds
        scope = "login" if is_login else "api"
        key = f"{scope}:{_client_ip(request)}"

        allowed, remaining, retry_after = await limiter.hit(key, limit, window)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please slow down."},
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
