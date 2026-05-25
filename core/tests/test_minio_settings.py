import os
import pytest
from pydantic import ValidationError
from core.settings.minio_settings import MinioSettings


def _set_minio_env():
    os.environ["MINIO_ENDPOINT_URL"] = "http://test-minio:9000"
    os.environ["MINIO_ROOT_USER"] = "test-access-key"
    os.environ["MINIO_ROOT_PASSWORD"] = "test-secret-key"
    os.environ["BRONZE_BUCKET_URL"] = "s3://test-bronze"


def test_minio_settings_fields_exist():
    """Verify MinioSettings fields are accessible when env vars are set."""
    _set_minio_env()
    settings = MinioSettings()

    assert settings.endpoint_url
    assert settings.access_key
    assert settings.secret_key is not None
    assert settings.bronze_bucket_url


def test_minio_settings_raises_on_missing_vars():
    """Verify ValidationError is raised when required env vars are absent."""
    with pytest.raises(ValidationError):
        MinioSettings()


def test_minio_settings_apply_to_environment():
    """Verify apply_to_environment() sets the dlt DESTINATION__ vars."""
    _set_minio_env()
    settings = MinioSettings()
    settings.apply_to_environment()

    assert os.environ.get("DESTINATION__FILESYSTEM__BUCKET_URL")
    assert os.environ.get("DESTINATION__FILESYSTEM__CREDENTIALS__AWS_ACCESS_KEY_ID")
    assert os.environ.get("DESTINATION__FILESYSTEM__CREDENTIALS__AWS_SECRET_ACCESS_KEY") is not None
    assert os.environ.get("DESTINATION__FILESYSTEM__CREDENTIALS__ENDPOINT_URL")
    assert os.environ.get("DESTINATION__FILESYSTEM__CREDENTIALS__VERIFY") is not None
