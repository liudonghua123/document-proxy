# app/mcp_server.py
"""FastMCP 工具定义（传统 @mcp.tool 装饰器风格）。

service 由 main.create_app 注入。
注意：模块级全局 `_service` 假定每进程只有一个应用实例
（每次 create_app() 会重新绑定它；创建多个 app 会使
MCP 工具指向最后注入的 service）。

工具为同步函数：fastmcp 默认 run_in_thread=True，
在线程池中执行，不会阻塞事件循环（SDK 为阻塞式 http 调用）。
"""
from typing import Any, Dict, List

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from .service import UpstreamError

mcp = FastMCP("document-proxy")
_service = None  # 由 set_service 注入


def set_service(service) -> None:
    global _service
    _service = service


def _call(fn, *args):
    """调用 service；UpstreamError → ToolError。"""
    try:
        return fn(*args)
    except UpstreamError as e:
        raise ToolError(f"upstream error {e.errcode}: {e.errmsg}")


@mcp.tool
def get_doc_info(docid: str) -> Dict[str, Any]:
    """获取文档基础信息（docid、名称、类型、创建/修改时间）。

    对应企微接口：get_doc_base_info。
    """
    return _call(_service.get_doc_info, docid)


@mcp.tool
def get_doc_content(docid: str) -> str:
    """获取企微文档（doc_type=3）内容，返回 Markdown 文本。

    对应企微接口：document/get。
    """
    return _call(_service.get_doc_content, docid)


@mcp.tool
def list_spreadsheet_sheets(docid: str) -> List[Dict[str, Any]]:
    """列出表格文档的工作表属性（sheet_id、标题、行列数）。

    对应企微接口：spreadsheet/get_sheet_properties。
    """
    return _call(_service.get_spreadsheet_sheet_props, docid)


@mcp.tool
def get_spreadsheet_records(docid: str, sheet_id: str) -> Dict[str, Any]:
    """获取表格（doc_type=4）指定工作表记录，紧凑格式 data: [{列名: 值}, ...]。

    对应企微接口：spreadsheet/get_sheet_range_data。
    """
    return _call(_service.get_spreadsheet_records, docid, sheet_id)


@mcp.tool
def list_smartsheet_sheets(docid: str) -> List[Dict[str, Any]]:
    """列出智能表格文档的子表列表（sheet_id、标题、类型）。

    对应企微接口：smartsheet/get_sheet。
    """
    return _call(_service.get_smartsheet_sheets, docid)


@mcp.tool
def get_smartsheet_records(docid: str, sheet_id: str) -> List[Dict[str, Any]]:
    """获取智能表格（doc_type=10）指定子表记录，紧凑格式 data: [{字段名: 值}, ...]。

    对应企微接口：smartsheet/get_records。
    """
    return _call(_service.get_smartsheet_records, docid, sheet_id)
