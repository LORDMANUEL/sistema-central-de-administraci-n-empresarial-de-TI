from pydantic_settings import BaseSettings, SettingsConfigDict
class Settings(BaseSettings):
    model_config=SettingsConfigDict(env_prefix="SOFTWARE_",extra="ignore")
    database_url:str="sqlite+pysqlite:///./software.db"
    trusted_proxy_token:str=""
