import os
from unittest.mock import patch
from core.dagster.resources import LakeResource, DLTResource, MinioResource


def test_lake_resource_builds_settings():
    with patch.dict(os.environ, {}, clear=True):
        resource = LakeResource()
        settings = resource.get_settings()
        assert settings.clickhouse_host
        assert settings.clickhouse_http_port


def test_dlt_resource_builds_settings():
    with patch("os.cpu_count", return_value=4):
        with patch.dict(os.environ, {}, clear=True):
            resource = DLTResource()
            settings = resource.get_settings()
            assert settings.available_threads
            assert settings.extract_workers


def test_minio_resource_builds_settings():
    with patch.dict(os.environ, {}, clear=True):
        resource = MinioResource()
        settings = resource.get_settings()
        assert settings.endpoint_url
        assert settings.bronze_bucket_url
