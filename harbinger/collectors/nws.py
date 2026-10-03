"""National Weather Service forecasts and the jacket / rain verdicts. See docs/sources/nws-weather.md."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import datetime, timedelta, timezone

import httpx2 as httpx

from ..config import WeatherConfig
from ..state import now_iso
from .base import Collector

log = logging.getLogger("harbinger.collectors.nws")

API = "https://api.weather.gov"
POINTS_TTL_S = 86400
HOURS = 18
JACKET_WINDOW_H = 12
WET_POP = 40

KIND_RULES = (
    ("storm", ("thunder",)),
    ("snow", ("snow", "sleet", "flurr", "ice", "wintry")),
    ("rain", ("rain", "shower", "drizzle")),
    ("fog", ("fog", "haze", "mist", "smoke")),
    ("cloudy", ("cloudy", "overcast")),
)
INCLEMENT = {"rain", "snow", "storm"}
KIND_WORD = {"rain": "Rain", "snow": "Snow", "storm": "Storms"}

_DURATION = re.compile(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?)?$")


# ---------- pure helpers ----------

def classify(short_forecast: str) -> str:
    s = short_forecast.lower()
    for kind, words in KIND_RULES:
        if any(w in s for w in words):
            return kind
    return "clear"


def parse_iso_duration(s: str) -> timedelta:
    m = _DURATION.match(s)
    if not m:
        raise ValueError(f"unsupported ISO 8601 duration {s!r}")
    d, h, mi = (int(x) if x else 0 for x in m.groups())
    return timedelta(days=d, hours=h, minutes=mi)


def expand_grid_values(values: list[dict]) -> dict[datetime, float]:
    """Run-length encoded gridpoint values to one entry per hour, keyed by UTC datetime."""
    out: dict[datetime, float] = {}
    for v in values:
        if v.get("value") is None:
            continue
        start_s, dur_s = v["validTime"].split("/")
        start = datetime.fromisoformat(start_s).astimezone(timezone.utc)
        hours = max(1, int(parse_iso_duration(dur_s).total_seconds() // 3600))
        for i in range(hours):
            out[start + timedelta(hours=i)] = float(v["value"])
    return out


def c_to_f(c: float) -> float:
    return c * 9 / 5 + 32


def fmt_hour(dt: datetime) -> str:
    return f"{dt.strftime('%I').lstrip('0')}{dt.strftime('%p').lower()}"


def rain_verdict(hourly: list[dict]) -> dict:
    """First wet span in the strip. Answer is a time range, 'Now to …', or 'None'."""
    wet = [h["pop"] >= WET_POP or h["kind"] in INCLEMENT for h in hourly]
    last = datetime.fromisoformat(hourly[-1]["t"]) + timedelta(hours=1)
    if not any(wet):
        peak = max(hourly, key=lambda h: h["pop"])
        detail = f"{peak['pop']}% at most, through {fmt_hour(last)}" if peak["pop"] > 0 else f"Dry through {fmt_hour(last)}"
        return {"answer": "None", "detail": detail[:80]}
    i = wet.index(True)
    j = i
    while j + 1 < len(wet) and wet[j + 1]:
        j += 1
    start = datetime.fromisoformat(hourly[i]["t"])
    end = datetime.fromisoformat(hourly[j]["t"]) + timedelta(hours=1)
    span = hourly[i:j + 1]
    peak = max(span, key=lambda h: h["pop"])
    kinds = {h["kind"] for h in span}
    word = KIND_WORD["snow"] if "snow" in kinds else KIND_WORD["storm"] if "storm" in kinds else KIND_WORD["rain"]
    answer = f"Now to {fmt_hour(end)}" if i == 0 else f"{fmt_hour(start)} to {fmt_hour(end)}"
    detail = f"{word} likely, {peak['pop']}% at {fmt_hour(datetime.fromisoformat(peak['t']))}"
    return {"answer": answer[:24], "detail": detail[:80]}


def jacket_verdict(feels: list[tuple[datetime, float]], thresholds: list[float]) -> dict:
    """Coldest feels-like over the window against three ascending thresholds."""
    if not feels:
        return {"answer": "?", "detail": "no apparent temperature data"}
    t, m = min(feels, key=lambda x: x[1])
    heavy_below, yes_below, light_below = thresholds
    if m >= light_below:
        answer = "No"
    elif m >= yes_below:
        answer = "Light"
    elif m >= heavy_below:
        answer = "Yes"
    else:
        answer = "Heavy"
    when = "now" if t == feels[0][0] else f"at {fmt_hour(t)}"
    return {"answer": answer, "detail": f"feels like {round(m)}° {when}"[:80]}


def alert_severity(event: str) -> str:
    e = event.lower()
    if "warning" in e:
        return "warning"
    if "watch" in e:
        return "watch"
    return "advisory"


def build_weather_slot(hourly_json: dict, grid_json: dict, daily_json: dict, alerts_json: dict,
                       now: datetime, thresholds: list[float], hours: int = HOURS) -> dict:
    """Pure assembly of the weather slot from the four NWS responses."""
    periods = hourly_json["properties"]["periods"]
    current = [p for p in periods if datetime.fromisoformat(p["endTime"]) > now][:hours]
    if not current:
        raise ValueError("hourly forecast has no periods after now")

    apparent = expand_grid_values(grid_json["properties"]["apparentTemperature"]["values"])

    def feels_at(dt: datetime) -> float | None:
        v = apparent.get(dt.astimezone(timezone.utc))
        return c_to_f(v) if v is not None else None

    hourly = []
    feels: list[tuple[datetime, float]] = []
    for p in current:
        t = datetime.fromisoformat(p["startTime"])
        pop = (p.get("probabilityOfPrecipitation") or {}).get("value")
        hourly.append({
            "t": p["startTime"],
            "temp_f": p["temperature"],
            "pop": int(pop or 0),
            "kind": classify(p["shortForecast"]),
            "short": p["shortForecast"][:40],
        })
        if len(feels) < JACKET_WINDOW_H:
            f = feels_at(t)
            feels.append((t, f if f is not None else float(p["temperature"])))

    first = current[0]
    t0 = datetime.fromisoformat(first["startTime"])
    feels0 = feels_at(t0)
    wind = f"{first.get('windSpeed', '')} {first.get('windDirection', '')}".strip()
    now_block = {
        "temp_f": first["temperature"],
        "feels_f": round(feels0 if feels0 is not None else first["temperature"]),
        "short": first["shortForecast"][:40],
    }
    if wind:
        now_block["wind"] = wind[:24]

    # Today's high comes from the daily forecast's daytime period when it is still
    # listed (it covers the whole day, including hours already past); the low from
    # tonight's period. Hourly data fills in when the daily periods have moved on.
    today = t0.date()
    daily = daily_json["properties"]["periods"]
    todays = [p for p in daily if datetime.fromisoformat(p["startTime"]).date() == today]
    day_p = next((p for p in todays if p["isDaytime"]), None)
    night_p = next((p for p in todays if not p["isDaytime"]), None)
    today_block = {
        "high_f": day_p["temperature"] if day_p else max(h["temp_f"] for h in hourly),
        "low_f": night_p["temperature"] if night_p else min(h["temp_f"] for h in hourly),
        "narrative": (daily[0]["detailedForecast"] if daily else "")[:240],
    }

    alerts = []
    for f in alerts_json.get("features", []):
        props = f.get("properties") or {}
        event = str(props.get("event") or "Alert")
        ends = props.get("ends") or props.get("expires")
        headline = f"{event} until {fmt_hour(datetime.fromisoformat(ends).astimezone(t0.tzinfo))}" if ends else event
        item = {"headline": headline[:120], "severity": alert_severity(event)}
        if props.get("onset"):
            item["onset"] = props["onset"]
        if ends:
            item["ends"] = ends
        alerts.append(item)

    return {
        "updated_at": now_iso(),
        "source": "nws",
        "verdicts": {"umbrella": rain_verdict(hourly), "jacket": jacket_verdict(feels, thresholds)},
        "now": now_block,
        "hourly": hourly,
        "today": today_block,
        "alerts": alerts,
    }


# ---------- collector ----------

class NWSCollector(Collector):
    name = "nws"
    slot = "weather"
    interval_s = 1800.0

    def __init__(self, cfg: WeatherConfig):
        self.cfg = cfg
        self._points: dict | None = None
        self._points_at = 0.0

    @property
    def headers(self) -> dict[str, str]:
        return {"User-Agent": self.cfg.user_agent, "Accept": "application/geo+json"}

    async def _get(self, client: httpx.AsyncClient, url: str) -> dict:
        r = await client.get(url, headers=self.headers)
        r.raise_for_status()
        return r.json()

    async def points(self, client: httpx.AsyncClient) -> dict:
        if self._points is None or time.monotonic() - self._points_at > POINTS_TTL_S:
            data = await self._get(client, f"{API}/points/{self.cfg.lat:.4f},{self.cfg.lon:.4f}")
            self._points = data["properties"]
            self._points_at = time.monotonic()
        return self._points

    async def fetch(self, client: httpx.AsyncClient) -> dict:
        pts = await self.points(client)
        hourly, grid, daily, alerts = await asyncio.gather(
            self._get(client, pts["forecastHourly"]),
            self._get(client, pts["forecastGridData"]),
            self._get(client, pts["forecast"]),
            self._get(client, f"{API}/alerts/active?point={self.cfg.lat:.4f},{self.cfg.lon:.4f}"),
        )
        now = datetime.now(timezone.utc)
        return build_weather_slot(hourly, grid, daily, alerts, now, self.cfg.jacket_thresholds_f)
