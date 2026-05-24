import os
import time
import logging
import requests
from typing import Dict, Any, List, Optional

# Setup basic logging
logger = logging.getLogger("riot_client")
logger.setLevel(logging.INFO)

# Map platform regions to routing regions (Match v5 API uses global routing regions)
REGION_MAP = {
    "br1": "americas",
    "na1": "americas",
    "la1": "americas",
    "la2": "americas",
    "euw1": "europe",
    "eun1": "europe",
    "tr1": "europe",
    "ru": "europe",
    "kr": "asia",
    "jp1": "asia",
    "oc1": "sea",
    "ph2": "sea",
    "sg2": "sea",
    "th2": "sea",
    "tw2": "sea",
    "vn2": "sea",
}

class RiotClient:
    """
    Riot Games API Client with built-in rate-limiting resilience and region mapping.
    """
    def __init__(self, api_key: Optional[str] = None, region: str = "br1", max_retries: int = 5):
        self.api_key = api_key or os.environ.get("LOL_API_KEY")
        if not self.api_key:
            raise ValueError("Riot Games API Key (LOL_API_KEY) must be provided or set in environment variables.")
        
        self.region = region.lower()
        self.routing_region = REGION_MAP.get(self.region, "americas")
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update({"X-Riot-Token": self.api_key})

    def _get_base_url(self, global_endpoint: bool = False) -> str:
        """Get the base URL for the API calls. Match/v5 uses routing region, Summoner uses platform region."""
        region_subdomain = self.routing_region if global_endpoint else self.region
        return f"https://{region_subdomain}.api.riotgames.com"

    def request(self, path: str, params: Optional[Dict[str, Any]] = None, global_endpoint: bool = False) -> Dict[str, Any]:
        """
        Executes an HTTP GET request with retries and rate limit handling.
        """
        base_url = self._get_base_url(global_endpoint)
        url = f"{base_url}{path}"
        
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(f"Requesting: {url} (Params: {params}) - Attempt {attempt}")
                response = self.session.get(url, params=params, timeout=10)
                
                # Check for rate limits (HTTP 429)
                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    sleep_time = float(retry_after) if retry_after else (2 ** attempt)
                    # Add a small buffer to avoid hitting it again immediately
                    sleep_time += 0.5
                    logger.warning(f"Riot API Rate Limit Hit (429). Retrying after {sleep_time:.2f} seconds...")
                    time.sleep(sleep_time)
                    continue
                
                # Raise error for other non-200 responses
                response.raise_for_status()
                return response.json()
                
            except requests.exceptions.RequestException as e:
                logger.error(f"HTTP request error on attempt {attempt}: {e}")
                if attempt == self.max_retries:
                    raise e
                # Exponential backoff for typical network drops / 5xx server issues
                sleep_time = 2 ** attempt
                logger.info(f"Retrying network error in {sleep_time} seconds...")
                time.sleep(sleep_time)
        
        raise RuntimeError(f"Failed to fetch data from {url} after {self.max_retries} attempts.")

    def get_summoner_by_name(self, summoner_name: str) -> Dict[str, Any]:
        """
        Fetches detailed summoner information by name.
        Uses platform subdomain (e.g. br1.api.riotgames.com).
        """
        path = f"/lol/summoner/v4/summoners/by-name/{summoner_name}"
        return self.request(path, global_endpoint=False)

    def get_match_ids_by_puuid(self, puuid: str, start: int = 0, count: int = 20) -> List[str]:
        """
        Fetches list of match IDs for a given summoner's PUUID.
        Uses global routing subdomain (e.g. americas.api.riotgames.com).
        """
        path = f"/lol/match/v5/matches/by-puuid/{puuid}/ids"
        params = {"start": start, "count": count}
        # In Match v5, this returns a JSON list of strings (match IDs)
        # requests.json() will be a List[str] rather than a Dict
        return self.request(path, params=params, global_endpoint=True)  # type: ignore

    def get_match_details(self, match_id: str) -> Dict[str, Any]:
        """
        Fetches detailed game state for a specific match ID.
        Uses global routing subdomain (e.g. americas.api.riotgames.com).
        """
        path = f"/lol/match/v5/matches/{match_id}"
        return self.request(path, global_endpoint=True)
