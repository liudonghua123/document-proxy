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
        if isinstance(self._records, list) and self._records and isinstance(self._records[0], dict) and "records" in self._records[0]:
            page = self._records.pop(0)
            resp = dict(page)
            resp.setdefault("records", [])
            return resp
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


def test_get_smartsheet_records_multi_page():
    fake = FakeWedoc(
        records=[
            {"has_more": True, "next": 1000, "records": [{"record_id": "r1", "values": {"k": "v1"}}]},
            {"has_more": False, "records": [{"record_id": "r2", "values": {"k": "v2"}}]},
        ]
    )
    svc = make_service(fake)
    assert svc.get_smartsheet_records("d1", "s1") == [{"k": "v1"}, {"k": "v2"}]
    record_calls = [c for c in fake.calls if c[0] == "records"]
    assert len(record_calls) == 2
    assert record_calls[0][3]["offset"] == 0
    assert record_calls[0][3]["limit"] == 1000
    assert record_calls[0][3]["key_type"] == "CELL_VALUE_KEY_TYPE_FIELD_TITLE"
    assert record_calls[1][3]["offset"] == 1000


def test_get_smartsheet_records_stops_on_non_monotonic_next():
    fake = FakeWedoc(
        records=[
            {"has_more": True, "next": 0, "records": [{"record_id": "r1", "values": {"k": "v1"}}]},
        ]
    )
    svc = make_service(fake)
    # next (0) <= 当前 offset (0)：不应死循环，只取一页
    assert svc.get_smartsheet_records("d1", "s1") == [{"k": "v1"}]
    assert len([c for c in fake.calls if c[0] == "records"]) == 1


def test_get_spreadsheet_a1_clamp():
    fake = FakeWedoc(
        props=[{"sheet_id": "s1", "title": "Big", "row_count": 5000, "column_count": 600}],
        range_data={"rows": []},
    )
    svc = make_service(fake)
    result = svc.get_spreadsheet("d1")
    assert result == [{"sheet_id": "s1", "title": "Big", "data": []}]
    assert ("range", "d1", "s1", "A1:J1000") in fake.calls
