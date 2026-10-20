# document-proxy — 企微文档数据代理

只读代理：把企业微信的文档、表格、智能表格统一暴露为 REST + MCP（Streamable HTTP）。

## 配置

复制 `.env.example` 为 `.env` 并填写：

- `API_KEY`：调用方鉴权（Bearer）
- `WEIXIN_WORK_CORP_ID`：企微企业 ID
- `WEIXIN_WORK_DOC_SECRET`：文档应用 secret
- `DEBUG`：设为 `true` 时 uvicorn 自动重载（代码改动后重启）

## 启动

    .venv/Scripts/python.exe main.py

（host/port 取自 .env 的 `HOST`/`PORT`，默认 0.0.0.0:8000）

## REST

| 路由 | 说明 | 对应企微接口 |
|---|---|---|
| `GET /api/v1/info/{docid}` | 文档/表格/智能表格基础信息 | wedoc get_doc_base_info |
| `GET /api/v1/document/{docid}` | 文档内容（Markdown） | wedoc document/get |
| `GET /api/v1/spreadsheet/{docid}` | 表格文档数据 = 工作表属性列表 | spreadsheet/get_sheet_properties |
| `GET /api/v1/spreadsheet/{docid}/{sheet_id}/records` | 表格记录 = 指定 sheet 的紧凑数据 | spreadsheet/get_sheet_range_data |
| `GET /api/v1/smartsheet/{docid}` | 智能表格文档数据 = sheet_list | smartsheet/get_sheet |
| `GET /api/v1/smartsheet/{docid}/{sheet_id}/records` | 智能表格记录（紧凑） | smartsheet/get_records |

响应统一 envelope：成功 `{"code": 0, "message": "ok", "data": ...}`；
上游错误保持 HTTP 404/502，body 为 `{"code": <errcode>, "message": <errmsg>}`。

请求头：`Authorization: Bearer <API_KEY>`

    curl -H "Authorization: Bearer $API_KEY" http://localhost:8000/api/v1/document/DOCID

表格（spreadsheet）示例：

    curl -H "Authorization: Bearer $API_KEY" \
      http://localhost:8000/api/v1/spreadsheet/dc2Ca04FoEzAiZhRrlEFYKDO_tSq-LsB9xVg---tXnpC7D0M-F9N-BxaYvY_IX84ZK6CgYoXxtvl2v6X-7zZ0StA

    curl -H "Authorization: Bearer $API_KEY" \
      http://localhost:8000/api/v1/spreadsheet/dc2Ca04FoEzAiZhRrlEFYKDO_tSq-LsB9xVg---tXnpC7D0M-F9N-BxaYvY_IX84ZK6CgYoXxtvl2v6X-7zZ0StA/BB08J2/records

智能表格（smartsheet）示例：

    curl -H "Authorization: Bearer $API_KEY" \
      http://localhost:8000/api/v1/smartsheet/dcZs2MUbIZRBXXpAN7Uin2WbVNUGEHHgvGLFBnQ6aD7DKctc9JYIQcQZ2YCBhZg4hvGRL8TwjtSW30AvmrZ6Rzfw

    curl -H "Authorization: Bearer $API_KEY" \
      http://localhost:8000/api/v1/smartsheet/dcZs2MUbIZRBXXpAN7Uin2WbVNUGEHHgvGLFBnQ6aD7DKctc9JYIQcQZ2YCBhZg4hvGRL8TwjtSW30AvmrZ6Rzfw/q979lj/records

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

工具：

- `get_doc_info` — 文档基础信息（企微 get_doc_base_info）
- `get_doc_content` — 文档内容 Markdown（企微 document/get）
- `list_spreadsheet_sheets` — 表格工作表属性列表（企微 spreadsheet/get_sheet_properties）
- `get_spreadsheet_records` — 表格指定工作表记录（企微 spreadsheet/get_sheet_range_data）
- `list_smartsheet_sheets` — 智能表格子表列表（企微 smartsheet/get_sheet）
- `get_smartsheet_records` — 智能表格指定子表记录（企微 smartsheet/get_records）

## 数据格式

- 文档 → Markdown
- 表格 / 智能表格 → `data: [{"字段名": "值"}, ...]`（首行作表头 / 字段标题作键）

## 错误处理

- REST：上游 errcode≠0 → 404（文档不存在，errcode 1934008）或 502（其他上游错误），detail 含 errcode/errmsg；401 表示 API_KEY 无效
- MCP：上游错误以 ToolError 返回（文本含 errcode/errmsg）

## 开发

    python -m venv .venv
    .venv/Scripts/python.exe -m pip install -r requirements.txt
    .venv/Scripts/python.exe -m pytest -v
