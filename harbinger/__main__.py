"""Command line: serve, collect, stations."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from .config import DEFAULT_GBFS_URL, load_config
from .state import StateStore


def _serve(args: argparse.Namespace) -> int:
    import uvicorn

    from .api import create_app

    cfg = load_config(args.config)
    store = StateStore(cfg.snapshot)
    if args.seed:
        if store.has_data:
            print(f"snapshot {cfg.snapshot} exists; ignoring --seed", file=sys.stderr)
        else:
            store.load(Path(args.seed))
            store.save()
            print(f"seeded state from {args.seed}", file=sys.stderr)
    if not cfg.agent_token:
        print("agent token not configured; PUT /api/slots/* will be refused", file=sys.stderr)
    app = create_app(cfg, store)
    uvicorn.run(app, host=args.host or cfg.host, port=args.port or cfg.port, log_level="info")
    return 0


def _collect(args: argparse.Namespace) -> int:
    from .collectors import build_collectors, make_client

    cfg = load_config(args.config)
    by_name = {c.name: c for c in build_collectors(cfg)}
    collector = by_name.get(args.name)
    if collector is None:
        print(f"no collector {args.name!r} configured; have {sorted(by_name) or 'none'}", file=sys.stderr)
        return 2

    async def run() -> dict:
        async with make_client() as client:
            return await collector.fetch(client)

    body = asyncio.run(run())
    StateStore(None).set_slot(collector.slot, body)  # validates without persisting
    json.dump(body, sys.stdout, indent=2)
    print()
    print(f"{collector.name}: slot {collector.slot!r} is valid", file=sys.stderr)
    return 0


def _stations(args: argparse.Namespace) -> int:
    from .collectors.citibike import feed_urls, search_stations
    from .collectors import make_client

    cfg = load_config(args.config)
    gbfs_url = cfg.bikes.gbfs_url if cfg.bikes else DEFAULT_GBFS_URL
    near = None
    if args.near:
        lat, lon = (float(x) for x in args.near.split(","))
        near = (lat, lon)

    async def run() -> list[dict]:
        async with make_client() as client:
            r = await client.get(gbfs_url)
            r.raise_for_status()
            info_url = feed_urls(r.json())["station_information"]
            r = await client.get(info_url)
            r.raise_for_status()
            return search_stations(r.json()["data"]["stations"], args.query, near, args.limit)

    for s in asyncio.run(run()):
        dist = f"{s['distance_m']:>6} m  " if "distance_m" in s else ""
        print(f"{dist}{s['station_id']}  {s['name']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx2").setLevel(logging.WARNING)
    ap = argparse.ArgumentParser(prog="harbinger")
    sub = ap.add_subparsers(dest="cmd", required=True)

    serve = sub.add_parser("serve", help="serve the dashboard, its API, and run the collectors")
    serve.add_argument("--config", help="path to config.yaml (default: ./config.yaml or $HARBINGER_CONFIG)")
    serve.add_argument("--seed", help="state document to load when no snapshot exists yet")
    serve.add_argument("--host")
    serve.add_argument("--port", type=int)
    serve.set_defaults(func=_serve)

    collect = sub.add_parser("collect", help="run one collector once and print its slot")
    collect.add_argument("name", help="citibike, nws, or mta")
    collect.add_argument("--config")
    collect.set_defaults(func=_collect)

    stations = sub.add_parser("stations", help="look up Citi Bike station IDs by name or location")
    stations.add_argument("query", nargs="?", help="name substring, e.g. 'Broadway & W 48'")
    stations.add_argument("--near", help="LAT,LON to sort by distance")
    stations.add_argument("--limit", type=int, default=15)
    stations.add_argument("--config")
    stations.set_defaults(func=_stations)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
