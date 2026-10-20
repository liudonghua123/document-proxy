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

def test_records_typed_list_values_to_plain():
    records = [
        {
            "record_id": "r1",
            "values": {
                "question": [{"text": "你好", "type": "text"}],
                "answer": [{"text": "好", "type": "text"}],
                "question_like": [{"text": "你好吗", "type": "text"}],
            },
        },
    ]
    assert records_to_compact(records) == [
        {"question": "你好", "answer": "好", "question_like": "你好吗"}
    ]


def test_records_empty_row_dropped():
    records = [
        {"record_id": "r1", "values": {}},
        {"record_id": "r2", "values": {"question": [{"text": "Q", "type": "text"}]}},
        {"record_id": "r3", "values": None},
    ]
    assert records_to_compact(records) == [
        {"question": "Q"},
    ]


def test_records_mixed_scalar_values():
    records = [
        {
            "record_id": "r1",
            "values": {
                "name": "plain",
                "count": 3,
                "flag": True,
                "typed": [{"text": "T", "type": "text"}],
            },
        },
    ]
    assert records_to_compact(records) == [
        {"name": "plain", "count": "3", "flag": "True", "typed": "T"}
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
