# tests/test_rest.py
import json

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


class StubService:
    def get_doc_info(self, docid):
        return {"docid": docid, "doc_name": "n", "doc_type": 3}

    def get_doc_content(self, docid):
        return "# hi\n"

    def get_spreadsheet(self, docid):
        return [{"sheet_id": "s1", "title": "S", "data": [{"q": "1"}]}]

    def get_smartsheet_records(self, docid, sheet_id):
        return [{"k": "v"}]


HEADERS = {"Authorization": "Bearer k1"}


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("API_KEY", "k1")
    monkeypatch.setenv("WEIXIN_WORK_CORP_ID", "corp")
    monkeypatch.setenv("WEIXIN_WORK_APP_SECRET", "s")
    monkeypatch.setenv("WEIXIN_WORK_DOC_SECRET", "ds")
    from app import main
    return main.create_app(service=StubService())


async def test_doc_content_ok(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/api/v1/docs/d1", headers=HEADERS)
    assert r.status_code == 200
    assert r.json() == {"data": "# hi\n"}


async def test_unauthorized(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/api/v1/docs/d1", headers={"Authorization": "Bearer bad"})
        assert r.status_code == 401
        r = await c.get("/api/v1/docs/d1")
        assert r.status_code == 401


async def test_spreadsheet_compact(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/api/v1/sheets/d1", headers=HEADERS)
    assert r.status_code == 200
    assert r.json() == {"data": [{"sheet_id": "s1", "title": "S", "data": [{"q": "1"}]}]}


async def test_upstream_error_maps_404(app):
    from app.service import UpstreamError

    class NotFoundService(StubService):
        def get_doc_content(self, docid):
            raise UpstreamError(1934008, "doc not found")

    from app import main
    app404 = main.create_app(service=NotFoundService())
    async with AsyncClient(transport=ASGITransport(app=app404), base_url="http://t") as c:
        r = await c.get("/api/v1/docs/d1", headers=HEADERS)
    assert r.status_code == 404


async def test_doc_info_ok(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/api/v1/docs/d1/info", headers=HEADERS)
    assert r.status_code == 200
    assert r.json() == {"data": {"docid": "d1", "doc_name": "n", "doc_type": 3}}


async def test_smartsheet_records_ok(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/api/v1/smartsheets/d1/s9/records", headers=HEADERS)
    assert r.status_code == 200
    assert r.json() == {"data": [{"k": "v"}]}


async def test_upstream_error_maps_502(app):
    from app.service import UpstreamError

    class BoomService(StubService):
        def get_doc_content(self, docid):
            raise UpstreamError(50001, "boom")

    from app import main
    app502 = main.create_app(service=BoomService())
    async with AsyncClient(transport=ASGITransport(app=app502), base_url="http://t") as c:
        r = await c.get("/api/v1/docs/d1", headers=HEADERS)
    assert r.status_code == 502
    assert r.json()["detail"]["errcode"] == 50001
    assert r.json()["detail"]["errmsg"] == "boom"


MCP_ACCEPT = {"Accept": "application/json, text/event-stream"}
INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-03-26",
                   "capabilities": {},
                   "clientInfo": {"name": "t", "version": "0"}}}


def _parse_jsonrpc(text):
    """防御性解析：响应可能是 SSE（data: 行）或纯 JSON。"""
    if text.lstrip().startswith("{"):
        return json.loads(text)
    for line in text.splitlines():
        if line.startswith("data:"):
            return json.loads(line[len("data:"):].strip())
    raise AssertionError(f"unparseable MCP response: {text!r}")


async def _init_session(client):
    r = await client.post("/mcp", json=INIT, headers={**HEADERS, **MCP_ACCEPT})
    assert r.status_code == 200
    session_id = r.headers.get("mcp-session-id")
    return session_id


async def test_mcp_tools_roundtrip(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        session_id = await _init_session(c)
        h = {**HEADERS, **MCP_ACCEPT, "mcp-session-id": session_id}

        r = await c.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, headers=h)
        assert r.status_code == 200
        payload = _parse_jsonrpc(r.text)
        names = {t["name"] for t in payload["result"]["tools"]}
        assert {"get_doc_info", "get_doc_content", "list_sheets",
                "get_spreadsheet_data", "get_smartsheet_records"} <= names

        r = await c.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                  "params": {"name": "get_doc_content", "arguments": {"docid": "d1"}}},
            headers=h,
        )
        assert r.status_code == 200
        payload = _parse_jsonrpc(r.text)
        assert payload["result"]["isError"] is False
        texts = [b["text"] for b in payload["result"]["content"] if b.get("type") == "text"]
        assert any("# hi" in t for t in texts)


async def test_mcp_tool_error_is_error_result(app):
    from app.service import UpstreamError

    class NotFoundService(StubService):
        def get_doc_content(self, docid):
            raise UpstreamError(1934008, "doc not found")

    from app import main
    app404 = main.create_app(service=NotFoundService())
    async with AsyncClient(transport=ASGITransport(app=app404), base_url="http://t") as c:
        session_id = await _init_session(c)
        h = {**HEADERS, **MCP_ACCEPT, "mcp-session-id": session_id}

        r = await c.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                  "params": {"name": "get_doc_content", "arguments": {"docid": "d1"}}},
            headers=h,
        )
        assert r.status_code == 200
        payload = _parse_jsonrpc(r.text)
        # UpstreamError 应被映射为 ToolError → isError=true 的错误结果
        assert payload["result"]["isError"] is True
        texts = " ".join(
            b.get("text", "") for b in payload["result"]["content"] if b.get("type") == "text"
        )
        assert "1934008" in texts and "doc not found" in texts


async def test_mcp_endpoint_protected_and_alive(app):
    # 未带 key → 401
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
        assert r.status_code == 401
    # 带 key → 非 401（MCP 会话建立/协议协商响应）
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize",
                  "params": {"protocolVersion": "2025-03-26",
                             "capabilities": {},
                             "clientInfo": {"name": "t", "version": "0"}}},
            headers={**HEADERS, "Accept": "application/json, text/event-stream"},
        )
        assert r.status_code != 401
