# app/rest.py
"""REST 路由：/api/v1 只读接口。

响应约定：
- 成功：{"code": 0, "message": "ok", "data": ...}
- 上游错误：保持 HTTP 404/502，body 为 {"code": <errcode>, "message": <errmsg>}
"""
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.security.http import HTTPAuthorizationCredentials, HTTPBearer

from .auth import verify_bearer
from .service import _NOT_FOUND_CODES, UpstreamError

_bearer = HTTPBearer(auto_error=False)
router = APIRouter(prefix="/api/v1")


def envelope_http_exception_handler(request: Request, exc: HTTPException):
    """把 _http_error 的 detail 重写为顶层 {"code": ..., "message": ...} body。

    仅影响带 code/message dict detail 的异常（上游错误映射）；
    其他 HTTPException（如 401/404 not-found）保持默认 {"detail": ...} 格式。
    在 main.create_app 中通过 app.add_exception_handler 注册。
    """
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail and "message" in detail:
        return JSONResponse(
            status_code=exc.status_code,
            content=detail,
            headers=getattr(exc, "headers", None),
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": detail},
        headers=getattr(exc, "headers", None),
    )


def require_auth(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> None:
    verify_bearer(credentials, request.app.state.api_key)


def _http_error(e: UpstreamError) -> HTTPException:
    code = (
        status.HTTP_404_NOT_FOUND
        if e.errcode in _NOT_FOUND_CODES
        else status.HTTP_502_BAD_GATEWAY
    )
    return HTTPException(
        status_code=code,
        detail={"code": e.errcode, "message": e.errmsg},
    )


@router.get("/docs/{docid}", dependencies=[Depends(require_auth)])
def get_doc_content(docid: str, request: Request) -> Dict[str, Any]:
    try:
        return {
            "code": 0,
            "message": "ok",
            "data": request.app.state.service.get_doc_content(docid),
        }
    except UpstreamError as e:
        raise _http_error(e)


@router.get("/docs/{docid}/info", dependencies=[Depends(require_auth)])
def get_doc_info(docid: str, request: Request) -> Dict[str, Any]:
    try:
        return {
            "code": 0,
            "message": "ok",
            "data": request.app.state.service.get_doc_info(docid),
        }
    except UpstreamError as e:
        raise _http_error(e)


@router.get("/spreadsheet/{docid}", dependencies=[Depends(require_auth)])
def get_spreadsheet(docid: str, request: Request) -> Dict[str, Any]:
    try:
        return {
            "code": 0,
            "message": "ok",
            "data": request.app.state.service.get_spreadsheet(docid),
        }
    except UpstreamError as e:
        raise _http_error(e)


@router.get(
    "/smartsheet/{docid}/{sheet_id}/records",
    dependencies=[Depends(require_auth)],
)
def get_smartsheet_records(docid: str, sheet_id: str, request: Request) -> Dict[str, Any]:
    try:
        return {
            "code": 0,
            "message": "ok",
            "data": request.app.state.service.get_smartsheet_records(docid, sheet_id),
        }
    except UpstreamError as e:
        raise _http_error(e)
