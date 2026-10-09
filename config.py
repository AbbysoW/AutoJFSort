from pydantic import BaseModel, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

class LogConfig(BaseModel):
    level: str = "DEBUG"
    format: str = "%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="__",
        extra="ignore",
    )

    debug: bool = False
    llm_api_key: str

    log: LogConfig = LogConfig()
settings = Settings()
