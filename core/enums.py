from enum import Enum


class EnvironmentEnum(str, Enum):
    PRODUCTION = "production"
    DEVELOPMENT = "development"
    TEST = "test"
    CI = "ci"

    def is_production(self) -> bool:
        return self == EnvironmentEnum.PRODUCTION

    def is_test(self) -> bool:
        return self in (EnvironmentEnum.TEST, EnvironmentEnum.CI)


class StorageEnum(str, Enum):
    MINIO = "minio"
    S3 = "s3"


class LayerEnum(str, Enum):
    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"
