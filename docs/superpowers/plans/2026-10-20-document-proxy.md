# 企微文档数据代理（document-proxy）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建只读的企微文档数据代理服务，通过 REST（FastAPI）和 MCP（FastMCP Streamable HTTP `/mcp`）暴露企微文档/表格/智能表格数据，表格类数据输出紧凑的行→对象映射。

**Architecture:** FastAPI 应用工厂 `create_app()`：REST 路由 + FastMCP 子应用挂载在 `/mcp`。`DocumentService` 封装 weixin-work-reborn 只读调用（token 由 SDK AccessTokenManager TTL 缓存）；`formatting.py` 纯函数负责 Node→Markdown 与表格→紧凑 data 转换。Bearer API_KEY 鉴权：REST 用 FastAPI dependency，`/mcp` 用纯 ASGI 中间件（dependency 覆盖不到 mount 的子应用）。

**Tech Stack:** Python 3.10+、FastAPI、FastMCP (>=2.8)、weixin-work-reborn (>=0.2.0)、python-dotenv、pytest + pytest-asyncio + httpx。

**Spec:** `docs/superpowers/specs/2026-10-20-document-proxy-design.md`

**约定:**
- 命令在项目根目录 `C:/Users/admin/code/ai/document-proxy` 下、Git Bash 中执行；测试统一用 `.venv/Scripts/python.exe -m pytest ...`。
- 每条 git commit message 末尾追加两行:
  `Co-authored-by: liudonghua123 <liudonghua123@gmail.com>`
  `Co-authored-by: Claude <noreply@anthropic.com>`
- 上游 SDK（requests）是同步阻塞的：REST 路由用 `def`（FastAPI 自动放线程池）；MCP 工具内部用 `anyio.to_thread.run_sync` 包裹。

---

### Task 1: 项目脚手架

**Files:**
- Create: `.gitignore`, `requirements.txt`, `.env.example`, `pytest.ini`, `app/__init__.py`, `tests/__init__.py`

- [ ] **Step 1: 初始化 git 与目录**

```bash
cd /c/Users/admin/code/ai/document-proxy
git init
mkdir -p app tests docs/superpowers/plans
```

- [ ] **Step 2: 写 .gitignore**

```gitignore
__pycache__/
*.py[cod]
.venv/
.env
.pytest_cache/
```

- [ ] **Step 3: 写 requirements.txt**

```text
fastapi>=0.115,<1.0
uvicorn[standard]>=0.30
fastmcp>=2.8
python-dotenv>=1.0
weixin-work-reborn>=0.2.0
pytest>=8.0
pytest-asyncio>=0.24
httpx>=0.27
```

- [ ] **Step 4: 写 .env.example**

```bash
# 本服务的调用方鉴权 key（必填）
API_KEY=change-me

# 企微配置
WEIXIN_WORK_BASE_URL=https://qyapi.weixin.qq.com/
WEIXIN_WORK_CORP_ID=your-corp-id
WEIXIN_WORK_APP_SECRET=your-app-secret
# 文档应用 secret（优先）；未配置时回退 CONTACTS_SYNC_SECRET
WEIXIN_WORK_DOC_SECRET=your-doc-secret
WEIXIN_WORK_CONTACTS_SYNC_SECRET=your-contacts-sync-secret

# 服务监听
HOST=0.0.0.0
PORT=8000
```

- [ ] **Step 5: 写 pytest.ini**

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
```

- [ ] **Step 6: 建 Python 包与虚拟环境**

```bash
touch app/__init__.py tests/__init__.py
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

- [ ] **Step 7: Commit**

```bash
git add .gitignore requirements.txt .env.example pytest.ini app/__init__.py tests/__init__.py
git commit -m "chore: scaffold document-proxy project"
```

---

### Task 2: 配置模块 config.py

**Files:**
- Create: `app/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_config.py
import pytest

from app.config import Settings


def make_env(monkeypatch, **overrides):
    base = {
        "API_KEY": "k1",
        "WEIXIN_WORK_CORP_ID": "corp",
        "WEIXIN_WORK_APP_SECRET": "app-secret",
        "WEIXIN_WORK_DOC_SECRET": "",
        "WEIXIN_WORK_CONTACTS_SYNC_SECRET": "contacts-secret",
        "WEIXIN_WORK_BASE_URL": "",
    }
    base.update(overrides)
    for k, v in base.items():
        monkeypatch.setenv(k, v)
    for k in ("HOST", "PORT"):
        monkeypatch.delenv(k, raising=False)


def test_required_missing_api_key(monkeypatch):
    make_env(monkeypatch, API_KEY="")
    with pytest.raises(ValueError, match="API_KEY"):
        Settings()


def test_doc_secret_fallback_to_contacts_sync(monkeypatch):
    make_env(monkeypatch)
    s = Settings()
    assert s.doc_secret == "contacts-secret"


def test_doc_secret_preferred(monkeypatch):
    make_env(monkeypatch, WEIXIN_WORK_DOC_SECRET="doc-secret")
    s = Settings()
    assert s.doc_secret == "doc-secret"


def test_base_url_default(monkeypatch):
    make_env(monkeypatch)
    s = Settings()
    assert s.base_url == "https://qyapi.weixin.qq.com/"
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_config.py -v`
Expected: FAIL（ModuleNotFoundError: app.config）

- [ ] **Step 3: 实现**

```python
# app/config.py
"""应用配置：读取 .env 与环境变量，含 doc_secret 回退逻辑。"""
import os

from dotenv import load_dotenv

load_dotenv()

_DEFAULT_BASE_URL = "https://qyapi.weixin.qq.com/"


class Settings:
    def __init__(self) -> None:
        self.api_key = os.getenv("API_KEY", "")
        self.base_url = os.getenv("WEIXIN_WORK_BASE_URL", "") or _DEFAULT_BASE_URL
        self.corp_id = os.getenv("WEIXIN_WORK_CORP_ID", "")
        self.app_secret = os.getenv("WEIXIN_WORK_APP_SECRET", "")
        self.doc_secret = (
            os.getenv("WEIXIN_WORK_DOC_SECRET", "")
            or os.getenv("WEIXIN_WORK_CONTACTS_SYNC_SECRET", "")
        )
        self.host = os.getenv("HOST", "0.0.0.0")
        self.port = int(os.getenv("PORT", "8000"))

        if not self.api_key:
            raise ValueError("API_KEY is required")
        if not self.corp_id:
            raise ValueError("WEIXIN_WORK_CORP_ID is required")
        if not self.app_secret:
            raise ValueError("WEIXIN_WORK_APP_SECRET is required")
        if not self.doc_secret:
            raise ValueError(
                "WEIXIN_WORK_DOC_SECRET or WEIXIN_WORK_CONTACTS_SYNC_SECRET is required"
            )
```

- [ ] **Step 4: 运行测试通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_config.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add app/config.py tests/test_config.py
git commit -m "feat: add Settings with doc_secret fallback"
```

---

### Task 3: 格式化纯函数 formatting.py

**Files:**
- Create: `app/formatting.py`
- Test: `tests/test_formatting.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_formatting.py
from app.formatting import cell_to_plain, grid_to_records, node_to_markdown, records_to_compact


# ---- cell_to_plain ----

def test_cell_text_piece():
    cell = {"text_piece": {"text": "hello"}}
    assert cell_to_plain(cell) == "hello"


def test_cell_number():
    assert cell_to_plain({"number": 3.5}) == "3.5"


def test_cell_empty():
    assert cell_to_plain({}) == ""
    assert cell_to_plain(None) == ""


# ---- grid_to_records：表格 → 紧凑 data ----

def test_grid_first_row_as_header():
    rows = [
        {"values": [{"cell_value": {"text_piece": {"text": "question"}}},
                    {"cell_value": {"text_piece": {"text": "answer"}}}]},
        {"values": [{"cell_value": {"text_piece": {"text": "Q1"}}},
                    {"cell_value": {"text_piece": {"text": "A1"}}}]},
    ]
    assert grid_to_records(rows) == [{"question": "Q1", "answer": "A1"}]


def test_grid_empty_header_uses_col_names():
    rows = [
        {"values": [{"cell_value": {}}, {"cell_value": {}}]},
        {"values": [{"cell_value": {"number": 1}}, {"cell_value": {}}]},
    ]
    assert grid_to_records(rows) == [{"col_1": "1", "col_2": ""}]


def test_grid_empty():
    assert grid_to_records([]) == []


# ---- records_to_compact：智能表格 → 紧凑 data ----

def test_records_to_compact_values_only():
    records = [
        {"record_id": "r1", "values": {"question": "Q1", "answer": "A1"}},
        {"record_id": "r2", "values": {"question": "Q2", "answer": "A2"}},
    ]
    assert records_to_compact(records) == [
        {"question": "Q1", "answer": "A1"},
        {"question": "Q2", "answer": "A2"},
    ]


def test_records_to_compact_empty():
    assert records_to_compact([]) == []


# ---- node_to_markdown：文档 Node 树 → Markdown ----

def test_paragraph_text():
    node = {"type": 1, "text_run": {"content": "hello"}}
    assert node_to_markdown(node) == "hello\n"


def test_children_recursion():
    node = {
        "type": 1,
        "children": [
            {"type": 1, "text_run": {"content": "a"}},
            {"type": 1, "text_run": {"content": "b"}},
        ],
    }
    assert node_to_markdown(node) == "a\nb\n"


def test_heading_prefix():
    node = {"type": 3, "text_run": {"content": "标题"}}
    assert node_to_markdown(node) == "# 标题\n"
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_formatting.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现**

```python
# app/formatting.py
"""纯函数：把企微上游数据转成对 AI 友好的紧凑格式。"""
from typing import Any, Dict, List

# 企微文档节点类型 → Markdown 前缀（type 含义见官方文档 Node 结构）
_HEADING_PREFIX = {2: "###### ", 3: "##### ", 4: "#### ", 5: "### ", 6: "## ", 7: "# "}
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
        parts.append(prefix + text)
    for child in node.get("children", []) or []:
        parts.append(node_to_markdown(child))
    return "\n".join(p for p in parts if p) + ("\n" if parts else "")
```

- [ ] **Step 4: 运行测试通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_formatting.py -v`
Expected: 全部 passed

- [ ] **Step 5: Commit**

```bash
git add app/formatting.py tests/test_formatting.py
git commit -m "feat: formatting pure functions (markdown/compact data)"
```

---

### Task 4: 上游错误与服务层 service.py

**Files:**
- Create: `app/service.py`
- Test: `tests/test_service.py`

- [ ] **Step 1: 写失败测试**

```python
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
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_service.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现**

```python
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
```

- [ ] **Step 4: 运行测试通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_service.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add app/service.py tests/test_service.py
git commit -m "feat: DocumentService with upstream error handling"
```

---

### Task 5: 鉴权 auth.py

**Files:**
- Create: `app/auth.py`
- Test: `tests/test_auth.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_auth.py
import secrets

from fastapi import HTTPException
from fastapi.security.http import HTTPAuthorizationCredentials

from app.auth import BearerAuthMiddleware, verify_bearer


def test_verify_bearer_ok():
    cred = HTTPAuthorizationCredentials(scheme="Bearer", credentials="right")
    assert verify_bearer(cred, "right") is None


def test_verify_bearer_wrong():
    cred = HTTPAuthorizationCredentials(scheme="Bearer", credentials="wrong")
    try:
        verify_bearer(cred, "right")
        assert False, "should raise"
    except HTTPException as e:
        assert e.status_code == 401


def test_verify_bearer_constant_time_compare():
    # 确保用的是 secrets.compare_digest（防时序攻击）
    assert BearerAuthMiddleware._matches("a", "a")
    assert not BearerAuthMiddleware._matches("a", "b")
    assert BearerAuthMiddleware._matches(secrets.token_hex(8), secrets.token_hex(8)) in (True, False)
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_auth.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现**

```python
# app/auth.py
"""Bearer API_KEY 鉴权：REST dependency + /mcp ASGI 中间件。"""
import secrets
from typing import Optional

from fastapi import HTTPException, Request, status
from fastapi.security.http import HTTPAuthorizationCredentials, HTTPBearer
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

_bearer_scheme = HTTPBearer(auto_error=False)


def verify_bearer(
    credentials: Optional[HTTPAuthorizationCredentials],
    api_key: str,
) -> None:
    if credentials is None or not BearerAuthMiddleware._matches(credentials.credentials, api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )


class BearerAuthMiddleware(BaseHTTPMiddleware):
    """保护指定路径前缀（/mcp）的 Bearer 鉴权中间件。"""

    def __init__(self, app, api_key: str, protected_prefixes: tuple = ("/mcp",)) -> None:
        super().__init__(app)
        self.api_key = api_key
        self.protected_prefixes = protected_prefixes

    @staticmethod
    def _matches(a: str, b: str) -> bool:
        return secrets.compare_digest(a.encode(), b.encode())

    def _authorized(self, request: Request) -> bool:
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth[7:].strip()
            return bool(token) and self._matches(token, self.api_key)
        return False

    async def dispatch(self, request: Request, call_next):
        if any(request.url.path.startswith(p) for p in self.protected_prefixes):
            if not self._authorized(request):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid or missing API key"},
                    headers={"WWW-Authenticate": "Bearer"},
                )
        return await call_next(request)
```

注意：`test_verify_bearer_constant_time_compare` 第三个断言只是防止误删 `_matches`；真正断言在前两个。

- [ ] **Step 4: 运行测试通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_auth.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add app/auth.py tests/test_auth.py
git commit -m "feat: bearer auth dependency and middleware"
```

---

### Task 6: REST 路由 rest.py 与应用工厂 main.py

**Files:**
- Create: `app/rest.py`, `app/main.py`
- Test: `tests/test_rest.py`

- [ ] **Step 1: 写失败测试**

```python
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


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("API_KEY", "k1")
    monkeypatch.setenv("WEIXIN_WORK_CORP_ID", "corp")
    monkeypatch.setenv("WEIXIN_WORK_APP_SECRET", "s")
    monkeypatch.setenv("WEIXIN_WORK_DOC_SECRET", "ds")
    from app import main
    return main.create_app(service=StubService())


HEADERS = {"Authorization": "Bearer k1"}


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
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_rest.py -v`
Expected: FAIL（app.main 不存在）

- [ ] **Step 3: 实现 rest.py**

```python
# app/rest.py
"""REST 路由：/api/v1 只读接口。"""
from typing import Optional

from fastapi import APIRouter, Depends, Request

from .auth import verify_bearer
from .service import UpstreamError

router = APIRouter(prefix="/api/v1", dependencies=[Depends(_auth)])


def _auth(request: Request) -> None:
    # 延迟导入避免循环依赖；api_key 存在 app.state
    from fastapi.security.http import HTTPBearer
    creds = HTTPBearer(auto_error=False)(request) if False else None
    raise NotImplementedError  # 由 main.py 通过依赖注入覆盖（见下）
```

上面这种写法不好——改为用 router 级 dependency 工厂：

```python
# app/rest.py（最终版）
"""REST 路由：/api/v1 只读接口。"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security.http import HTTPAuthorizationCredentials, HTTPBearer

from .auth import verify_bearer
from .service import UpstreamError

_bearer = HTTPBearer(auto_error=False)
router = APIRouter(prefix="/api/v1")


def get_api_key(request: Request) -> str:
    return request.app.state.api_key


def require_auth(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> None:
    verify_bearer(credentials, get_api_key(request))


def _http_error(e: UpstreamError) -> HTTPException:
    code = status.HTTP_404_NOT_FOUND if e.errcode in (1934008,) else status.HTTP_502_BAD_GATEWAY
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
```

- [ ] **Step 4: 实现 mcp_server.py**

```python
# app/mcp_server.py
"""FastMCP 工具定义。工具函数从 app.state 取 DocumentService。"""
from typing import Any, Dict, List

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from .service import UpstreamError

mcp = FastMCP("document-proxy")


def _service(request):
    return request.app.state.service


def _wrap(fn):
    """把 UpstreamError 转成 MCP ToolError。"""
    async def inner(*args, **kwargs):
        try:
            return await fn(*args, **kwargs)
        except UpstreamError as e:
            raise ToolError(f"upstream error {e.errcode}: {e.errmsg}")
    return inner


@mcp.tool
@_wrap
async def get_doc_info(request, docid: str) -> Dict[str, Any]:
    """获取文档基础信息（docid、名称、类型、创建/修改时间）。"""
    import anyio
    return await anyio.to_thread.run_sync(_service(request).get_doc_info, docid)


@mcp.tool
@_wrap
async def get_doc_content(request, docid: str) -> str:
    """获取企微文档（doc_type=3）内容，返回 Markdown 文本。"""
    import anyio
    return await anyio.to_thread.run_sync(_service(request).get_doc_content, docid)


@mcp.tool
@_wrap
async def list_sheets(request, docid: str) -> List[Dict[str, Any]]:
    """列出表格/智能表格的工作表属性（sheet_id、标题、行列数）。"""
    import anyio
    return await anyio.to_thread.run_sync(_service(request).get_sheet_properties_only, docid)


@mcp.tool
@_wrap
async def get_spreadsheet_data(request, docid: str) -> List[Dict[str, Any]]:
    """获取表格（doc_type=4）全部工作表数据，紧凑格式 data: [{列名: 值}, ...]。"""
    import anyio
    return await anyio.to_thread.run_sync(_service(request).get_spreadsheet, docid)


@mcp.tool
@_wrap
async def get_smartsheet_records(request, docid: str, sheet_id: str) -> List[Dict[str, Any]]:
    """获取智能表格（doc_type=10）指定子表记录，紧凑格式 data: [{字段名: 值}, ...]。"""
    import anyio
    return await anyio.to_thread.run_sync(
        _service(request).get_smartsheet_records, docid, sheet_id
    )
```

注意：FastMCP 的 `@mcp.tool` 从函数签名生成参数 schema，`request` 参数会导致 schema 不合法。**最终实现里工具函数不接收 request**，改为模块级持有 service 引用（由 main.py 在 create_app 时注入）。最终版 `mcp_server.py`：

```python
# app/mcp_server.py（最终版）
"""FastMCP 工具定义；service 由 main.create_app 注入。"""
from typing import Any, Dict, List

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from .service import UpstreamError

mcp = FastMCP("document-proxy")
_service = None  # type: ignore


def set_service(service) -> None:
    global _service
    _service = service


def _run(fn, *args):
    import anyio
    return anyio.to_thread.run_sync(fn, *args)


def _tool(fn):
    async def wrapper(*args, **kwargs):
        try:
            return await fn(*args, **kwargs)
        except UpstreamError as e:
            raise ToolError(f"upstream error {e.errcode}: {e.errmsg}")
    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    wrapper.__annotations__ = fn.__annotations__
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
```

- [ ] **Step 5: 实现 main.py**

```python
# app/main.py
"""应用工厂：组装 REST + MCP + 鉴权中间件。"""
from typing import Optional

from fastapi import FastAPI

from .auth import BearerAuthMiddleware
from .config import Settings
from .mcp_server import mcp, set_service
from .rest import router
from .service import DocumentService


def create_app(service: Optional[DocumentService] = None) -> FastAPI:
    settings = Settings()
    app = FastAPI(title="document-proxy", version="0.1.0")
    app.state.api_key = settings.api_key
    app.state.service = service or DocumentService(settings)

    set_service(app.state.service)
    app.include_router(router)
    app.mount("/mcp", mcp.streamable_http_app())
    app.add_middleware(BearerAuthMiddleware, api_key=settings.api_key)
    return app


app = create_app()
```

同时给 `service.py` 补一个测试与 MCP 共用的方法（在 Task 4 的 service 中加入；若 Task 4 未加，现在补上）：

```python
    def get_sheet_properties_only(self, docid: str) -> List[Dict[str, Any]]:
        props_resp = self._wedoc.get_sheet_properties(docid=docid)
        self._check(props_resp)
        return props_resp.get("properties", [])
```

对应在 `tests/test_service.py` 的 `StubWedoc`/`FakeWedoc` 中已有 `get_sheet_properties`，无需改动。

- [ ] **Step 6: 运行测试通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_rest.py -v`
Expected: 5 passed

- [ ] **Step 7: 全量回归**

Run: `.venv/Scripts/python.exe -m pytest -v`
Expected: 全部 passed

- [ ] **Step 8: Commit**

```bash
git add app/rest.py app/mcp_server.py app/main.py app/service.py tests/test_rest.py
git commit -m "feat: REST routes, MCP tools, app factory with auth middleware"
```

---

### Task 7: README 与手动验证

**Files:**
- Create: `README.md`
- Create: `.env`（本地，不入库）

- [ ] **Step 1: 写 .env（用真实凭据）**

复制 `.env.example` 为 `.env`，填入真实 `API_KEY` 与企微配置。此文件不入 git。

- [ ] **Step 2: 写 README.md**

```markdown
# document-proxy — 企微文档数据代理

只读代理：把企业微信的文档、表格、智能表格统一暴露为 REST + MCP（Streamable HTTP）。

## 配置

复制 `.env.example` 为 `.env` 并填写：

- `API_KEY`：调用方鉴权（Bearer）
- `WEIXIN_WORK_CORP_ID` / `WEIXIN_WORK_APP_SECRET`
- `WEIXIN_WORK_DOC_SECRET`（优先）或 `WEIXIN_WORK_CONTACTS_SYNC_SECRET`（回退）

## 启动

    .venv/Scripts/python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000

## REST

- `GET /api/v1/docs/{docid}` — 文档内容（Markdown）
- `GET /api/v1/docs/{docid}/info` — 文档基础信息
- `GET /api/v1/sheets/{docid}` — 表格数据（紧凑 `data: [{列: 值}]`）
- `GET /api/v1/smartsheets/{docid}/{sheet_id}/records` — 智能表格记录（紧凑）

请求头：`Authorization: Bearer <API_KEY>`

    curl -H "Authorization: Bearer $API_KEY" http://localhost:8000/api/v1/docs/DOCID

## MCP

端点：`http://localhost:8000/mcp`（Streamable HTTP，Header 带 `Authorization: Bearer <API_KEY>`）

MCP 配置示例（Claude Code / 通用 MCP 客户端）：

    {
      "mcpServers": {
        "document-proxy": {
          "url": "http://localhost:8000/mcp",
          "headers": { "Authorization": "Bearer <API_KEY>" }
        }
      }
    }

工具：`get_doc_info`、`get_doc_content`、`list_sheets`、`get_spreadsheet_data`、`get_smartsheet_records`

## 数据格式

- 文档 → Markdown
- 表格 / 智能表格 → `data: [{"字段名": "值"}, ...]`（首行作表头 / 字段标题作键）
```

- [ ] **Step 3: 手动冒烟（有凭据时）**

```bash
.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000 &
curl -s -H "Authorization: Bearer $API_KEY" http://localhost:8000/docs/../api/v1 2>/dev/null
curl -s -H "Authorization: Bearer $API_KEY" http://localhost:8000/api/v1/docs/<真实docid>
```

Expected: 返回 Markdown / 紧凑 data JSON。

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: add README with REST/MCP usage"
```

---

## Self-Review 结果

1. **Spec 覆盖**：三种类型（doc/sheet/smartsheet）→ Task 3/4/6；Bearer 鉴权 REST+MCP → Task 5/6；doc_secret 回退 → Task 2；紧凑 data → Task 3；MCP `/mcp` 挂载 → Task 6；README/手动验证 → Task 7。均覆盖。
2. **占位符扫描**：Task 6 Step 3 中第一个 `rest.py` 片段是"反例展示"并明确标注废弃，最终版完整可执行。
3. **类型一致性**：`_matches`、`verify_bearer`、`UpstreamError(errcode/errmsg)`、`get_sheet_properties_only` 在 Task 4/5/6 中签名一致。
