"""Configuration — pydantic Settings with dotenv fallback."""

from __future__ import annotations

from functools import cached_property

from pydantic import BaseModel, Field, field_validator


class SupersetConfig(BaseModel):
    """Superset instance configuration."""

    base_url: str = Field(
        description="Superset base URL, e.g. https://superset.example.com",
    )
    username: str = Field(
        description="Superset username for JWT auth",
    )
    password: str = Field(
        description="Superset password (never log)",
    )

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        return v

    def login_url(self) -> str:
        return f"{self.base_url}/api/v1/security/login"

    def dashboard_url(self, dashboard_id: str | int) -> str:
        return f"{self.base_url}/superset/dashboard/{dashboard_id}/"


class MCPConfig(BaseModel):
    """MCP server configuration."""

    host: str = Field(default="127.0.0.1", description="MCP server host")
    port: int = Field(default=5008, description="MCP server port")
    timeout: int = Field(default=120, description="HTTP timeout in seconds")

    @cached_property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"


class RetryConfig(BaseModel):
    """Retry/semaphore configuration."""

    max_retries: int = Field(default=3, ge=1, le=10)
    base_delay: float = Field(default=1.0, ge=0.1)
    max_delay: float = Field(default=30.0, ge=1.0)

    def backoff(self, attempt: int) -> float:
        """Exponential backoff with cap."""
        delay = min(self.base_delay * (2 ** attempt), self.max_delay)
        return delay


class Settings(BaseModel):
    """Top-level application settings, loaded from env or defaults.toml."""

    superset: SupersetConfig = Field(default_factory=SupersetConfig)
    mcp: MCPConfig = Field(default_factory=MCPConfig)
    retry: RetryConfig = Field(default_factory=RetryConfig)
    log_level: str = Field(default="INFO")

    @classmethod
    def from_env(cls) -> "Settings":
        """Load settings from environment variables with fallback."""
        import os

        superset = SupersetConfig(
            base_url=os.getenv("SUPERSET_BASE_URL", "http://localhost:8088"),
            username=os.getenv("SUPERSET_USERNAME", "admin"),
            password=os.getenv("SUPERSET_PASSWORD", ""),
        )
        mcp = MCPConfig(
            host=os.getenv("MCP_HOST", "127.0.0.1"),
            port=int(os.getenv("MCP_PORT", "5008")),
            timeout=int(os.getenv("MCP_TIMEOUT", "120")),
        )
        retry = RetryConfig(
            max_retries=int(os.getenv("MCP_MAX_RETRIES", "3")),
            base_delay=float(os.getenv("MCP_BASE_DELAY", "1.0")),
            max_delay=float(os.getenv("MCP_MAX_DELAY", "30.0")),
        )
        return cls(
            superset=superset,
            mcp=mcp,
            retry=retry,
            log_level=os.getenv("LOG_LEVEL", "INFO"),
        )

