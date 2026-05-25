import os
import logging
import dlt
from typing import List, Optional, Iterator, Dict, Any
from core.riot_client import RiotClient

logger = logging.getLogger("riot_ingestion")
logger.setLevel(logging.INFO)

@dlt.source(name="riot_api_source")
def riot_source(summoner_names: List[str], region: str = "br1", match_count: int = 5) -> Any:
    """
    Riot Games dlt source. Takes a list of summoner names, resolves them to PUUIDs,
    and grabs recent match details.
    """
    client = RiotClient(region=region)

    @dlt.resource(name="summoners", write_disposition="merge", primary_key="id")
    def summoners() -> Iterator[Dict[str, Any]]:
        """Fetch basic summoner profiles for the given names."""
        for name in summoner_names:
            try:
                summoner = client.get_summoner_by_name(name)
                yield summoner
            except Exception as e:
                logger.error(f"Failed to fetch summoner '{name}': {e}")

    @dlt.transformer(data_from=summoners, name="match_ids", write_disposition="append")
    def match_ids(summoner_record: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
        """Fetch recent match IDs for each summoner's PUUID."""
        puuid = summoner_record.get("puuid")
        name = summoner_record.get("name")
        if not puuid:
            logger.warning(f"No PUUID found for summoner record: {summoner_record}")
            return
        
        try:
            m_ids = client.get_match_ids_by_puuid(puuid, count=match_count)
            logger.info(f"Found {len(m_ids)} match IDs for summoner '{name}'")
            for m_id in m_ids:
                yield {
                    "summoner_name": name,
                    "puuid": puuid,
                    "match_id": m_id
                }
        except Exception as e:
            logger.error(f"Failed to fetch match IDs for puuid {puuid}: {e}")

    @dlt.transformer(data_from=match_ids, name="match_details", write_disposition="merge", primary_key="match_id")
    def match_details(match_record: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
        """Fetch full game telemetry for each match ID."""
        match_id = match_record["match_id"]
        try:
            detail = client.get_match_details(match_id)
            
            # Extract important metadata at top level for easy partitioning/indexing
            # dlt's default flattener will also preserve the nested info block
            yield {
                "match_id": match_id,
                "summoner_name": match_record["summoner_name"],
                "puuid": match_record["puuid"],
                **detail
            }
        except Exception as e:
            logger.error(f"Failed to fetch match details for match {match_id}: {e}")

    return summoners, match_ids, match_details


def create_minio_pipeline(
    pipeline_name: str = "riot_lakehouse_ingest",
    dataset_name: str = "league_of_legends",
    minio_settings: Optional["MinioSettings"] = None,
) -> dlt.Pipeline:
    """
    Creates and configures a dlt pipeline pointing to the local MinIO S3-compatible Bronze layer.
    Accepts an optional MinioSettings instance for testability; reads from environment by default.
    """
    from core.settings.minio_settings import MinioSettings as _MinioSettings
    settings = minio_settings or _MinioSettings()
    settings.apply_to_environment()

    return dlt.pipeline(
        pipeline_name=pipeline_name,
        destination="filesystem",
        dataset_name=dataset_name,
    )
