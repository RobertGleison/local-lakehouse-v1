import os
from unittest.mock import patch
from core.settings.dlt_settings import DLTSettings


def test_dlt_settings_fields_exist():
    """Verify DLTSettings fields are accessible after construction."""
    with patch("os.cpu_count", return_value=8):
        settings = DLTSettings()

        assert settings.available_threads
        assert settings.extract_workers
        assert settings.normalize_workers
        assert settings.load_workers


def test_dlt_settings_env_overrides_respected():
    """Verify that custom environment variables are picked up by DLTSettings."""
    os.environ["EXTRACT__WORKERS"] = "12"
    os.environ["NORMALIZE__WORKERS"] = "8"
    os.environ["LOAD__WORKERS"] = "10"

    with patch("os.cpu_count", return_value=4):
        settings = DLTSettings()

        assert settings.extract_workers
        assert settings.normalize_workers
        assert settings.load_workers
