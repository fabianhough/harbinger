"""Configuration: config.yaml next to the checkout, with env overrides for secrets."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_WRITABLE_SLOTS = ["news", "notices"]
DEFAULT_GBFS_URL = "https://gbfs.citibikenyc.com/gbfs/gbfs.json"
DEFAULT_USER_AGENT = "harbinger (https://github.com/fabianhough/harbinger)"
DEFAULT_JACKET_THRESHOLDS_F = [40.0, 55.0, 68.0]


@dataclass
class BikesConfig:
    origins: list[str]
    destinations: list[str]
    gbfs_url: str = DEFAULT_GBFS_URL


@dataclass
class WeatherConfig:
    lat: float
    lon: float
    user_agent: str = DEFAULT_USER_AGENT
    jacket_thresholds_f: list[float] = field(default_factory=lambda: list(DEFAULT_JACKET_THRESHOLDS_F))


@dataclass
class LineConfig:
    route: str
    stop: str
    labels: dict[str, str] = field(default_factory=dict)


@dataclass
class TransitConfig:
    station_name: str
    directions: dict[str, str]
    lines: list[LineConfig]


@dataclass
class Config:
    host: str = "0.0.0.0"
    port: int = 8080
    agent_token: str | None = None
    writable_slots: list[str] = field(default_factory=lambda: list(DEFAULT_WRITABLE_SLOTS))
    snapshot: Path = Path("var/state.json")
    web_dir: Path = Path("web")
    bikes: BikesConfig | None = None
    weather: WeatherConfig | None = None
    transit: TransitConfig | None = None


def _bikes(data: dict | None) -> BikesConfig | None:
    if not data:
        return None
    return BikesConfig(
        origins=[str(s) for s in data.get("origins", [])],
        destinations=[str(s) for s in data.get("destinations", [])],
        gbfs_url=str(data.get("gbfs_url", DEFAULT_GBFS_URL)),
    )


def _weather(data: dict | None) -> WeatherConfig | None:
    if not data:
        return None
    thresholds = data.get("jacket_thresholds_f") or DEFAULT_JACKET_THRESHOLDS_F
    if len(thresholds) != 3:
        raise ValueError("weather.jacket_thresholds_f needs exactly three values, ascending")
    return WeatherConfig(
        lat=float(data["lat"]),
        lon=float(data["lon"]),
        user_agent=str(data.get("user_agent", DEFAULT_USER_AGENT)),
        jacket_thresholds_f=sorted(float(t) for t in thresholds),
    )


def _transit(data: dict | None) -> TransitConfig | None:
    if not data:
        return None
    lines = [
        LineConfig(route=str(l["route"]), stop=str(l["stop"]), labels={str(k): str(v) for k, v in (l.get("labels") or {}).items()})
        for l in data.get("lines", [])
    ]
    if not lines:
        raise ValueError("transit.lines is empty")
    return TransitConfig(
        station_name=str(data.get("station_name", "")),
        directions={str(k): str(v) for k, v in (data.get("directions") or {}).items()},
        lines=lines,
    )


def load_config(path: str | os.PathLike | None = None) -> Config:
    """Load config.yaml (or $HARBINGER_CONFIG, or the given path).

    Relative paths inside the file resolve against the file's own directory. When no
    file exists the defaults apply, relative to the current directory. The agent
    token may also come from HARBINGER_AGENT_TOKEN, which wins over the file.
    """
    p = Path(path or os.environ.get("HARBINGER_CONFIG") or "config.yaml")
    data: dict = {}
    root = Path.cwd()
    if p.exists():
        data = yaml.safe_load(p.read_text()) or {}
        root = p.resolve().parent

    server = data.get("server") or {}
    agent = data.get("agent") or {}
    state = data.get("state") or {}
    web = data.get("web") or {}

    token = os.environ.get("HARBINGER_AGENT_TOKEN") or agent.get("token")
    if token in ("", "change-me"):
        token = None

    return Config(
        host=str(server.get("host", "0.0.0.0")),
        port=int(server.get("port", 8080)),
        agent_token=token,
        writable_slots=list(agent.get("writable_slots", DEFAULT_WRITABLE_SLOTS)),
        snapshot=root / state.get("snapshot", "var/state.json"),
        web_dir=root / web.get("dir", "web"),
        bikes=_bikes(data.get("bikes")),
        weather=_weather(data.get("weather")),
        transit=_transit(data.get("transit")),
    )
