# tests/test_service.py
import pytest

from app.service import DocumentService, UpstreamError


class FakeWedoc:
    """替身：按脚本返回或抛错。"""

    def __init__(self, doc_data=None, props=None, range_data=None, records=None):
        self._doc_data = doc_data
        self._props = props
        self._range_data = range_data
        self._records = records
        self.calls = []

    def get_document_base_info(self, docid):
        self.calls.append(("info", docid))
        return {"errcode": 0, "doc_base_info": {"docid": docid, "doc_name": "n", "doc_type": 3}}

    def get_document_data(self, docid):
        self.calls.append(("doc", docid))
        if self._doc_data is None:
            return {"errcode": 1934008, "errmsg": "not found"}
        return {"errcode": 0, "document": self._doc_data}

    def get_sheet_properties(self, docid):
        self.calls.append(("props", docid))
        return {"errcode": 0, "properties": self._props or []}

    def get_sheet_range_data(self, docid, sheet_id, range_str):
        self.calls.append(("range", docid, sheet_id, range_str))
        return {"errcode": 0, "data": {"result": self._range_data}}

    def query_records(self, docid, sheet_id, **kwargs):
        self.calls.append(("records", docid, sheet_id, kwargs))
        return {"errcode": 0, "records": self._records or [], "total": len(self._records or [])}


def make_service(fake):
    svc = DocumentService.__new__(DocumentService)
    svc._wedoc = fake
    return svc


def test_get_doc_content_markdown():
    fake = FakeWedoc(doc_data={"type": 1, "text_run": {"content": "hi"}})
    svc = make_service(fake)
    assert svc.get_doc_content("d1") == "hi\n"


def test_upstream_error_raises():
    fake = FakeWedoc(doc_data=None)  # errcode 1934008
    svc = make_service(fake)
    with pytest.raises(UpstreamError) as ei:
        svc.get_doc_content("d1")
    assert ei.value.errcode == 1934008
    assert "not found" in str(ei.value)


def test_get_spreadsheet_all_sheets():
    fake = FakeWedoc(
        props=[{"sheet_id": "s1", "title": "Sheet1", "row_count": 2, "column_count": 2}],
        range_data={
            "rows": [
                {"values": [{"cell_value": {"text_piece": {"text": "question"}}},
                            {"cell_value": {"text_piece": {"text": "answer"}}}]},
                {"values": [{"cell_value": {"text_piece": {"text": "Q"}}},
                            {"cell_value": {"text_piece": {"text": "A"}}}]},
            ]
        },
    )
    svc = make_service(fake)
    result = svc.get_spreadsheet("d1")
    assert result == [{"sheet_id": "s1", "title": "Sheet1", "data": [{"question": "Q", "answer": "A"}]}]


def test_get_smartsheet_records():
    fake = FakeWedoc(records=[{"record_id": "r1", "values": {"k": "v"}}])
    svc = make_service(fake)
    assert svc.get_smartsheet_records("d1", "s1") == [{"k": "v"}]


def test_get_sheet_properties_only():
    fake = FakeWedoc(props=[{"sheet_id": "s1", "title": "T", "row_count": 3, "column_count": 2}])
    svc = make_service(fake)
    assert svc.get_sheet_properties_only("d1") == [
        {"sheet_id": "s1", "title": "T", "row_count": 3, "column_count": 2}
    ]
