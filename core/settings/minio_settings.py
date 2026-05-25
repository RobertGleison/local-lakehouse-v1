import os
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class MinioSettings(BaseSettings):
    """
    Settings for the MinIO S3-compatible object storage endpoint.
    Provides credentials and bucket configuration for the Bronze lake layer.
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    endpoint_url: str = Field(
        alias="MINIO_ENDPOINT_URL",
        description="HTTP endpoint for the MinIO service",
    )
    access_key: str = Field(
        alias="MINIO_ROOT_USER",
        description="MinIO root access key (AWS_ACCESS_KEY_ID equivalent)",
    )
    secret_key: SecretStr = Field(
        alias="MINIO_ROOT_PASSWORD",
        description="MinIO root secret key (AWS_SECRET_ACCESS_KEY equivalent)",
    )
    bronze_bucket_url: str = Field(
        alias="BRONZE_BUCKET_URL",
        description="dlt filesystem destination bucket URL for the Bronze layer",
    )

    def apply_to_environment(self) -> None:
        """Set the dlt DESTINATION__ env vars that the filesystem destination expects."""
        os.environ.setdefault("DESTINATION__FILESYSTEM__BUCKET_URL", self.bronze_bucket_url)
        os.environ.setdefault(
            "DESTINATION__FILESYSTEM__CREDENTIALS__AWS_ACCESS_KEY_ID", self.access_key
        )
        os.environ.setdefault(
            "DESTINATION__FILESYSTEM__CREDENTIALS__AWS_SECRET_ACCESS_KEY",
            self.secret_key.get_secret_value(),
        )
        os.environ.setdefault(
            "DESTINATION__FILESYSTEM__CREDENTIALS__ENDPOINT_URL", self.endpoint_url
        )
        os.environ.setdefault("DESTINATION__FILESYSTEM__CREDENTIALS__AWS_SESSION_TOKEN", "")
        os.environ.setdefault("DESTINATION__FILESYSTEM__CREDENTIALS__VERIFY", "False")
