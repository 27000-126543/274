import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

    DATABASE_URL: str = "sqlite:///ip_protection.db"
    REDIS_URL: str = "redis://localhost:6379/0"

    SIMILARITY_THRESHOLD: float = 0.80

    MAX_CONCURRENT_SPIDERS: int = 10
    REQUEST_TIMEOUT: int = 30
    USER_AGENT: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

    TAOBAO_ENABLED: bool = True
    JD_ENABLED: bool = True
    PDD_ENABLED: bool = True
    DOUYIN_ENABLED: bool = True
    XIAOHONGSHU_ENABLED: bool = True

    SMTP_SERVER: str = "smtp.company.com"
    SMTP_PORT: int = 465
    SMTP_USER: str = "legal@company.com"
    SMTP_PASSWORD: str = ""
    SMTP_USE_SSL: bool = True

    COMPANY_NAME: str = "示例科技有限公司"
    LEGAL_DEPARTMENT_EMAIL: str = "legal@company.com"
    LEGAL_DIRECTOR_EMAIL: str = "director@company.com"

    EVIDENCE_STORAGE_PATH: str = str(BASE_DIR / "evidence")
    LOG_FILE: str = str(BASE_DIR / "logs" / "ip_protection.log")
    LOG_LEVEL: str = "INFO"

    SERVER_HOST: str = "0.0.0.0"
    SERVER_PORT: int = 8000

    @property
    def evidence_path(self) -> Path:
        path = Path(self.EVIDENCE_STORAGE_PATH)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def log_path(self) -> Path:
        path = Path(self.LOG_FILE).parent
        path.mkdir(parents=True, exist_ok=True)
        return Path(self.LOG_FILE)


settings = Settings()
