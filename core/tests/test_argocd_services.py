import json
from pathlib import Path

SERVICES_FILE = Path(__file__).parents[1] / "argocd" / "services" / "services.json"
REQUIRED_FIELDS = {"service", "path", "wave"}


def load_services():
    with open(SERVICES_FILE) as f:
        data = json.load(f)
    return data["applications"]


def test_services_json_is_valid():
    services = load_services()
    assert len(services) > 0


def test_all_services_have_required_fields():
    for svc in load_services():
        missing = REQUIRED_FIELDS - svc.keys()
        assert not missing, f"{svc.get('service', '?')} missing fields: {missing}"


def test_service_names_are_unique():
    names = [s["service"] for s in load_services()]
    assert len(names) == len(set(names)), "Duplicate service names found"


def test_wave_values_are_numeric_strings():
    for svc in load_services():
        assert svc["wave"].isdigit(), f"{svc['service']} has non-numeric wave: {svc['wave']}"


def test_paths_follow_convention():
    for svc in load_services():
        path = svc["path"]
        # secrets entry is the only exception
        if svc["service"] == "local-lakehouse-secrets":
            continue
        assert path.startswith("infra/"), f"{svc['service']} path should start with 'infra/': {path}"
        assert path.endswith("/application"), f"{svc['service']} path should end with '/application': {path}"
