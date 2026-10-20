# app/formatting.py
"""纯函数：把企微上游数据转成对 AI 友好的紧凑格式。"""
from typing import Any, Dict, List

# 企微文档节点类型 → Markdown 前缀（type 含义见官方文档 Node 结构；测试约定 type 3 = H1）
_HEADING_PREFIX = {3: "# ", 4: "## ", 5: "### ", 6: "#### ", 7: "##### ", 8: "###### "}
_LIST_PREFIX = {11: "- ", 12: "1. ", 13: "1. "}


def cell_to_plain(cell: Any) -> str:
    """单元格 cell_value → 纯文本。"""
    if not cell:
        return ""
    if "text_piece" in cell:
        return str(cell["text_piece"].get("text", ""))
    if "number" in cell:
        num = cell["number"]
        return str(int(num)) if isinstance(num, float) and num.is_integer() else str(num)
    return ""


def grid_to_records(rows: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """表格 GridData.rows → 行→对象映射。首行非空时作表头，否则用 col_1/col_2/..."""
    if not rows:
        return []
    matrix = [
        [cell_to_plain(c.get("cell_value")) for c in r.get("values", [])]
        for r in rows
    ]
    header, body = matrix[0], matrix[1:]
    if not any(header):
        header = [f"col_{i + 1}" for i in range(len(header))]
    return [dict(zip(header, row)) for row in body]


def records_to_compact(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """智能表格 records（key_type=FIELD_TITLE）→ 只保留 values 的紧凑列表。"""
    return [r.get("values", {}) for r in records]


def node_to_markdown(node: Dict[str, Any]) -> str:
    """递归把企微文档 Node 树扁平化为 Markdown 文本。"""
    if not node:
        return ""
    parts: List[str] = []
    node_type = node.get("type", 0)
    text = node.get("text_run", {}).get("content", "")
    if text:
        prefix = _HEADING_PREFIX.get(node_type, "") or _LIST_PREFIX.get(node_type, "")
        parts.append(prefix + text + "\n")
    for child in node.get("children", []) or []:
        parts.append(node_to_markdown(child))
    return "".join(p for p in parts if p)
