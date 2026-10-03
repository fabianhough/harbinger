# /// script
# requires-python = ">=3.11"
# dependencies = ["gtfs-realtime-bindings>=1.0.0", "requests"]
# ///
"""Decode MTA subway GTFS-realtime feeds and print arrivals for given stop IDs.

Usage: uv run mta_recon.py <feed> <stop_id> [<stop_id>...]
  feed: one of ace bdfm g nqrw jz l 1234567s si  (the nyct%2Fgtfs-<feed> suffix; "1234567s" maps to plain "gtfs")
"""
import sys, time, collections
import requests
from google.transit import gtfs_realtime_pb2

BASE = "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs"
feed_key, stops = sys.argv[1], set(sys.argv[2:])
url = BASE if feed_key == "1234567s" else f"{BASE}-{feed_key}"

t0 = time.time()
r = requests.get(url, timeout=30)
r.raise_for_status()
msg = gtfs_realtime_pb2.FeedMessage()
msg.ParseFromString(r.content)
now = time.time()
print(f"url={url}\nhttp={r.status_code} bytes={len(r.content)} content-type={r.headers.get('content-type')} fetch_s={now-t0:.2f}")
print(f"header: gtfs_realtime_version={msg.header.gtfs_realtime_version} timestamp={msg.header.timestamp} age_s={now-msg.header.timestamp:.0f}")
kinds = collections.Counter()
for e in msg.entity:
    for k in ("trip_update", "vehicle", "alert"):
        if e.HasField(k): kinds[k] += 1
print(f"entities={len(msg.entity)} by_kind={dict(kinds)}")

# first trip_update, full structure once
for e in msg.entity:
    if e.HasField("trip_update"):
        tu = e.trip_update
        print("\n--- example trip_update (first entity) ---")
        print(f"entity.id={e.id} trip_id={tu.trip.trip_id} route_id={tu.trip.route_id} start_date={tu.trip.start_date} start_time={tu.trip.start_time}")
        ext = tu.trip.Extensions if hasattr(tu.trip, "Extensions") else None
        print(f"stop_time_updates={len(tu.stop_time_update)} first={[(s.stop_id, s.arrival.time, s.departure.time) for s in tu.stop_time_update[:3]]}")
        break

print(f"\n--- arrivals at {sorted(stops)} (prefix match on N/S) ---")
rows = []
for e in msg.entity:
    if not e.HasField("trip_update"): continue
    tu = e.trip_update
    for s in tu.stop_time_update:
        if s.stop_id[:-1] in stops or s.stop_id in stops:
            t = s.arrival.time or s.departure.time
            rows.append((t, s.stop_id, tu.trip.route_id, tu.trip.trip_id, (t-now)/60))
for t, sid, route, trip, mins in sorted(rows)[:12]:
    print(f"{sid} {route:>2} in {mins:5.1f} min  epoch={t} trip={trip}")
print(f"total matching stop_time_updates={len(rows)}")
