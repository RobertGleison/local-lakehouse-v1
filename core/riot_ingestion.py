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


def create_minio_pipeline(pipeline_name: str = "riot_lakehouse_ingest", dataset_name: str = "league_of_legends") -> dlt.Pipeline:
    """
    Creates and configures a dlt pipeline pointing to the local MinIO S3-compatible Bronze layer.
    """
    # Standard MinIO defaults for local k3d datalake environment
    minio_endpoint = os.environ.get("MINIO_ENDPOINT_URL", "http://localhost:9000")
    aws_access_key = os.environ.get("MINIO_ROOT_USER", "minioadmin")
    aws_secret_key = os.environ.get("MINIO_ROOT_PASSWORD", "minioadmin123")
    bucket_url = os.environ.get("BRONZE_BUCKET_URL", "s3://bronze")

    # Set dlt expected environment variables if not already explicitly set in environment
    os.environ.setdefault("DESTINATION__FILESYSTEM__BUCKET_URL", bucket_url)
    os.environ.setdefault("DESTINATION__FILESYSTEM__CREDENTIALS__AWS_ACCESS_KEY_ID", aws_access_key)
    os.environ.setdefault("DESTINATION__FILESYSTEM__CREDENTIALS__AWS_SECRET_ACCESS_KEY", aws_secret_key)
    os.environ.setdefault("DESTINATION__FILESYSTEM__CREDENTIALS__ENDPOINT_URL", minio_endpoint)
    
    # Configure fsspec/s3fs behavior (use custom endpoints for S3 destination)
    # This prevents boto3 from trying to verify SSL or use AWS global endpoints
    os.environ.setdefault("DESTINATION__FILESYSTEM__CREDENTIALS__AWS_SESSION_TOKEN", "")
    os.environ.setdefault("DESTINATION__FILESYSTEM__CREDENTIALS__VERIFY", "False")

    return dlt.pipeline(
        pipeline_name=pipeline_name,
        destination="filesystem",
        dataset_name=dataset_name
    )
