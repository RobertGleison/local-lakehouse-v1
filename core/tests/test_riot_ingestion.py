import pytest
from unittest.mock import MagicMock, patch
import requests
from core.riot_client import RiotClient
from core.riot_ingestion import riot_source

# Dummy API Key for testing
TEST_API_KEY = "RGAPI-mock-key"

@pytest.fixture
def mock_client():
    with patch.dict("os.environ", {"LOL_API_KEY": TEST_API_KEY}):
        return RiotClient(region="br1")


def test_riot_client_region_mapping():
    """Assert platform region correctly maps to global routing subdomain."""
    client_br = RiotClient(api_key=TEST_API_KEY, region="br1")
    assert client_br.routing_region == "americas"

    client_eu = RiotClient(api_key=TEST_API_KEY, region="euw1")
    assert client_eu.routing_region == "europe"

    client_kr = RiotClient(api_key=TEST_API_KEY, region="kr")
    assert client_kr.routing_region == "asia"


def test_riot_client_rate_limiting_retry():
    """Verify that RiotClient respects Retry-After headers when encountering HTTP 429."""
    client = RiotClient(api_key=TEST_API_KEY, max_retries=3)
    
    # Mock requests.Session.get
    mock_response_429 = MagicMock()
    mock_response_429.status_code = 429
    mock_response_429.headers = {"Retry-After": "0.1"}
    
    mock_response_200 = MagicMock()
    mock_response_200.status_code = 200
    mock_response_200.json.return_value = {"id": "123", "name": "FakeSummoner"}
    
    # Side effect: first call is 429, second is 200 success
    with patch.object(client.session, "get", side_effect=[mock_response_429, mock_response_200]) as mock_get:
        # Patch sleep to make test run instantly
        with patch("time.sleep") as mock_sleep:
            res = client.get_summoner_by_name("FakeSummoner")
            
            # Assertions
            assert res == {"id": "123", "name": "FakeSummoner"}
            assert mock_get.call_count == 2
            # Sleep was called once with the float representation of Retry-After (0.1) + buffer (0.5)
            mock_sleep.assert_called_once_with(0.6)


@patch("core.riot_ingestion.RiotClient")
def test_riot_source_yields_expected_resources(mock_client_class):
    """
    Verify that the dlt source correctly traverses:
    summoners -> match_ids -> match_details
    """
    # 1. Setup mock returns for the RiotClient instance
    mock_client_instance = mock_client_class.return_value
    
    mock_client_instance.get_summoner_by_name.return_value = {
        "id": "summoner-1",
        "puuid": "puuid-abc-123",
        "name": "Faker"
    }
    
    mock_client_instance.get_match_ids_by_puuid.return_value = ["BR1_111", "BR1_222"]
    
    mock_client_instance.get_match_details.side_effect = lambda m_id: {
        "metadata": {"matchId": m_id},
        "info": {"gameMode": "CLASSIC"}
    }
    
    # 2. Build the dlt source
    source = riot_source(["Faker"], region="br1", match_count=2)
    
    # Extract the individual resources from the source container
    summoners_res, match_ids_res, match_details_res = source.resources.values()
    
    # 3. Test Summoners resource
    summoners_list = list(summoners_res)
    assert len(summoners_list) == 1
    assert summoners_list[0]["name"] == "Faker"
    assert summoners_list[0]["puuid"] == "puuid-abc-123"
    
    # 4. Test Match IDs transformer (requires output of summoners)
    match_ids_list = list(match_ids_res._pipe.gen(summoners_list[0]))
    assert len(match_ids_list) == 2
    assert match_ids_list[0]["match_id"] == "BR1_111"
    assert match_ids_list[1]["match_id"] == "BR1_222"
    assert match_ids_list[0]["summoner_name"] == "Faker"
    
    # 5. Test Match Details transformer (requires output of match_ids)
    match_details_list = list(match_details_res._pipe.gen(match_ids_list[0]))
    assert len(match_details_list) == 1
    assert match_details_list[0]["match_id"] == "BR1_111"
    assert match_details_list[0]["metadata"]["matchId"] == "BR1_111"
    assert match_details_list[0]["info"]["gameMode"] == "CLASSIC"
