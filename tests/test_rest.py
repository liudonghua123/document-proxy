# tests/test_rest.py
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
