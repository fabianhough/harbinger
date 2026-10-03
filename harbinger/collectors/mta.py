"""MTA subway arrivals and alerts via GTFS-realtime. See docs/sources/mta-subway.md."""

from __future__ import annotations

import asyncio
import logging
import time

import httpx2 as httpx
from google.transit import gtfs_realtime_pb2

from ..config import TransitConfig
from ..state import now_iso
from .base import Collector

log = logging.getLogger("harbinger.collectors.mta")

FEED_BASE = "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs"
ALERTS_URL = "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/camsys%2Fsubway-alerts.json"
ALERTS_TTL_S = 180
ARRIVALS_PER_DIRECTION = 6

# GTFS route_id -> realtime feed key ("" is the numbered-lines feed with no suffix).
ROUTE_FEED = {
    "A": "ace", "C": "ace", "E": "ace", "H": "ace",
    "B": "bdfm", "D": "bdfm", "F": "bdfm", "FX": "bdfm", "M": "bdfm",
    "G": "g",
    "J": "jz", "Z": "jz",
    "N": "nqrw", "Q": "nqrw", "R": "nqrw", "W": "nqrw",
    "L": "l",
    "1": "", "2": "", "3": "", "4": "", "5": "", "6": "", "6X": "", "7": "", "7X": "", "GS": "",
    "SI": "si",
}


def feed_url(key: str) -> str:
    return FEED_BASE if key == "" else f"{FEED_BASE}-{key}"


# ---------- pure helpers ----------

def arrivals_for(msg: gtfs_realtime_pb2.FeedMessage, route: str, stop: str, now_epoch: float,
                 limit: int = ARRIVALS_PER_DIRECTION) -> dict[str, list[float]]:
    """Minutes until arrival at stop+N and stop+S for one route, ascending."""
    out: dict[str, list[float]] = {"N": [], "S": []}
    for e in msg.entity:
        if not e.HasField("trip_update"):
            continue
        tu = e.trip_update
        if tu.trip.route_id != route:
            continue
        for stu in tu.stop_time_update:
            sid = stu.stop_id
            if sid[:-1] != stop or sid[-1] not in out:
                continue
            t = stu.arrival.time or stu.departure.time
            if not t:
                continue
            minutes = (t - now_epoch) / 60
            if minutes < -0.5:
                continue
            out[sid[-1]].append(round(minutes, 1))
    return {d: sorted(v)[:limit] for d, v in out.items()}


def _is_active(periods: list[dict] | None, now_epoch: float) -> bool:
    if not periods:
        return True
    for p in periods:
        start = p.get("start", 0) or 0
        end = p.get("end")
        if start <= now_epoch and (end is None or end >= now_epoch):
            return True
    return False


def _text(tt: dict | None) -> str:
    translations = (tt or {}).get("translation") or []
    for t in translations:
        if t.get("language", "en") == "en":
            return str(t.get("text", "")).strip()
    return str(translations[0].get("text", "")).strip() if translations else ""


def parse_alerts(alerts_json: dict, routes: set[str], stops: set[str], now_epoch: float) -> dict[str, list[dict]]:
    """Active alerts per configured route.

    An alert that names stops is about those stops: it is kept only if one of ours
    is among them, and then scoped "station". An alert naming no stops is line-wide.
    """
    per_route: dict[str, list[dict]] = {r: [] for r in routes}
    for ent in alerts_json.get("entity", []):
        alert = ent.get("alert") or {}
        if not _is_active(alert.get("active_period"), now_epoch):
            continue
        informed = alert.get("informed_entity") or []
        alert_routes = {ie.get("route_id") for ie in informed if ie.get("route_id")} & routes
        if not alert_routes:
            continue
        stop_ids = {ie.get("stop_id") for ie in informed if ie.get("stop_id")}
        if stop_ids and not (stop_ids & stops):
            continue
        header = _text(alert.get("header_text"))
        if not header:
            continue
        atype = (alert.get("transit_realtime.mercury_alert") or {}).get("alert_type") or "Alert"
        item = {"type": str(atype)[:32], "header": header[:240], "scope": "station" if stop_ids else "line"}
        for r in alert_routes:
            if item not in per_route[r]:
                per_route[r].append(item)
    return per_route


def build_transit_slot(cfg: TransitConfig, feeds: dict[str, gtfs_realtime_pb2.FeedMessage],
                       alerts_json: dict, now_epoch: float) -> dict:
    routes = {l.route for l in cfg.lines}
    stops = {l.stop for l in cfg.lines}
    alerts = parse_alerts(alerts_json, routes, stops, now_epoch)
    lines = []
    for l in cfg.lines:
        msg = feeds[ROUTE_FEED[l.route]]
        arr = arrivals_for(msg, l.route, l.stop, now_epoch)
        lines.append({
            "route": l.route,
            "directions": {
                d: {"label": l.labels.get(d, cfg.directions.get(d, d)), "arrivals_min": arr[d]}
                for d in ("N", "S")
            },
            "alerts": alerts.get(l.route, []),
        })
    slot = {"updated_at": now_iso(), "station": {"name": cfg.station_name[:40]}, "lines": lines}
    if cfg.directions.get("N") and cfg.directions.get("S"):
        slot["directions"] = {"N": cfg.directions["N"][:24], "S": cfg.directions["S"][:24]}
    return slot


# ---------- collector ----------

class MTACollector(Collector):
    name = "mta"
    slot = "transit"
    interval_s = 30.0

    def __init__(self, cfg: TransitConfig):
        unknown = [l.route for l in cfg.lines if l.route not in ROUTE_FEED]
        if unknown:
            raise ValueError(f"unknown MTA route(s) {unknown}; known: {sorted(ROUTE_FEED)}")
        self.cfg = cfg
        self._alerts: dict = {"entity": []}
        self._alerts_at = 0.0

    async def _feed(self, client: httpx.AsyncClient, key: str) -> gtfs_realtime_pb2.FeedMessage:
        r = await client.get(feed_url(key))
        r.raise_for_status()
        msg = gtfs_realtime_pb2.FeedMessage()
        msg.ParseFromString(r.content)
        return msg

    async def alerts(self, client: httpx.AsyncClient) -> dict:
        if time.monotonic() - self._alerts_at > ALERTS_TTL_S:
            try:
                r = await client.get(ALERTS_URL)
                r.raise_for_status()
                self._alerts = r.json()
                self._alerts_at = time.monotonic()
            except Exception as e:  # noqa: BLE001 - alerts are secondary; arrivals still publish
                log.warning("alerts fetch failed, keeping previous: %s", e)
                self._alerts_at = time.monotonic() - ALERTS_TTL_S + 30
        return self._alerts

    async def fetch(self, client: httpx.AsyncClient) -> dict:
        keys = sorted({ROUTE_FEED[l.route] for l in self.cfg.lines})
        msgs = await asyncio.gather(*(self._feed(client, k) for k in keys))
        alerts = await self.alerts(client)
        return build_transit_slot(self.cfg, dict(zip(keys, msgs)), alerts, time.time())
