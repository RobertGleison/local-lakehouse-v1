from core.enums import EnvironmentEnum, StorageEnum, LayerEnum


def test_environment_enum_values():
    assert EnvironmentEnum.PRODUCTION.value == "production"
    assert EnvironmentEnum.DEVELOPMENT.value == "development"
    assert EnvironmentEnum.TEST.value == "test"
    assert EnvironmentEnum.CI.value == "ci"


def test_storage_enum_values():
    assert StorageEnum.MINIO.value == "minio"
    assert StorageEnum.S3.value == "s3"


def test_layer_enum_values():
    assert LayerEnum.BRONZE.value == "bronze"
    assert LayerEnum.SILVER.value == "silver"
    assert LayerEnum.GOLD.value == "gold"


def test_environment_enum_helpers():
    assert EnvironmentEnum.TEST.is_test() is True
    assert EnvironmentEnum.CI.is_test() is True
    assert EnvironmentEnum.PRODUCTION.is_test() is False
    assert EnvironmentEnum.PRODUCTION.is_production() is True
    assert EnvironmentEnum.DEVELOPMENT.is_production() is False
