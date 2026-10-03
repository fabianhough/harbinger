import json
from pathlib import Path

import pytest
from google.transit import gtfs_realtime_pb2

from harbinger.collectors.mta import ROUTE_FEED, arrivals_for, build_transit_slot, feed_url, parse_alerts
from harbinger.config import LineConfig, TransitConfig
from harbinger.state import StateStore

FIX = Path(__file__).parent / "fixtures"
ALERTS = json.loads((FIX / "mta_alerts.json").read_text())
NOW = 1_791_063_500.0  # inside the fixture's Delays alerts' active periods

CFG = TransitConfig(
    station_name="Jay St-MetroTech",
    directions={"N": "Manhattan", "S": "Brooklyn"},
    lines=[LineConfig("F", "A41"), LineConfig("A", "A41"), LineConfig("R", "R29", labels={"S": "Bay Ridge"})],
)


def feed(*trips):
    """trips: (route, [(stop_id, seconds_from_now), ...])"""
    msg = gtfs_realtime_pb2.FeedMessage()
    msg.header.gtfs_realtime_version = "1.0"
    msg.header.timestamp = int(NOW)
    for i, (route, stops) in enumerate(trips):
        e = msg.entity.add()
        e.id = f"t{i}"
        e.trip_update.trip.trip_id = f"trip{i}"
        e.trip_update.trip.route_id = route
        for sid, secs in stops:
            stu = e.trip_update.stop_time_update.add()
            stu.stop_id = sid
            stu.arrival.time = int(NOW + secs)
            stu.departure.time = int(NOW + secs)
    return msg


def test_feed_urls():
    assert feed_url("bdfm").endswith("nyct%2Fgtfs-bdfm")
    assert feed_url("").endswith("nyct%2Fgtfs")
    assert ROUTE_FEED["F"] == "bdfm" and ROUTE_FEED["G"] == "g" and ROUTE_FEED["1"] == ""


def test_arrivals_sorted_per_direction_and_filtered():
    msg = feed(
        ("F", [("A40N", 60), ("A41N", 600)]),
        ("F", [("A41N", 120), ("A41S", 1200)]),
        ("F", [("A41S", -120)]),          # left two minutes ago: dropped
        ("F", [("A41S", -20)]),           # at the platform: kept as ~0
        ("A", [("A41N", 30)]),            # other route: ignored
        ("F", [("R29N", 90)]),            # other stop: ignored
    )
    arr = arrivals_for(msg, "F", "A41", NOW)
    assert arr["N"] == [2.0, 10.0]
    assert arr["S"] == [-0.3, 20.0]


def test_arrivals_capped_at_six():
    msg = feed(*[("R", [("R29N", 60 * k)]) for k in range(1, 10)])
    assert arrivals_for(msg, "R", "R29", NOW)["N"] == [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]


def test_parse_alerts_from_fixture_scopes_and_filters():
    per = parse_alerts(ALERTS, {"A", "F", "R"}, {"A41", "R29"}, NOW)
    # Delay alerts name routes only: line scope on each route they mention.
    assert any(a["type"] == "Delays" and a["scope"] == "line" for a in per["A"])
    assert any(a["type"] == "Delays" and a["scope"] == "line" for a in per["F"])
    # Station notices and planned skips for other stations are dropped entirely.
    assert all(a["scope"] == "line" for route in per for a in per[route])
    assert not any("Sutphin" in a["header"] or "AirTrain" in a["header"] or "74 St" in a["header"]
                   for route in per for a in per[route])


def test_parse_alerts_station_scope_and_activity():
    alerts = {"entity": [
        {"id": "ours", "alert": {
            "informed_entity": [{"route_id": "A", "stop_id": "A41"}, {"route_id": "A", "stop_id": "A42"}],
            "active_period": [{"start": NOW - 10}],
            "header_text": {"translation": [{"text": "[A] trains skip Jay St-MetroTech", "language": "en"}]},
            "transit_realtime.mercury_alert": {"alert_type": "Planned - Stops Skipped"},
        }},
        {"id": "future", "alert": {
            "informed_entity": [{"route_id": "A"}],
            "active_period": [{"start": NOW + 3600}],
            "header_text": {"translation": [{"text": "later"}]},
        }},
        {"id": "expired", "alert": {
            "informed_entity": [{"route_id": "A"}],
            "active_period": [{"start": NOW - 7200, "end": NOW - 3600}],
            "header_text": {"translation": [{"text": "earlier"}]},
        }},
        {"id": "no-period", "alert": {
            "informed_entity": [{"route_id": "R"}],
            "header_text": {"translation": [{"text": "[R] always"}]},
        }},
    ]}
    per = parse_alerts(alerts, {"A", "R"}, {"A41"}, NOW)
    assert per["A"] == [{"type": "Planned - Stops Skipped", "header": "[A] trains skip Jay St-MetroTech", "scope": "station"}]
    assert per["R"] == [{"type": "Alert", "header": "[R] always", "scope": "line"}]


def test_build_transit_slot_validates():
    feeds = {
        "bdfm": feed(("F", [("A41N", 700), ("A41S", 300)])),
        "ace": feed(("A", [("A41N", 900)])),
        "nqrw": feed(("R", [("R29S", 100)])),
    }
    slot = build_transit_slot(CFG, feeds, ALERTS, NOW)
    StateStore(None).set_slot("transit", slot)
    assert slot["directions"] == {"N": "Manhattan", "S": "Brooklyn"}
    by_route = {l["route"]: l for l in slot["lines"]}
    assert by_route["F"]["directions"]["N"]["arrivals_min"] == [11.7]
    assert by_route["R"]["directions"]["S"] == {"label": "Bay Ridge", "arrivals_min": [1.7]}
    assert by_route["R"]["directions"]["N"] == {"label": "Manhattan", "arrivals_min": []}
    assert any(a["type"] == "Delays" for a in by_route["F"]["alerts"])
