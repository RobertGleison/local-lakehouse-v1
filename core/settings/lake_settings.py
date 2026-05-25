from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class LakeSettings(BaseSettings):
    """
    Settings to configure connection strings, ports, and authorization
    parameters for data lake endpoints including ClickHouse OLAP and Cloudbeaver.
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ClickHouse Connection Configurations
    clickhouse_host: str = Field(
        alias="CLICKHOUSE_HOST",
        description="Host address of the ClickHouse service in the cluster",
    )
    clickhouse_http_port: int = Field(
        alias="CLICKHOUSE_HTTP_PORT",
        description="HTTP connection port for ClickHouse server",
    )
    clickhouse_native_port: int = Field(
        alias="CLICKHOUSE_NATIVE_PORT",
        description="Native TCP protocol port for ClickHouse server",
    )
    clickhouse_user: str = Field(
        alias="CLICKHOUSE_USER",
        description="ClickHouse login username",
    )
    clickhouse_password: SecretStr = Field(
        alias="CLICKHOUSE_PASSWORD",
        description="ClickHouse login password",
    )
    clickhouse_database: str = Field(
        alias="CLICKHOUSE_DATABASE",
        description="Default database schema for ClickHouse connection",
    )

    # Cloudbeaver Configurations
    cloudbeaver_host: str = Field(
        alias="CLOUDBEAVER_HOST",
        description="Host address of the Cloudbeaver Web SQL editor",
    )
    cloudbeaver_port: int = Field(
        alias="CLOUDBEAVER_PORT",
        description="Connection port for Cloudbeaver Web UI",
    )

    @property
    def clickhouse_http_url(self) -> str:
        """Construct the HTTP JDBC connection string for ClickHouse client drivers."""
        password = self.clickhouse_password.get_secret_value()
        auth = f"{self.clickhouse_user}:{password}@" if password else f"{self.clickhouse_user}@"
        return f"http://{auth}{self.clickhouse_host}:{self.clickhouse_http_port}/{self.clickhouse_database}"

    @property
    def clickhouse_native_url(self) -> str:
        """Construct the Native clickhouse driver protocol connection string."""
        return f"clickhouse://{self.clickhouse_host}:{self.clickhouse_native_port}/{self.clickhouse_database}"

    @property
    def cloudbeaver_url(self) -> str:
        """Construct the full address to access the Cloudbeaver Web UI."""
        return f"http://{self.cloudbeaver_host}:{self.cloudbeaver_port}"
