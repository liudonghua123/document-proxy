# 企微文档数据代理（document-proxy）设计

日期：2026-10-20

## 目标

提供一个"文档数据代理"HTTP 服务，把企业微信的**文档、表格、智能表格**三种数据源统一暴露为：

1. **RESTful API**（FastAPI 实现）
2. **MCP 服务**（FastMCP，Streamable HTTP，挂载在 `/mcp`）

供 AI 客户端（如 Claude、MCP Host）或普通程序消费。

## 范围

**只读代理**。不做文档创建/删除/编辑/权限修改。支持三种类型的数据读取：

| 类型 | 企微 doc_type | 数据来源接口 | 输出格式 |
|------|--------------|--------------|----------|
| 文档 | 3 | `wedoc/document/get` | Markdown（Node 树扁平化为纯文本） |
| 表格 | 4 | `wedoc/spreadsheet/get_sheet_properties` + `get_sheet_range_data` | 紧凑行→对象映射 `data: [{...}, ...]` |
| 智能表格 | 10 | `wedoc/smartsheet/get_records` | 紧凑行→对象映射 `data: [{...}, ...]` |

## 配置（.env）

```
API_KEY=xxx                              # 本服务调用方鉴权（必填）
WEIXIN_WORK_BASE_URL=https://qyapi.weixin.qq.com/
WEIXIN_WORK_CORP_ID=xxx                  # 必填
WEIXIN_WORK_APP_SECRET=xxx               # 必填（Config 校验需要）
WEIXIN_WORK_DOC_SECRET=xxx               # 文档应用 secret（优先使用）
WEIXIN_WORK_CONTACTS_SYNC_SECRET=xxx     # 回退：DOC_SECRET 未配置时使用
HOST=0.0.0.0
PORT=8000
```

- token 获取：优先 `WEIXIN_WORK_DOC_SECRET`；未配置时回退 `WEIXIN_WORK_CONTACTS_SYNC_SECRET` 作为 doc secret。
- 由 weixin-work-reborn 的 `AccessTokenManager` 做 TTL 缓存（7000s）。

## 架构

```
┌─────────────┐      Bearer API_KEY      ┌──────────────────────────────┐
│  REST 客户端 │ ───────────────────────▶ │  FastAPI app                 │
└─────────────┘                          │  ├ REST /api/v1/...          │
┌─────────────┐      Bearer API_KEY      │  ├ /mcp (FastMCP streamable) │
│  MCP 客户端  │ ───────────────────────▶ │  │   AuthMiddleware          │
└─────────────┘                          │  └ DocumentService           │
                                         │      └ weixin-work-reborn    │
                                         └──────────────────────────────┘
                                                        │
                                                        ▼
                                              企微开放平台 qyapi.weixin.qq.com
```

### 模块划分

```
document-proxy/
├── .env.example
├── requirements.txt
├── README.md
├── app/
│   ├── __init__.py
│   ├── config.py          # Settings: 读 .env，解析 doc_secret 回退逻辑
│   ├── auth.py            # Bearer 校验（FastAPI dependency + ASGI 中间件）
│   ├── service.py         # DocumentService: 封装 WeChatWorkClient 的只读操作
│   ├── formatting.py      # Node 树→Markdown；表格 rows→紧凑 data
│   ├── rest.py            # FastAPI 路由 /api/v1/...
│   ├── mcp_server.py      # FastMCP 实例与工具定义
│   └── main.py            # 组装 FastAPI app，挂载 MCP
└── tests/
    ├── test_config.py
    ├── test_formatting.py
    ├── test_auth.py
    └── test_rest.py
```

### 各单元职责

- **config.py**：`Settings` dataclass。`load_dotenv()` 后读取环境变量；`doc_secret` 属性实现"DOC_SECRET 优先、CONTACTS_SYNC_SECRET 回退"；缺 `API_KEY`/`CORP_ID`/`APP_SECRET` 时抛 `ValueError`。
- **auth.py**：
  - `verify_bearer(credentials)` FastAPI dependency：校验 `Authorization: Bearer <API_KEY>`，不匹配返回 401。
  - `BearerAuthMiddleware`：纯 ASGI 中间件，保护 `/mcp` 路径（同时允许 `?access_token=` 查询参数以兼容部分 MCP 客户端——已确认方案为仅 Bearer 头，不实现 query 兼容）。
- **service.py**：`DocumentService(settings)`。懒加载 `WeChatWorkClient`。方法：
  - `get_doc_info(docid)` → `doc_base_info`
  - `get_doc_content(docid)` → Markdown 字符串
  - `get_spreadsheet(docid)` → 每个 sheet 的紧凑数据
  - `get_smartsheet_records(docid, sheet_id)` → 紧凑数据
- **formatting.py**（纯函数，重点测试）：
  - `node_to_markdown(node)`：递归遍历企微文档 Node 树，拼接文本；标题加 `#`，列表加 `-`，表格转 Markdown 表格。
  - `grid_to_records(rows, start_row)`：表格 GridData `rows[].values[].cell_value` → 行→对象映射列表（首行非空时作为表头键名，否则用 `col_1/col_2/...`）。
  - `records_to_compact(records)`：智能表格 `records[].values`（key_type=FIELD_TITLE）→ 直接取 `values` 组成紧凑列表。
- **rest.py**：路由（均依赖 `verify_bearer`）：
  - `GET /api/v1/docs/{docid}` → `{data: "markdown..."}`
  - `GET /api/v1/docs/{docid}/info` → `{data: {...}}`
  - `GET /api/v1/sheets/{docid}` → `{data: {sheet_id: {title, data: [...]}}}`
  - `GET /api/v1/smartsheets/{docid}/{sheet_id}/records` → `{data: [...]}`
- **mcp_server.py**：`FastMCP("document-proxy")`，工具：
  - `get_doc_info(docid)` / `get_doc_content(docid)` / `list_sheets(docid)` / `get_spreadsheet_data(docid)` / `get_smartsheet_records(docid, sheet_id)`
- **main.py**：`create_app()` 工厂——加载 Settings、构造 DocumentService、注册 REST router、`app.mount("/mcp", mcp.streamable_http_app())`、添加 `BearerAuthMiddleware`。

## 错误处理

- 上游 `errcode != 0` → 抛 `UpstreamError`，REST 层转 502（带 errcode/errmsg），MCP 层转 `ToolError` 文本。
- 401：`{"detail": "Invalid or missing API key"}`。
- 404：docid 不存在（上游 errcode 1934008 等）统一映射为 404。
- 未知异常 → 500，日志记录堆栈。

## 测试策略

- `formatting.py` 纯函数：直接单测 Node 树→Markdown、GridData→紧凑 data 的典型与边界（空表、缺表头、多行）。
- `config.py`：monkeypatch 环境变量，测回退逻辑与必填校验。
- REST/MCP：`httpx.AsyncClient` + ASGI transport；`DocumentService` 用 mock 替身，不打真实上游。
- 不做真实企微调用的集成测试（无凭据时不可运行，README 提供手动 curl 验证步骤）。

## 安全

- API_KEY 使用 `secrets.compare_digest` 比较防时序攻击。
- .env 不入库；提供 .env.example。.gitignore 覆盖 .env。
