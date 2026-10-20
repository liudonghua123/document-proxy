# app/rest.py
"""REST 路由：/api/v1 只读接口。"""
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security.http import HTTPAuthorizationCredentials, HTTPBearer

from .auth import verify_bearer
from .service import _NOT_FOUND_CODES, UpstreamError

_bearer = HTTPBearer(auto_error=False)
router = APIRouter(prefix="/api/v1")


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
    return HTTPException(status_code=code, detail={"errcode": e.errcode, "errmsg": e.errmsg})


@router.get("/docs/{docid}", dependencies=[Depends(require_auth)])
def get_doc_content(docid: str, request: Request) -> Dict[str, Any]:
    try:
        return {"data": request.app.state.service.get_doc_content(docid)}
    except UpstreamError as e:
        raise _http_error(e)


@router.get("/docs/{docid}/info", dependencies=[Depends(require_auth)])
def get_doc_info(docid: str, request: Request) -> Dict[str, Any]:
    try:
        return {"data": request.app.state.service.get_doc_info(docid)}
    except UpstreamError as e:
        raise _http_error(e)


@router.get("/sheets/{docid}", dependencies=[Depends(require_auth)])
def get_spreadsheet(docid: str, request: Request) -> Dict[str, Any]:
    try:
        return {"data": request.app.state.service.get_spreadsheet(docid)}
    except UpstreamError as e:
        raise _http_error(e)


@router.get("/smartsheets/{docid}/{sheet_id}/records", dependencies=[Depends(require_auth)])
def get_smartsheet_records(docid: str, sheet_id: str, request: Request) -> Dict[str, Any]:
    try:
        return {"data": request.app.state.service.get_smartsheet_records(docid, sheet_id)}
    except UpstreamError as e:
        raise _http_error(e)
