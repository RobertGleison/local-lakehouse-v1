from soda.scan import Scan
from dagster import asset_check, AssetCheckResult


def build_soda_check(asset, yml_path: str, blocking: bool):
    """Auto-wire a Soda YAML file as a Dagster asset_check.

    Adding quality checks to a new table only requires a .yml file —
    no Python changes. See ADR 0003 for check tiering conventions.
    """
    @asset_check(asset=asset, blocking=blocking)
    def _check(context) -> AssetCheckResult:
        scan = Scan()
        scan.set_data_source_name("duckdb")
        scan.add_configuration_yaml_file("soda/configuration.yml")
        scan.add_sodacl_yaml_file(yml_path)
        scan.add_variables({"date": context.partition_key})
        scan.execute()
        return AssetCheckResult(
            passed=scan.get_error_count() == 0,
            metadata={
                "errors": scan.get_error_count(),
                "warnings": scan.get_warning_count(),
            },
        )

    return _check
