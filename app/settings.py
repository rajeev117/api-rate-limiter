from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RL_", case_sensitive=False)

    redis_url: str = "redis://redis:6379/0"

    # Token bucket defaults
    capacity: int = 10
    refill_rate_per_sec: float = 5.0

    # Keying / behavior
    key_prefix: str = "rl"
    # When Redis is unavailable: "fail_open" allows traffic; "fail_closed" throttles.
    failure_mode: str = "fail_open"

    # HTTP server
    host: str = "0.0.0.0"
    port: int = 8000


settings = Settings()
