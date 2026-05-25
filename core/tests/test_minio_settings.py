import os
from unittest.mock import patch
from core.settings.minio_settings import MinioSettings

def test_minio_settings_defaults():
    with patch.dict(os.environ, {}, clear=True):
        settings = MinioSettings()

        assert settings.endpoint_url == "http://minio:9000"
        assert settings.access_key == "minioadmin"
        assert settings.secret_key.get_secret_value() == "minioadmin123"
        assert settings.bronze_bucket_url == "s3://bronze"

def test_minio_settings_env_overrides():
    custom_env = {
        "MINIO_ENDPOINT_URL": "http://192.168.1.10:9000",
        "MINIO_ROOT_USER": "myuser",
        "MINIO_ROOT_PASSWORD": "mypassword",
        "BRONZE_BUCKET_URL": "s3://my-bronze-bucket",
    }
    with patch.dict(os.environ, custom_env, clear=True):
        settings = MinioSettings()

        assert settings.endpoint_url == "http://192.168.1.10:9000"
        assert settings.access_key == "myuser"
        assert settings.secret_key.get_secret_value() == "mypassword"
        assert settings.bronze_bucket_url == "s3://my-bronze-bucket"

def test_minio_settings_dlt_env_vars():
    """Verify that apply_to_environment() sets the dlt-expected DESTINATION__ vars."""
    with patch.dict(os.environ, {}, clear=True):
        settings = MinioSettings()
        settings.apply_to_environment()

        assert os.environ["DESTINATION__FILESYSTEM__BUCKET_URL"] == "s3://bronze"
        assert os.environ["DESTINATION__FILESYSTEM__CREDENTIALS__AWS_ACCESS_KEY_ID"] == "minioadmin"
        assert os.environ["DESTINATION__FILESYSTEM__CREDENTIALS__AWS_SECRET_ACCESS_KEY"] == "minioadmin123"
        assert os.environ["DESTINATION__FILESYSTEM__CREDENTIALS__ENDPOINT_URL"] == "http://minio:9000"
