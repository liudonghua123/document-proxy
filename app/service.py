# app/service.py
"""DocumentService：封装 weixin-work-reborn 的只读文档操作。"""
from typing import Any, Dict, List

from weixin_work_reborn import WeChatWorkClient

from .config import Settings
from .formatting import grid_to_records, node_to_markdown, records_to_compact

# 上游 errcode → HTTP 404 的"文档不存在"错误码
_NOT_FOUND_CODES = {1934008}


class UpstreamError(Exception):
    """企微上游返回 errcode != 0。"""

    def __init__(self, errcode: int, errmsg: str) -> None:
        self.errcode = errcode
        self.errmsg = errmsg
        super().__init__(f"wedoc upstream error {errcode}: {errmsg}")


class DocumentService:
    def __init__(self, settings: Settings) -> None:
        self._client = WeChatWorkClient(
            config=_SdkConfigAdapter(settings),
            token_cache_size=8,
            token_cache_ttl=7000,
        )
        self._wedoc_api = None

    @property
    def _wedoc(self):
        if self._wedoc_api is None:
            self._wedoc_api = self._client.wedoc_api
        return self._wedoc_api

    @_wedoc.setter
    def _wedoc(self, value):
        self._wedoc_api = value

    # ---- 内部 ----

    def _check(self, resp: Dict[str, Any]) -> None:
        errcode = resp.get("errcode", 0)
        if errcode != 0:
            raise UpstreamError(errcode, resp.get("errmsg", "unknown"))

    # ---- 对外只读操作 ----

    def get_doc_info(self, docid: str) -> Dict[str, Any]:
        resp = self._wedoc.get_document_base_info(docid=docid)
        self._check(resp)
        return resp.get("doc_base_info", {})

    def get_doc_content(self, docid: str) -> str:
        resp = self._wedoc.get_document_data(docid=docid)
        self._check(resp)
        return node_to_markdown(resp.get("document", {}))

    def get_sheet_properties_only(self, docid: str) -> List[Dict[str, Any]]:
        props_resp = self._wedoc.get_sheet_properties(docid=docid)
        self._check(props_resp)
        return props_resp.get("properties", [])

    def get_spreadsheet(self, docid: str) -> List[Dict[str, Any]]:
        props_resp = self._wedoc.get_sheet_properties(docid=docid)
        self._check(props_resp)
        result = []
        for prop in props_resp.get("properties", []):
            sheet_id = prop["sheet_id"]
            row_count = prop.get("row_count", 0)
            col_count = prop.get("column_count", 0)
            if row_count <= 0 or col_count <= 0:
                result.append({"sheet_id": sheet_id, "title": prop.get("title", ""), "data": []})
                continue
            # A1 表示法，上限保护：行<=1000、列<=200、单元格<=10000
            n_rows = min(row_count, 1000)
            n_cols = min(col_count, 200, max(1, 10000 // n_rows))
            col_letter = _col_name(n_cols)
            data_resp = self._wedoc.get_sheet_range_data(
                docid=docid, sheet_id=sheet_id, range_str=f"A1:{col_letter}{n_rows}"
            )
            self._check(data_resp)
            rows = data_resp.get("data", {}).get("result", {}).get("rows", [])
            result.append(
                {
                    "sheet_id": sheet_id,
                    "title": prop.get("title", ""),
                    "data": grid_to_records(rows),
                }
            )
        return result

    def get_smartsheet_records(self, docid: str, sheet_id: str) -> List[Dict[str, Any]]:
        records: List[Dict[str, Any]] = []
        offset = 0
        while True:
            resp = self._wedoc.query_records(
                docid=docid, sheet_id=sheet_id,
                key_type="CELL_VALUE_KEY_TYPE_FIELD_TITLE",
                offset=offset, limit=1000,
            )
            self._check(resp)
            records.extend(resp.get("records", []))
            if not resp.get("has_more"):
                break
            offset = resp.get("next", offset + 1000)
        return records_to_compact(records)


def _col_name(n: int) -> str:
    """1 → A, 26 → Z, 27 → AA。"""
    name = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        name = chr(65 + rem) + name
    return name


class _SdkConfigAdapter:
    """把我们的 Settings 适配成 SDK Config 所需的最小属性集合。"""

    def __init__(self, settings: Settings) -> None:
        self.base_url = settings.base_url
        self.corp_id = settings.corp_id
        self.app_secret = settings.app_secret
        self.doc_secret = settings.doc_secret
        self.contacts_sync_secret = settings.doc_secret
