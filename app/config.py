# app/config.py
"""应用配置：读取 .env 与环境变量。"""
import os

from dotenv import load_dotenv

load_dotenv()

_DEFAULT_BASE_URL = "https://qyapi.weixin.qq.com/"


def _env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes")


class Settings:
    def __init__(self) -> None:
        self.api_key = os.getenv("API_KEY", "")
        self.base_url = os.getenv("WEIXIN_WORK_BASE_URL", "") or _DEFAULT_BASE_URL
        self.corp_id = os.getenv("WEIXIN_WORK_CORP_ID", "")
        self.doc_secret = os.getenv("WEIXIN_WORK_DOC_SECRET", "")
        self.host = os.getenv("HOST", "0.0.0.0")
        self.port = int(os.getenv("PORT", "8000"))
        self.debug = _env_bool("DEBUG", False)

        if not self.api_key:
            raise ValueError("API_KEY is required")
        if not self.corp_id:
            raise ValueError("WEIXIN_WORK_CORP_ID is required")
        if not self.doc_secret:
            raise ValueError("WEIXIN_WORK_DOC_SECRET is required")
