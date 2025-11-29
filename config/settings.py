from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # FMP API
    fmp_api_key: str
    fmp_base_url: str = "https://financialmodelingprep.com/api"
    
    # Anthropic Claude API
    anthropic_api_key: str
    
    # Macro monitoring APIs
    newsapi_key: str
    fred_api_key: str
    
    # Database
    database_url: str
    
    # Redis
    redis_url: str = "redis://localhost:6379/0"
    
    # Notification
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    
    # App Settings
    polling_interval_minutes: int = 15
    news_lookback_hours: int = 24
    impact_threshold: int = 5  # Minimum impact score to notify (0-10)
    
    # News filtering
    filter_low_quality_sources: bool = True  # Filter YouTube, social media, etc.
    deduplicate_news: bool = True  # Remove duplicate news about same event
    
    class Config:
        env_file = ".env"


settings = Settings()