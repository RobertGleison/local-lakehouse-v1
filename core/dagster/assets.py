import os
from typing import Any
from dagster import asset, Output, AssetExecutionContext
from core.riot_ingestion import riot_source, create_minio_pipeline
from core.dagster.resources import MinioResource


@asset(
    group_name="bronze",
    description="Ingests raw Riot Games summoner and match telemetry, loading it as Parquet files in the MinIO Bronze layer.",
    required_resource_keys={"minio"},
)
def bronze_summoner_data(context: AssetExecutionContext) -> Output[Any]:
    summoner_names = ["Doublelift"]
    context.log.info(f"Starting bronze ingestion for summoners: {summoner_names}")

    api_key = os.environ.get("LOL_API_KEY", "")
    is_mock = not api_key or api_key.startswith("RGAPI-mock") or len(api_key) < 10

    if is_mock:
        context.log.warning("No valid 'LOL_API_KEY' found. Ingesting in mock/dry-run mode.")
        summoner_names = ["Faker"]

    minio_resource: MinioResource = context.resources.minio
    minio_settings = minio_resource.get_settings()

    pipeline = create_minio_pipeline(
        pipeline_name="riot_bronze_ingest",
        dataset_name="league_of_legends",
        minio_settings=minio_settings,
    )

    if is_mock:
        from unittest.mock import patch, MagicMock
        mock_client = MagicMock()
        mock_client.get_summoner_by_name.return_value = {
            "id": "summoner-demo-id",
            "accountId": "account-demo-id",
            "puuid": "puuid-demo-faker-12345",
            "name": "Faker",
            "summonerLevel": 700,
        }
        mock_client.get_match_ids_by_puuid.return_value = ["MOCK_BR1_001", "MOCK_BR1_002"]
        mock_client.get_match_details.side_effect = lambda match_id: {
            "metadata": {"dataVersion": "2", "matchId": match_id, "participants": ["puuid-demo-faker-12345"]},
            "info": {"gameCreation": 1716545000, "gameDuration": 1800, "gameMode": "CLASSIC"},
        }
        patcher = patch("core.riot_ingestion.RiotClient", return_value=mock_client)
        patcher.start()

    source = riot_source(summoner_names=summoner_names, region="br1", match_count=2)
    context.log.info("Running dlt S3 pipeline...")
    load_info = pipeline.run(source, loader_file_format="parquet")

    if is_mock:
        patcher.stop()

    context.log.info(f"Ingestion successful! Load ID: {load_info.loads_ids[0]}")

    return Output(
        value=load_info,
        metadata={
            "load_id": load_info.loads_ids[0],
            "dataset_name": pipeline.dataset_name,
            "pipeline_name": pipeline.pipeline_name,
            "destination": pipeline.destination.__class__.__name__,
            "tables_loaded": ", ".join(list(pipeline.default_schema.data_tables())),
        },
    )
