# tests/test_config.py
import pytest

from app.config import Settings


def make_env(monkeypatch, **overrides):
    base = {
        "API_KEY": "k1",
        "WEIXIN_WORK_CORP_ID": "corp",
        "WEIXIN_WORK_DOC_SECRET": "doc-secret",
        "WEIXIN_WORK_BASE_URL": "",
    }
    for k in ("HOST", "PORT", "DEBUG"):
        monkeypatch.delenv(k, raising=False)
    base.update(overrides)
    for k, v in base.items():
        monkeypatch.setenv(k, v)


def test_required_missing_api_key(monkeypatch):
    make_env(monkeypatch, API_KEY="")
    with pytest.raises(ValueError, match="API_KEY"):
        Settings()


def test_doc_secret_required(monkeypatch):
    make_env(monkeypatch, WEIXIN_WORK_DOC_SECRET="")
    with pytest.raises(ValueError, match="DOC_SECRET"):
        Settings()


def test_doc_secret_used_directly(monkeypatch):
    make_env(monkeypatch, WEIXIN_WORK_DOC_SECRET="doc-secret")
    s = Settings()
    assert s.doc_secret == "doc-secret"


def test_base_url_default(monkeypatch):
    make_env(monkeypatch)
    s = Settings()
    assert s.base_url == "https://qyapi.weixin.qq.com/"


def test_debug_parsing(monkeypatch):
    make_env(monkeypatch)
    assert Settings().debug is False
    for v in ("true", "1", "yes", "TRUE", "Yes"):
        make_env(monkeypatch, DEBUG=v)
        assert Settings().debug is True, v
    make_env(monkeypatch, DEBUG="false")
    assert Settings().debug is False
