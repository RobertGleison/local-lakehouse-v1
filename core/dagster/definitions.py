from dagster import Definitions, define_asset_job, AssetSelection
from core.dagster.assets import bronze_summoner_data

# Define a job that materializes the bronze assets (Riot Games API ingestion)
bronze_ingestion_job = define_asset_job(
    name="bronze_ingestion_job",
    selection=AssetSelection.assets(bronze_summoner_data)
)

# Export the Definitions container so Dagster CLI/webserver can load them
defs = Definitions(
    assets=[bronze_summoner_data],
    jobs=[bronze_ingestion_job]
)
