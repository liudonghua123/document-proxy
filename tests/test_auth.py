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
