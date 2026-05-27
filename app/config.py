from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    database_url: str = "sqlite:///./taukits.db"
    bacon_api_url: str = "https://demob.bacontrack.com.ar/api"
    bacon_token: str = ""
    sucursal_codigo: str = "001"
    sucursal_nombre: str = "Morón"
    estudio_codigo: str = "001"
    estudio_nombre: str = "Helicobacter Pylori (Urea-13C)"
    db_schema: str = "lab"
    app_env: str = "prod"

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()
