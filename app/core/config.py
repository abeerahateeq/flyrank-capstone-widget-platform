from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg2://widget_user:widget_pass@localhost:5432/widget_platform"

    geo_provider_a_url: str = "http://ip-api.com/json/{ip}"
    geo_provider_b_url: str = "https://ipapi.co/{ip}/json/"

    rate_limit_per_ip: str = "10/minute"
    rate_limit_per_widget: str = "60/minute"

    # Demo/testing toggles — flipped live in the § 13 demo to prove
    # graceful degradation without touching code.
    force_geo_provider_a_down: bool = False
    force_geo_provider_b_down: bool = False
    force_email_failure: bool = False

    allowed_origins: str = "*"

    class Config:
        env_file = ".env"

    @property
    def cors_origins(self) -> list[str]:
        if self.allowed_origins == "*":
            return ["*"]
        return [o.strip() for o in self.allowed_origins.split(",")]


settings = Settings()
