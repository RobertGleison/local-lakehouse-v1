# core/dagster/resources.py
import os
from unittest.mock import patch
from dagster import ConfigurableResource
from core.settings import DLTSettings, LakeSettings, MinioSettings


class LakeResource(ConfigurableResource):
    """Dagster resource wrapping LakeSettings for ClickHouse connectivity."""

    clickhouse_host: str = "clickhouse"
    clickhouse_http_port: int = 8123
    clickhouse_native_port: int = 9000
    clickhouse_user: str = "default"
    clickhouse_password: str = ""
    clickhouse_database: str = "default"
    cloudbeaver_host: str = "cloudbeaver"
    cloudbeaver_port: int = 8978

    def get_settings(self) -> LakeSettings:
        env = {
            "CLICKHOUSE_HOST": self.clickhouse_host,
            "CLICKHOUSE_HTTP_PORT": str(self.clickhouse_http_port),
            "CLICKHOUSE_NATIVE_PORT": str(self.clickhouse_native_port),
            "CLICKHOUSE_USER": self.clickhouse_user,
            "CLICKHOUSE_PASSWORD": self.clickhouse_password,
            "CLICKHOUSE_DATABASE": self.clickhouse_database,
            "CLOUDBEAVER_HOST": self.cloudbeaver_host,
            "CLOUDBEAVER_PORT": str(self.cloudbeaver_port),
        }
        with patch.dict(os.environ, env, clear=True):
            return LakeSettings()


class DLTResource(ConfigurableResource):
    """Dagster resource wrapping DLTSettings for dlt worker configuration."""

    def get_settings(self) -> DLTSettings:
        return DLTSettings()


class MinioResource(ConfigurableResource):
    """Dagster resource wrapping MinioSettings for S3/MinIO pipeline connectivity."""

    endpoint_url: str = "http://minio:9000"
    access_key: str = "minioadmin"
    secret_key: str = "minioadmin123"
    bronze_bucket_url: str = "s3://bronze"

    def get_settings(self) -> MinioSettings:
        env = {
            "MINIO_ENDPOINT_URL": self.endpoint_url,
            "MINIO_ROOT_USER": self.access_key,
            "MINIO_ROOT_PASSWORD": self.secret_key,
            "BRONZE_BUCKET_URL": self.bronze_bucket_url,
        }
        with patch.dict(os.environ, env, clear=True):
            return MinioSettings()
