from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    database_url: str = "sqlite:///./taukits.db"
    bacon_api_url: str = "https://demob.bacontrack.com.ar/api"
    #bacon_api_url: str = "https://back.bacontrack.com.ar/api"
    bacon_token: str = ""
    sucursal_codigo: str = "001"
    sucursal_nombre: str = "Morón"
    estudio_codigo: str = "001"
    estudio_nombre: str = "Helicobacter Pylori (Urea-13C)"
    db_schema: str = "lab"
    app_env: str = "prod"
    smtp_server: str = "smtp.office365.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    bacon_contact_email: str = ""

    # Autenticación / JWT
    jwt_secret: str = "dev-insecure-secret-change-me"
    jwt_algorithm: str = "HS256"
    session_timeout_minutes: int = 15        # vida del access token
    refresh_timeout_minutes: int = 720       # vida del refresh token (12 h)

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()
