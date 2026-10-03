# Citi Bike (GBFS)

Last verified: 2026-10-03

## Where

- Discovery: `https://gbfs.citibikenyc.com/gbfs/gbfs.json` (GBFS 1.1). It points at
  Lyft-hosted feeds under `https://gbfs.lyft.com/gbfs/1.1/bkn/en/`.
- GBFS 2.3 is also published: `https://gbfs.lyft.com/gbfs/2.3/bkn/gbfs.json`.
  It adds `vehicle_types.json` and per-type counts in `station_status`.
- Spec: https://github.com/MobilityData/gbfs
- Citi Bike system data page: https://citibikenyc.com/system-data
- Auth: none. No `User-Agent` requirement observed.
- `ttl`: 60 s on every feed. `Last-Modified` header present.

Feeds that matter:

| Feed | Purpose | Changes |
|---|---|---|
| `station_information.json` | Static per station: id, name, lat/lon, capacity | Rarely |
| `station_status.json` | Live counts per station | Every minute |
| `vehicle_types.json` (2.3 only) | Maps `vehicle_type_id` to classic/electric | Rarely |

## How

```sh
curl -sS https://gbfs.citibikenyc.com/gbfs/gbfs.json | jq '.data.en.feeds[] | {name, url}'
curl -sS -o si.json https://gbfs.lyft.com/gbfs/1.1/bkn/en/station_information.json
curl -sS -o ss.json https://gbfs.lyft.com/gbfs/1.1/bkn/en/station_status.json
# nearest 5 stations to a coordinate, joined with live status
jq -n --slurpfile si si.json --slurpfile ss ss.json '
  ($ss[0].data.stations | map({(.station_id): .}) | add) as $st
  | $si[0].data.stations
  | map(. + {d: ((.lat-40.7580)*(.lat-40.7580) + ((.lon+73.9855)*0.76)*((.lon+73.9855)*0.76))})
  | sort_by(.d) | .[0:5]
  | map({name, station_id, capacity, status: $st[.station_id]})'
```

## What

`station_information.json` lists 2520 stations. Per station:

```json
{
  "station_id": "64f0f28c-bedc-42d5-b107-ecdd48fc30cd",
  "name": "Broadway & W 48 St",
  "short_name": "6771.03",
  "lat": 40.76017739537783,
  "lon": -73.98486793041229,
  "region_id": "71",
  "capacity": 103,
  "station_type": "classic"
}
```

`station_status.json`, same station, same minute:

```json
{
  "station_id": "64f0f28c-bedc-42d5-b107-ecdd48fc30cd",
  "num_bikes_available": 5,
  "num_ebikes_available": 2,
  "num_bikes_disabled": 3,
  "num_docks_available": 94,
  "num_docks_disabled": 0,
  "is_installed": 1,
  "is_renting": 1,
  "is_returning": 1,
  "last_reported": 1791057191
}
```

In GBFS 2.3 the same record also carries:

```json
"vehicle_types_available": [
  { "vehicle_type_id": "1", "count": 3 },
  { "vehicle_type_id": "2", "count": 2 }
]
```

where `vehicle_types.json` says `1` is `human` propulsion and `2` is
`electric_assist` with `max_range_meters` about 69 km.

Field semantics confirmed from the sample: `num_bikes_available` **includes**
e-bikes (3 classic + 2 electric = 5). Classic count is therefore
`num_bikes_available - num_ebikes_available`.

**Mapping to the dashboard question:** for each configured station, show classic
and e-bike counts at the origin and dock count at the destination, with
`last_reported` driving the staleness indicator.

## Caveats

- `station_id` is a mixed bag: some are UUIDs, some are numeric strings. Match on
  the exact string, never parse.
- Some entries are placeholders: `is_installed: 0`, `capacity: 0`,
  `last_reported: 86400`. Filter on `is_installed == 1` before anything else.
- `station_information` is 2520 records; fetch it once a day, not every poll.
- The nearest-station math in **How** is a flat-earth approximation that is fine at
  Brooklyn scale; use it for discovery, then pin the chosen `station_id`s in config.
- The 1.1 feed is what the official discovery URL advertises. 2.3 is the better
  structure if it stays published; the `gbfs_versions.json` endpoint lists both.
