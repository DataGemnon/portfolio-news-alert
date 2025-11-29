from pydantic_settings import BaseSettings
from pydantic import Field
import os

# Détection de l'environnement
IS_STREAMLIT_CLOUD = os.getenv("STREAMLIT_RUNTIME_ENV") is not None

class Settings(BaseSettings):
    # API Keys
    fmp_api_key: str = Field(default="", env="FMP_API_KEY")
    anthropic_api_key: str = Field(default="", env="ANTHROPIC_API_KEY")
    newsapi_key: str = Field(default="", env="NEWSAPI_KEY")
    fred_api_key: str = Field(default="", env="FRED_API_KEY")
    
    # URLs
    fmp_base_url: str = Field(default="https://financialmodelingprep.com/api", env="FMP_BASE_URL")
    redis_url: str = Field(default="", env="REDIS_URL")
    database_url: str = Field(default="sqlite:///portfolio_news.db", env="DATABASE_URL")
    
    # Email config
    smtp_host: str = Field(default="smtp.gmail.com", env="SMTP_HOST")
    smtp_port: int = Field(default=587, env="SMTP_PORT")
    smtp_user: str = Field(default="", env="SMTP_USER")
    smtp_password: str = Field(default="", env="SMTP_PASSWORD")
    
    # App config
    polling_interval_minutes: int = Field(default=60, env="POLLING_INTERVAL_MINUTES")
    news_lookback_hours: int = Field(default=24, env="NEWS_LOOKBACK_HOURS")
    impact_threshold: int = Field(default=6, env="IMPACT_THRESHOLD")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

# Fonction pour charger les settings depuis Streamlit secrets
def load_settings():
    """Charge les settings depuis .env ou st.secrets selon l'environnement"""
    
    if IS_STREAMLIT_CLOUD:
        # On est sur Streamlit Cloud, utiliser st.secrets
        try:
            import streamlit as st
            secrets = st.secrets.get("default", {})
            
            return Settings(
                fmp_api_key=secrets.get("FMP_API_KEY", ""),
                anthropic_api_key=secrets.get("ANTHROPIC_API_KEY", ""),
                newsapi_key=secrets.get("NEWSAPI_KEY", ""),
                fred_api_key=secrets.get("FRED_API_KEY", ""),
                smtp_host=secrets.get("SMTP_HOST", "smtp.gmail.com"),
                smtp_port=int(secrets.get("SMTP_PORT", "587")),
                smtp_user=secrets.get("SMTP_USER", ""),
                smtp_password=secrets.get("SMTP_PASSWORD", ""),
                redis_url=secrets.get("REDIS_URL", ""),
                database_url=secrets.get("DATABASE_URL", "sqlite:///portfolio_news.db"),
            )
        except Exception as e:
            print(f"Error loading Streamlit secrets: {e}")
            # Fallback sur valeurs par défaut
            return Settings()
    else:
        # Environnement local, utiliser .env
        return Settings()

# Créer l'instance settings
settings = load_settings()