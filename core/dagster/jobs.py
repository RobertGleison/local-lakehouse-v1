from dagster import define_asset_job, AssetSelection
from core.dagster.assets import bronze_summoner_data

bronze_ingestion_job = define_asset_job(
    name="bronze_ingestion_job",
    selection=AssetSelection.assets(bronze_summoner_data),
    description="Materializes all bronze-layer Riot Games assets.",
)
