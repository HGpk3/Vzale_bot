from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    app_name: str = 'Vzale Site API'
    app_env: str = 'dev'
    database_url: str = ''
    jwt_secret: str = 'change-me'
    bot_login_secret: str = 'change-me-bot-login-secret'
    admin_ids: str = '409436763,469460286'
    cors_origins: str = 'http://localhost:3000,http://127.0.0.1:3000'

    access_token_ttl_minutes: int = 60
    refresh_token_ttl_minutes: int = 60 * 24 * 14
    refresh_token_retention_days: int = 30
    bot_login_ttl_seconds: int = 300
    bot_login_retention_days: int = 7

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(',') if origin.strip()]


settings = Settings()
