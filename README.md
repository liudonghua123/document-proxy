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

## 错误处理

- REST：上游 errcode≠0 → 404（文档不存在，errcode 1934008）或 502（其他上游错误），detail 含 errcode/errmsg；401 表示 API_KEY 无效
- MCP：上游错误以 ToolError 返回（文本含 errcode/errmsg）

## 开发

    python -m venv .venv
    .venv/Scripts/python.exe -m pip install -r requirements.txt
    .venv/Scripts/python.exe -m pytest -v
