import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from harbinger.collectors.nws import (
    alert_severity, build_weather_slot, classify, expand_grid_values, fmt_hour,
    jacket_verdict, parse_iso_duration, rain_verdict,
)
from harbinger.state import StateStore

FIX = Path(__file__).parent / "fixtures"
HOURLY = json.loads((FIX / "nws_hourly.json").read_text())
GRID = json.loads((FIX / "nws_gridpoint.json").read_text())
DAILY = json.loads((FIX / "nws_daily.json").read_text())
NO_ALERTS = {"features": []}
THRESHOLDS = [40.0, 55.0, 68.0]
EDT = timezone(timedelta(hours=-4))


def hours(spec):
    """spec: list of (pop, kind) starting at 3pm local."""
    t0 = datetime(2026, 10, 3, 15, tzinfo=EDT)
    return [{"t": (t0 + timedelta(hours=i)).isoformat(), "temp_f": 60, "pop": pop, "kind": kind}
            for i, (pop, kind) in enumerate(spec)]


@pytest.mark.parametrize("short,kind", [
    ("Sunny", "clear"), ("Mostly Sunny", "clear"), ("Partly Cloudy", "cloudy"), ("Mostly Cloudy", "cloudy"),
    ("Chance Showers", "rain"), ("Rain Likely", "rain"), ("Slight Chance Drizzle", "rain"),
    ("Chance Showers And Thunderstorms", "storm"), ("Snow Showers", "snow"), ("Sleet", "snow"),
    ("Patchy Fog", "fog"), ("Haze", "fog"),
])
def test_classify(short, kind):
    assert classify(short) == kind


def test_parse_iso_duration():
    assert parse_iso_duration("PT1H") == timedelta(hours=1)
    assert parse_iso_duration("PT18H") == timedelta(hours=18)
    assert parse_iso_duration("P1DT6H") == timedelta(days=1, hours=6)
    with pytest.raises(ValueError):
        parse_iso_duration("1H")


def test_expand_grid_values_runs_length():
    out = expand_grid_values([{"validTime": "2026-10-03T12:00:00+00:00/PT3H", "value": 10.0},
                              {"validTime": "2026-10-03T15:00:00+00:00/PT1H", "value": None}])
    keys = sorted(out)
    assert len(keys) == 3 and keys[0] == datetime(2026, 10, 3, 12, tzinfo=timezone.utc)
    assert all(v == 10.0 for v in out.values())


def test_fmt_hour():
    assert fmt_hour(datetime(2026, 10, 3, 22, tzinfo=EDT)) == "10pm"
    assert fmt_hour(datetime(2026, 10, 4, 0, tzinfo=EDT)) == "12am"
    assert fmt_hour(datetime(2026, 10, 4, 9, tzinfo=EDT)) == "9am"


def test_rain_verdict_none():
    v = rain_verdict(hours([(0, "clear")] * 6))
    assert v["answer"] == "None" and v["detail"].startswith("Dry through")
    v = rain_verdict(hours([(5, "clear"), (20, "cloudy")]))
    assert v["answer"] == "None" and "20%" in v["detail"]


def test_rain_verdict_span_by_pop_or_kind():
    v = rain_verdict(hours([(0, "clear"), (10, "cloudy"), (55, "rain"), (65, "rain"), (30, "cloudy"), (45, "cloudy")]))
    assert v["answer"] == "5pm to 7pm"       # first span only: 5pm and 6pm hours
    assert v["detail"] == "Rain likely, 65% at 6pm"
    v = rain_verdict(hours([(0, "clear"), (20, "snow")]))  # kind alone is enough
    assert v["answer"] == "4pm to 5pm" and v["detail"].startswith("Snow")


def test_rain_verdict_now():
    v = rain_verdict(hours([(70, "storm"), (60, "rain"), (0, "clear")]))
    assert v["answer"] == "Now to 5pm" and v["detail"].startswith("Storms")


def test_jacket_verdict_thresholds():
    t0 = datetime(2026, 10, 3, 15, tzinfo=EDT)
    series = lambda *vals: [(t0 + timedelta(hours=i), float(v)) for i, v in enumerate(vals)]
    assert jacket_verdict(series(70, 72), THRESHOLDS)["answer"] == "No"
    assert jacket_verdict(series(70, 60), THRESHOLDS) == {"answer": "Light", "detail": "feels like 60° at 4pm"}
    assert jacket_verdict(series(50, 65), THRESHOLDS) == {"answer": "Yes", "detail": "feels like 50° now"}
    assert jacket_verdict(series(39), THRESHOLDS)["answer"] == "Heavy"


def test_alert_severity():
    assert alert_severity("Wind Advisory") == "advisory"
    assert alert_severity("Flood Watch") == "watch"
    assert alert_severity("Severe Thunderstorm Warning") == "warning"


def test_build_slot_from_fixtures():
    first = datetime.fromisoformat(HOURLY["properties"]["periods"][0]["startTime"])
    now = first + timedelta(minutes=10)
    slot = build_weather_slot(HOURLY, GRID, DAILY, NO_ALERTS, now, THRESHOLDS)
    StateStore(None).set_slot("weather", slot)
    assert len(slot["hourly"]) == 18
    assert slot["hourly"][0]["t"] == first.isoformat()
    assert slot["now"]["temp_f"] == HOURLY["properties"]["periods"][0]["temperature"]
    assert slot["today"] == {"high_f": 71, "low_f": 57, "narrative": DAILY["properties"]["periods"][0]["detailedForecast"]}
    assert slot["verdicts"]["jacket"]["answer"] in {"No", "Light", "Yes", "Heavy"}
    assert slot["alerts"] == []


def test_build_slot_skips_past_periods_and_maps_alerts():
    first = datetime.fromisoformat(HOURLY["properties"]["periods"][0]["startTime"])
    now = first + timedelta(hours=3, minutes=30)
    alerts = {"features": [{"properties": {
        "event": "Wind Advisory", "severity": "Minor",
        "onset": "2026-10-03T18:00:00-04:00", "ends": "2026-10-03T22:00:00-04:00",
    }}]}
    slot = build_weather_slot(HOURLY, GRID, DAILY, alerts, now, THRESHOLDS)
    StateStore(None).set_slot("weather", slot)
    assert slot["hourly"][0]["t"] == HOURLY["properties"]["periods"][3]["startTime"]
    assert slot["alerts"] == [{"headline": "Wind Advisory until 10pm", "severity": "advisory",
                               "onset": "2026-10-03T18:00:00-04:00", "ends": "2026-10-03T22:00:00-04:00"}]
