"""Citi Bike via GBFS. See docs/sources/citibike.md."""

from __future__ import annotations

import logging
import math
import time
from datetime import datetime, timezone

import httpx2 as httpx

from ..config import BikesConfig
from ..state import now_iso
from .base import Collector

log = logging.getLogger("harbinger.collectors.citibike")

INFO_TTL_S = 86400


def iso_from_epoch(epoch: int | float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).astimezone().isoformat(timespec="seconds")


def feed_urls(gbfs: dict) -> dict[str, str]:
    """Map feed name to URL from a GBFS discovery document (1.x or 2.x shape)."""
    data = gbfs["data"]
    block = data.get("en") or next(iter(data.values()))
    return {f["name"]: f["url"] for f in block["feeds"]}


def build_bikes_slot(info: dict[str, dict], status_json: dict, origins: list[str], destinations: list[str]) -> dict:
    """Pure assembly of the bikes slot from station information and status."""
    by_id = {s["station_id"]: s for s in status_json["data"]["stations"]}
    stations = []
    for role, ids in (("origin", origins), ("destination", destinations)):
        for sid in ids:
            meta = info.get(sid)
            if meta is None:
                raise ValueError(f"unknown Citi Bike station_id {sid!r}; try `harbinger stations <name>`")
            st = by_id.get(sid)
            if st is None:
                log.warning("station %s (%s) missing from station_status; skipping", sid, meta.get("name"))
                continue
            bikes = int(st.get("num_bikes_available", 0))
            ebike = int(st.get("num_ebikes_available", 0))
            stations.append({
                "role": role,
                "name": str(meta["name"])[:40],
                "classic": max(0, bikes - ebike),
                "ebike": ebike,
                "docks": int(st.get("num_docks_available", 0)),
                "renting": bool(st.get("is_renting", 0)) and bool(st.get("is_installed", 1)),
                "reported_at": iso_from_epoch(int(st["last_reported"])),
            })
    if not stations:
        raise ValueError("no configured Citi Bike stations present in station_status")
    return {"updated_at": now_iso(), "stations": stations}


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def search_stations(stations: list[dict], query: str | None = None, near: tuple[float, float] | None = None, limit: int = 15) -> list[dict]:
    """Filter by name substring and/or sort by distance from a coordinate."""
    hits = stations
    if query:
        q = query.lower()
        hits = [s for s in hits if q in str(s.get("name", "")).lower()]
    if near:
        lat, lon = near
        hits = sorted(hits, key=lambda s: haversine_m(lat, lon, s["lat"], s["lon"]))
        hits = [{**s, "distance_m": round(haversine_m(lat, lon, s["lat"], s["lon"]))} for s in hits]
    else:
        hits = sorted(hits, key=lambda s: str(s.get("name", "")))
    return hits[:limit]


class CitiBikeCollector(Collector):
    name = "citibike"
    slot = "bikes"
    interval_s = 60.0

    def __init__(self, cfg: BikesConfig):
        self.cfg = cfg
        self._feeds: dict[str, str] | None = None
        self._info: dict[str, dict] = {}
        self._info_at = 0.0

    async def feeds(self, client: httpx.AsyncClient) -> dict[str, str]:
        if self._feeds is None:
            r = await client.get(self.cfg.gbfs_url)
            r.raise_for_status()
            self._feeds = feed_urls(r.json())
        return self._feeds

    async def station_info(self, client: httpx.AsyncClient) -> dict[str, dict]:
        if not self._info or time.monotonic() - self._info_at > INFO_TTL_S:
            feeds = await self.feeds(client)
            r = await client.get(feeds["station_information"])
            r.raise_for_status()
            self._info = {s["station_id"]: s for s in r.json()["data"]["stations"]}
            self._info_at = time.monotonic()
        return self._info

    async def fetch(self, client: httpx.AsyncClient) -> dict:
        feeds = await self.feeds(client)
        info = await self.station_info(client)
        r = await client.get(feeds["station_status"])
        r.raise_for_status()
        return build_bikes_slot(info, r.json(), self.cfg.origins, self.cfg.destinations)
