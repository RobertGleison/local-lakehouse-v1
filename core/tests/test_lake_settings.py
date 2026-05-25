import os
import pytest
from pydantic import ValidationError
from core.settings.lake_settings import LakeSettings


def _set_lake_env():
    os.environ["CLICKHOUSE_HOST"] = "test-clickhouse"
    os.environ["CLICKHOUSE_HTTP_PORT"] = "8123"
    os.environ["CLICKHOUSE_NATIVE_PORT"] = "9000"
    os.environ["CLICKHOUSE_USER"] = "test-user"
    os.environ["CLICKHOUSE_PASSWORD"] = "test-password"
    os.environ["CLICKHOUSE_DATABASE"] = "test-db"
    os.environ["CLOUDBEAVER_HOST"] = "test-cloudbeaver"
    os.environ["CLOUDBEAVER_PORT"] = "8978"


def test_lake_settings_fields_exist():
    """Verify LakeSettings fields are accessible when env vars are set."""
    _set_lake_env()
    settings = LakeSettings()

    assert settings.clickhouse_host
    assert settings.clickhouse_http_port
    assert settings.clickhouse_native_port
    assert settings.clickhouse_user
    assert settings.clickhouse_password is not None
    assert settings.clickhouse_database
    assert settings.cloudbeaver_host
    assert settings.cloudbeaver_port
    assert settings.clickhouse_http_url
    assert settings.clickhouse_native_url
    assert settings.cloudbeaver_url


def test_lake_settings_raises_on_missing_vars():
    """Verify ValidationError is raised when required env vars are absent."""
    with pytest.raises(ValidationError):
        LakeSettings()
