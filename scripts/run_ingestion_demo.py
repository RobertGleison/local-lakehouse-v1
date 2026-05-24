import os
import sys
import logging
from unittest.mock import patch, MagicMock

# Enable info logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("run_ingestion_demo")

# Simple custom helper to load local .env if present
def load_dotenv():
    env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
    if os.path.exists(env_path):
        logger.info(f"Loading environment variables from {env_path}")
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    # Strip quotes if present
                    v = v.strip("'\"")
                    os.environ[k] = v

# Load environment
load_dotenv()

# Add repo root to python path so core modules can be imported
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.riot_ingestion import riot_source, create_minio_pipeline

def run_pipeline():
    api_key = os.environ.get("LOL_API_KEY")
    
    # 1. Determine if we are running with a real Riot Games API key
    is_mock = not api_key or api_key.startswith("RGAPI-mock") or len(api_key) < 10
    
    if is_mock:
        logger.warning("No valid 'LOL_API_KEY' found in environment. Running ingestion in MOCK mode...")
        # Mock RiotClient to simulate API responses for dry-run
        mock_client = MagicMock()
        mock_client.get_summoner_by_name.return_value = {
            "id": "summoner-demo-id",
            "accountId": "account-demo-id",
            "puuid": "puuid-demo-faker-12345",
            "name": "Faker",
            "profileIconId": 6,
            "revisionDate": 1716544983,
            "summonerLevel": 700
        }
        mock_client.get_match_ids_by_puuid.return_value = ["MOCK_BR1_001", "MOCK_BR1_002"]
        mock_client.get_match_details.side_effect = lambda match_id: {
            "metadata": {
                "dataVersion": "2",
                "matchId": match_id,
                "participants": ["puuid-demo-faker-12345"]
            },
            "info": {
                "gameCreation": 1716545000,
                "gameDuration": 1800,
                "gameEndTimestamp": 1716546800,
                "gameId": 12345678,
                "gameMode": "CLASSIC",
                "gameType": "MATCHED_GAME"
            }
        }
        
        patcher = patch("core.riot_ingestion.RiotClient", return_value=mock_client)
        patcher.start()
        
    else:
        logger.info("Valid 'LOL_API_KEY' found! Running ingestion in LIVE mode...")

    # 2. Initialize the dlt pipeline with local MinIO targets
    logger.info("Initializing dlt pipeline targeting local MinIO Bronze layer...")
    pipeline = create_minio_pipeline(
        pipeline_name="riot_bronze_ingest",
        dataset_name="league_of_legends"
    )

    # 3. Create the Riot dlt source (ingesting summoner profiles + 2 recent match details)
    logger.info("Running dlt source stream...")
    summoner_names = ["Doublelift"] if not is_mock else ["Faker"]
    source = riot_source(summoner_names=summoner_names, region="br1", match_count=2)

    try:
        # 4. Execute the pipeline and load it as Parquet format
        load_info = pipeline.run(source, loader_file_format="parquet")
        
        logger.info("\n==========================================")
        logger.info("INGESTION DEMO PIPELINE RUN COMPLETE SUCCESS!")
        logger.info("==========================================")
        logger.info(f"Pipeline Name: {pipeline.pipeline_name}")
        logger.info(f"Dataset Name: {pipeline.dataset_name}")
        logger.info(f"Destination: {pipeline.destination.__class__.__name__}")
        logger.info(f"Loaded Tables: {list(pipeline.default_schema.data_tables())}")
        logger.info(f"Load ID: {load_info.loads_ids[0]}")
        logger.info("==========================================\n")
        
        if is_mock:
            patcher.stop()
            
    except Exception as e:
        logger.error(f"Failed to run the ingestion pipeline: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    run_pipeline()
