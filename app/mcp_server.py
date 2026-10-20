# app/mcp_server.py
"""FastMCP 工具定义；service 由 main.create_app 注入。"""
import inspect
from typing import Any, Dict, List

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from .service import UpstreamError

mcp = FastMCP("document-proxy")
_service = None  # 由 set_service 注入


def set_service(service) -> None:
    global _service
    _service = service


def _run(fn, *args):
    import anyio
    return anyio.to_thread.run_sync(fn, *args)


def _tool(fn):
    # fastmcp 4.x 不支持 *args/**kwargs 签名的工具函数，
    # 因此按原参数显式包装（保持 JSON schema 干净）。
    async def wrapper(*args, **kwargs):
        try:
            return await fn(*args, **kwargs)
        except UpstreamError as e:
            raise ToolError(f"upstream error {e.errcode}: {e.errmsg}")
    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    wrapper.__annotations__ = fn.__annotations__
    wrapper.__wrapped__ = fn
    wrapper.__signature__ = inspect.signature(fn)
    return wrapper


@_tool
async def get_doc_info(docid: str) -> Dict[str, Any]:
    """获取文档基础信息（docid、名称、类型、创建/修改时间）。"""
    return await _run(_service.get_doc_info, docid)


@_tool
async def get_doc_content(docid: str) -> str:
    """获取企微文档（doc_type=3）内容，返回 Markdown 文本。"""
    return await _run(_service.get_doc_content, docid)


@_tool
async def list_sheets(docid: str) -> List[Dict[str, Any]]:
    """列出表格/智能表格的工作表属性（sheet_id、标题、行列数）。"""
    return await _run(_service.get_sheet_properties_only, docid)


@_tool
async def get_spreadsheet_data(docid: str) -> List[Dict[str, Any]]:
    """获取表格（doc_type=4）全部工作表数据，紧凑格式 data: [{列名: 值}, ...]。"""
    return await _run(_service.get_spreadsheet, docid)


@_tool
async def get_smartsheet_records(docid: str, sheet_id: str) -> List[Dict[str, Any]]:
    """获取智能表格（doc_type=10）指定子表记录，紧凑格式 data: [{字段名: 值}, ...]。"""
    return await _run(_service.get_smartsheet_records, docid, sheet_id)


mcp.tool(get_doc_info)
mcp.tool(get_doc_content)
mcp.tool(list_sheets)
mcp.tool(get_spreadsheet_data)
mcp.tool(get_smartsheet_records)
