import json
from pathlib import Path

import pytest

from harbinger.collectors.citibike import build_bikes_slot, feed_urls, haversine_m, search_stations
from harbinger.state import StateStore

FIX = Path(__file__).parent / "fixtures"
INFO = {s["station_id"]: s for s in json.loads((FIX / "citibike_station_information.json").read_text())["data"]["stations"]}
STATUS = json.loads((FIX / "citibike_station_status.json").read_text())
ORIGINS = ["64f0f28c-bedc-42d5-b107-ecdd48fc30cd", "904930bd-2671-4695-9c1a-8a894b041129"]
DESTS = ["66dc292c-0aca-11e7-82f6-3863bb44ef7c", "66dca682-0aca-11e7-82f6-3863bb44ef7c"]


def test_feed_urls_from_discovery():
    gbfs = json.loads((FIX / "citibike_gbfs.json").read_text())
    urls = feed_urls(gbfs)
    assert set(urls) == {"station_information", "station_status"}
    assert urls["station_status"].endswith("station_status.json")


def test_build_slot_matches_schema_and_roles():
    slot = build_bikes_slot(INFO, STATUS, ORIGINS, DESTS)
    StateStore(None).set_slot("bikes", slot)  # raises if invalid
    assert [s["role"] for s in slot["stations"]] == ["origin", "origin", "destination", "destination"]
    assert slot["stations"][0]["name"] == "Broadway & W 48 St"


def test_classic_excludes_ebikes():
    by_id = {s["station_id"]: s for s in STATUS["data"]["stations"]}
    slot = build_bikes_slot(INFO, STATUS, ORIGINS, [])
    for s, sid in zip(slot["stations"], ORIGINS):
        raw = by_id[sid]
        assert s["ebike"] == raw["num_ebikes_available"]
        assert s["classic"] == raw["num_bikes_available"] - raw["num_ebikes_available"]
        assert s["docks"] == raw["num_docks_available"]
        assert s["renting"] is True


def test_unknown_station_is_a_config_error():
    with pytest.raises(ValueError, match="unknown Citi Bike station_id"):
        build_bikes_slot(INFO, STATUS, ["nope"], [])


def test_station_missing_from_status_is_skipped():
    status = {"data": {"stations": [s for s in STATUS["data"]["stations"] if s["station_id"] != ORIGINS[0]]}}
    slot = build_bikes_slot(INFO, status, ORIGINS, [])
    assert [s["name"] for s in slot["stations"]] == ["6 Ave & W 45 St"]


def test_search_by_name_and_distance():
    stations = list(INFO.values())
    assert [s["name"] for s in search_stations(stations, query="w 45")] == ["6 Ave & W 45 St", "W 45 St & 8 Ave"]
    near = search_stations(stations, near=(40.7580, -73.9855), limit=2)
    assert near[0]["distance_m"] <= near[1]["distance_m"]
    assert haversine_m(40.7580, -73.9855, 40.7580, -73.9855) == 0
