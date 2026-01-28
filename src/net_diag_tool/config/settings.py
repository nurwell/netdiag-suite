from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional

class Settings(BaseSettings):
    APP_NAME: str = "NetDiagSuite"
    APP_ENV: str = "production"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    
    DEFAULT_TIMEOUT: int = 10
    PING_TARGET_PRIMARY: str = "8.8.8.8"
    PING_TARGET_SECONDARY: str = "1.1.1.1"
    
    REPORT_OUTPUT_DIR: str = "./reports"
    INCLUDE_SYSTEM_METRICS: bool = True
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

@lru_cache()
def get_settings() -> Settings:
    return Settings()
