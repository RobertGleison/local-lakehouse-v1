# core/dagster/tests/test_resources.py
import os
from unittest.mock import patch
from core.dagster.resources import LakeResource, DLTResource, MinioResource

def test_lake_resource_builds_settings():
    with patch.dict(os.environ, {}, clear=True):
        resource = LakeResource()
        settings = resource.get_settings()
        assert settings.clickhouse_host == "clickhouse"
        assert settings.clickhouse_http_port == 8123

def test_dlt_resource_builds_settings():
    with patch("os.cpu_count", return_value=4):
        with patch.dict(os.environ, {}, clear=True):
            resource = DLTResource()
            settings = resource.get_settings()
            assert settings.available_threads == 4
            assert settings.extract_workers == 3

def test_minio_resource_builds_settings():
    with patch.dict(os.environ, {}, clear=True):
        resource = MinioResource()
        settings = resource.get_settings()
        assert settings.endpoint_url == "http://minio:9000"
        assert settings.bronze_bucket_url == "s3://bronze"
