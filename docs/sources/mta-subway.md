# MTA Subway (GTFS and GTFS-realtime)

Last verified: 2026-10-03

## Where

- Developer portal: https://new.mta.info/developers (feed list, terms, and the NYCT
  protobuf extension definition). GTFS-realtime spec: https://gtfs.org/realtime/
- Auth: **none**. No API key, no `User-Agent` requirement observed.
- Realtime trip feeds, one per line group, protobuf bodies served as `text/plain`:

  | Feed key | URL suffix | Lines |
  |---|---|---|
  | `ace` | `nyct%2Fgtfs-ace` | A C E (and the H / Rockaway shuttle) |
  | `bdfm` | `nyct%2Fgtfs-bdfm` | B D F FX M |
  | `g` | `nyct%2Fgtfs-g` | G |
  | `jz` | `nyct%2Fgtfs-jz` | J Z |
  | `nqrw` | `nyct%2Fgtfs-nqrw` | N Q R W |
  | `l` | `nyct%2Fgtfs-l` | L |
  | (none) | `nyct%2Fgtfs` | 1 2 3 4 5 6 7 and the 42 St shuttle |
  | `si` | `nyct%2Fgtfs-si` | Staten Island Railway |

  Base: `https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/`
- Service alerts: same base, `camsys%2Fsubway-alerts` (protobuf, 434 KB) or
  `camsys%2Fsubway-alerts.json` (JSON, same content). Use the JSON.
- Static GTFS (stop IDs, route names, schedules):
  `https://rrgtfsfeeds.s3.amazonaws.com/gtfs_subway.zip` (5.6 MB). The copy fetched
  today is `feed_version 20260826-X-long-term-supplement-trip-ids`, valid
  2026-05-26 to 2026-10-31.

## How

Example station: **Jay St-MetroTech**, chosen because it is served by lines from
three different realtime feeds (A/C in `ace`, F in `bdfm`, R in `nqrw`), which is
the same merge problem as the real station.

```sh
# 1. Stop IDs from the static feed
curl -sS -o gtfs_subway.zip https://rrgtfsfeeds.s3.amazonaws.com/gtfs_subway.zip
unzip -o -q gtfs_subway.zip -d gtfs_static
grep -i "jay st" gtfs_static/stops.txt
# 2. Realtime arrivals (script in docs/recon/, deps resolved by uv)
uv run docs/recon/mta_recon.py ace  A41
uv run docs/recon/mta_recon.py bdfm A41
uv run docs/recon/mta_recon.py nqrw R29
# 3. Alerts for a route
curl -sS https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/camsys%2Fsubway-alerts.json \
  | jq '[.entity[] | select(.alert.informed_entity | any(.route_id=="R"))]
         | map({id, active: .alert.active_period, header: .alert.header_text.translation[0].text})'
```

## What

### Stop IDs

`stops.txt` has 1488 rows, 496 of them parent stations. Jay St-MetroTech is **two**
parent stations with separate IDs, because the A/C/F platforms and the R platforms
are distinct complexes in the data:

```
A41,Jay St-MetroTech,40.692338,-73.987342,1,
A41N,Jay St-MetroTech,...,,A41
A41S,Jay St-MetroTech,...,,A41
R29,Jay St-MetroTech,40.692180,-73.985942,1,
R29N,...   R29S,...
```

Realtime `stop_id`s are always the platform children: parent ID plus `N` or `S`.
`N`/`S` is the MTA's per-line direction convention (roughly "toward the northern
terminal"), not compass-true. Matching on the parent prefix catches both directions.

### Trip feeds

Header: `gtfs_realtime_version 1.0`, `timestamp` is feed generation time. Observed
ages at fetch: 2 to 7 seconds. Bodies are 19 KB (`g`) to 92 KB (`bdfm`).

Entities come in pairs, one `trip_update` and one `vehicle` per running train
(ACE: 72 + 72, NQRW: 74 + 74, BDFM: 101 + 101, G: 25 + 25 at ~16:00 on a
Saturday). No `alert` entities in these feeds.

`trip_update`:

```
trip.trip_id   = "090800_C..S"      # origin-time code, route, direction, path
trip.route_id  = "C"
trip.start_date = "20261003"
stop_time_update[] = { stop_id: "A41S", arrival.time: 1791057292,
                       departure.time: 1791057292, departure_occupancy_status }
```

`arrival.time` and `departure.time` are epoch seconds and equal at intermediate
stops. `delay` and `uncertainty` are **not** set. Minutes-until-arrival is simply
`(arrival.time - now) / 60`; a train at the platform shows slightly negative.

`vehicle`: `trip`, `stop_id` (the stop it is at or heading to), `current_status`
(`STOPPED_AT`, `IN_TRANSIT_TO`, `INCOMING_AT`), `timestamp`.

Merged arrivals at the example station, one fetch, sorted (trimmed):

```
A41S  F in   0.8 min      R29S  R in   1.2 min
A41S  C in   0.9 min      R29S  R in   8.4 min
A41S  A in   3.2 min      R29N  R in   9.4 min
A41S  C in   7.9 min      R29S  R in  15.9 min
A41S  F in   9.3 min
A41N  A in  10.4 min
A41N  F in  10.8 min
```

Each feed carried 18 to 35 matching `stop_time_update`s for the station, i.e.
roughly an hour of lookahead.

### Alerts

JSON mirror of the protobuf, `gtfs_realtime_version 2.0`, 178 entities. The header
`timestamp` was ~11 minutes old at fetch, so alerts refresh far less often than
trips. Per alert (trimmed):

```json
{
  "id": "lmm:alert:270204:26",
  "alert": {
    "informed_entity": [ { "agency_id": "MTASBWY", "route_id": "R" } ],
    "active_period": [ { "start": 1791055071, "end": 1791057000 } ],
    "header_text": { "translation": [ { "text": "Downtown [R] trains are running with delays ...", "language": "en" } ] },
    "description_text": { "...": "..." },
    "transit_realtime.mercury_alert": {
      "created_at": 1791055071, "updated_at": 1791055651,
      "alert_type": "Delays", "display_before_active": 0
    }
  }
}
```

`header_text` uses `[R]` bracket notation for route bullets, which the UI can
render as the familiar circles. `alert_type` values seen: `Delays`, plus planned
work entries that carry `display_before_active`. `active_period.end` may be absent.

**Mapping to the dashboard question:** fetch the feeds that cover the configured
station, collect `stop_time_update`s whose `stop_id` starts with a configured
parent ID, bucket by direction and route, show the next few minutes-to-arrival per
route. Overlay any alert whose `informed_entity` names one of those routes and
whose `active_period` contains now.

## Caveats

- The NYCT protobuf extension (train ID, assigned flag, actual direction) is not
  bundled with `gtfs-realtime-bindings` and the `upb` protobuf backend refuses to
  expose unknown fields. Not needed: route and direction are recoverable from
  `route_id` and the stop ID suffix.
- `Content-Type: text/plain` on a binary body. Do not let an HTTP client try to
  decode it as text.
- Trip feeds only contain trains the system has assigned. Late-night and
  disruption gaps are real gaps, not fetch failures.
- The static feed expires (`feed_end_date`). Stop IDs are stable in practice, but
  the zip should be re-fetched on a schedule and the configured IDs re-validated.
- `route_id` is not always the bullet: `FX` is the Brooklyn F express, and the
  three shuttles (`GS`, `FS`, `H`) all display as `S`. Use `routes.txt`
  `route_short_name` for display.
- Feeds regenerate every ~30 s. Polling at 30 to 60 s is appropriate; faster is
  wasted. Alerts can be polled every few minutes.
