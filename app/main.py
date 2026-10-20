# app/main.py
"""应用工厂：组装 REST + MCP + 鉴权中间件。

MCP 挂载说明：
- fastmcp 4.x 使用 `mcp.http_app()`（内部路由为 '/mcp'），2.x 的
  `streamable_http_app()` 在 4.x 已移除。
- 将 mcp_app 挂载到 '/' 使其内部 '/mcp' 路由对外即 POST /mcp；
  REST 路由先注册，Mount('/') 兜底，互不冲突。
- lifespan：生产环境下 uvicorn 会执行 FastAPI 的 lifespan
  （create_app 传入 mcp_app.lifespan，用于启动 MCP 会话管理器）。
  但 httpx 的 ASGITransport 不会发送 lifespan 事件，因此用
  _LazyLifespanASGI 包装：首次收到 HTTP 请求时若 lifespan 尚未
  运行（例如测试传输、或 pytest-asyncio 每测试新建事件循环），
  则在后台任务中启动它，使 POST /mcp 在测试中也能正常工作。
"""
import asyncio
from typing import Any, AsyncIterator, Optional

from fastapi import FastAPI, HTTPException

from .auth import BearerAuthMiddleware
from .config import Settings
from .mcp_server import mcp, set_service
from .rest import envelope_http_exception_handler, router
from .service import DocumentService


class _LazyLifespanASGI:
    """按需启动被包装应用的 lifespan（首次 HTTP 请求时）。

    - 同一事件循环内只启动一次；
    - 收到 ASGI lifespan scope（如 uvicorn 正常启动流程）时，
      标记 lifespan 已由外部启动，_ensure_started 变为空操作，
      避免 lifespan 被运行两次；
    - lifespan 启动失败时把异常记录下来，等待方（首个 HTTP
      请求）直接重新抛出，而不是无限挂起；
    - 检测到事件循环更换（pytest-asyncio 每测试新建 loop）时重启；
      fastmcp 的 lifespan 每次运行都会创建全新的 session manager，
      因此重启是安全的。
    """

    def __init__(self, app) -> None:
        self._app = app
        self._loop_id: Optional[int] = None
        self._started = asyncio.Event()
        self._error: Optional[BaseException] = None
        self._lock = asyncio.Lock()

    async def _ensure_started(self) -> None:
        loop_id = id(asyncio.get_running_loop())
        async with self._lock:
            if self._error is not None:
                # lifespan 启动失败：向后续请求直接抛出已记录的异常，
                # 而不是挂起或反复重试。
                raise self._error
            if self._started.is_set() and self._loop_id == loop_id:
                # 已在当前事件循环启动（或由外部 lifespan scope 启动）
                return
            self._loop_id = loop_id
            self._started = asyncio.Event()
            self._error = None

            async def _run() -> None:
                try:
                    async with self._app.router.lifespan_context(self._app):
                        self._started.set()
                        await asyncio.Event().wait()
                except BaseException as e:  # noqa: BLE001 - 原样传给等待方
                    self._error = e
                    self._started.set()

            # 后台 lifespan 任务从不显式退出：懒启动的 lifespan
            # 生命周期与进程一致，由进程退出统一清理。
            asyncio.create_task(_run())
            await self._started.wait()
            if self._error is not None:
                raise self._error

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "lifespan":
            # 外部服务器（uvicorn 等）会自己跑 lifespan；
            # 标记已启动，首个 HTTP 请求不再重复启动。
            async with self._lock:
                self._started.set()
                self._loop_id = id(asyncio.get_running_loop())
            await self._app(scope, receive, send)
        elif scope["type"] == "http":
            await self._ensure_started()
            await self._app(scope, receive, send)
        else:
            await self._app(scope, receive, send)


def create_app(service: Optional[DocumentService] = None) -> _LazyLifespanASGI:
    settings = Settings()
    mcp_app = mcp.http_app()  # 4.x：内部路由 '/mcp'；2.x 的 streamable_http_app 已移除

    app = FastAPI(title="document-proxy", version="0.1.0", lifespan=mcp_app.lifespan)
    app.state.api_key = settings.api_key
    app.state.service = service or DocumentService(settings)

    set_service(app.state.service)
    app.include_router(router)
    # 上游错误响应保持 {"code": ..., "message": ...} 顶层 envelope
    app.add_exception_handler(HTTPException, envelope_http_exception_handler)
    # REST 路由已注册，Mount('/') 兜底把其余路径（含 /mcp）交给 MCP 应用
    app.mount("/", mcp_app)
    app.add_middleware(BearerAuthMiddleware, api_key=settings.api_key)
    return _LazyLifespanASGI(app)
