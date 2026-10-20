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
