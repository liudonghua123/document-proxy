"""启动入口：python main.py"""
import uvicorn

from app.config import Settings


def main() -> None:
    settings = Settings()
    uvicorn.run(
        "app.main:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )


if __name__ == "__main__":
    main()
