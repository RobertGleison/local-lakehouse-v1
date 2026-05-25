import os
from unittest.mock import patch
import pytest
from core.settings.dlt_settings import DLTSettings

def test_dlt_settings_defaults():
    """Verify that DLTSettings calculates logical worker counts based on threads."""
    # Mock os.cpu_count to return 8 logical cores
    with patch("os.cpu_count", return_value=8):
        # Clear env variables to ensure validators run and calculate values
        with patch.dict(os.environ, {}, clear=True):
            settings = DLTSettings()

            # Assert defaults are calculated correctly:
            # available_threads = 8
            assert settings.available_threads == 8

            # extract_workers = max(1, 8 - 1) = 7
            assert settings.extract_workers == 7
            assert os.environ["EXTRACT__WORKERS"] == "7"

            # normalize_workers = max(1, 8 - 2) = 6
            assert settings.normalize_workers == 6
            assert os.environ["NORMALIZE__WORKERS"] == "6"

            # load_workers = max(1, 8 - 1) = 7
            assert settings.load_workers == 7
            assert os.environ["LOAD__WORKERS"] == "7"


def test_dlt_settings_env_overrides():
    """Verify that custom environment variables override defaults."""
    custom_env = {
        "EXTRACT__WORKERS": "12",
        "NORMALIZE__WORKERS": "8",
        "LOAD__WORKERS": "10",
        "DLT_DATA_DIR": "/tmp/dlt"
    }

    with patch("os.cpu_count", return_value=4):
        with patch.dict(os.environ, custom_env, clear=True):
            settings = DLTSettings()

            # Available threads is 4
            assert settings.available_threads == 4

            # Environment values should take precedence
            assert settings.extract_workers == 12
            assert settings.normalize_workers == 8
            assert settings.load_workers == 10

            # No changes to the environment variables
            assert os.environ["EXTRACT__WORKERS"] == "12"
