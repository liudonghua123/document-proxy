# app/auth.py
"""Bearer API_KEY 鉴权：REST dependency + /mcp ASGI 中间件。"""
import secrets
from typing import Optional

from fastapi import HTTPException, Request, status
from fastapi.security.http import HTTPAuthorizationCredentials, HTTPBearer
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

_bearer_scheme = HTTPBearer(auto_error=False)


def verify_bearer(
    credentials: Optional[HTTPAuthorizationCredentials],
    api_key: str,
) -> None:
    if credentials is None or not BearerAuthMiddleware._matches(credentials.credentials, api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )


class BearerAuthMiddleware(BaseHTTPMiddleware):
    """保护指定路径前缀（/mcp）的 Bearer 鉴权中间件。"""

    def __init__(self, app, api_key: str, protected_prefixes: tuple = ("/mcp",)) -> None:
        super().__init__(app)
        self.api_key = api_key
        self.protected_prefixes = protected_prefixes

    @staticmethod
    def _matches(a: str, b: str) -> bool:
        return secrets.compare_digest(a.encode(), b.encode())

    def _authorized(self, request: Request) -> bool:
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth[7:].strip()
            return bool(token) and self._matches(token, self.api_key)
        return False

    async def dispatch(self, request: Request, call_next):
        if any(request.url.path.startswith(p) for p in self.protected_prefixes):
            if not self._authorized(request):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid or missing API key"},
                    headers={"WWW-Authenticate": "Bearer"},
                )
        return await call_next(request)
