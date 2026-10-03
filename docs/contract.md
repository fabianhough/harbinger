# State contract

Last updated: 2026-10-03

Every pane on the dashboard renders from one JSON document, the **state**. Internal
collectors produce most of it. An external agent writes the rest. This page is the
contract between them and the page, written for whoever builds the agent side.

The machine-readable version is `schema/state.schema.json` (JSON Schema 2020-12).
A complete example is `web/sample/state.json`. It uses placeholder locations, real
feed payloads where the recon captured them, and invented values elsewhere (the
evening showers, the wind advisory, the news, the notices) so that every rendering
path is exercised.

## Document

```json
{
  "generated_at": "2026-10-03T15:55:00-04:00",
  "slots": {
    "weather": { ... },
    "transit": { ... },
    "bikes":   { ... },
    "news":    { ... },
    "notices": { ... }
  }
}
```

- `generated_at` is when the server assembled the document.
- Every slot carries its own `updated_at`, the time its data was last refreshed.
- A slot may be absent. The page then shows an empty pane that says so.
- Timestamps are ISO 8601 with a UTC offset.

## Freshness

The page, not the payload, decides what counts as stale. Each slot has a budget in
`web/config.js`. Past the budget the pane is **stale** (desaturated, age shown in
amber). Past three times the budget it is **dead** (faded, age shown in red).

| Slot | Budget | Written by |
|---|---|---|
| `weather` | 2 h | collector (NWS) |
| `transit` | 2 min | collector (MTA GTFS-realtime) |
| `bikes` | 5 min | collector (Citi Bike GBFS) |
| `news` | 12 h | agent |
| `notices` | 24 h | agent |

## Slots

### `weather`

```json
{
  "updated_at": "...",
  "source": "nws",
  "verdicts": {
    "umbrella": { "answer": "10pm to 1am", "detail": "Showers likely, 65% at 11pm" },
    "jacket":   { "answer": "Light",       "detail": "57° tonight, feels like 52° after 10pm" }
  },
  "now":    { "temp_f": 71, "feels_f": 65, "short": "Sunny", "wind": "8 mph NE" },
  "hourly": [ { "t": "...", "temp_f": 71, "pop": 0, "kind": "clear", "short": "Sunny" } ],
  "today":  { "high_f": 71, "low_f": 55, "narrative": "Mostly sunny ..." },
  "alerts": [ { "headline": "Wind Advisory until 10 PM", "severity": "advisory",
                "onset": "...", "ends": "..." } ]
}
```

- `verdicts` are the words shown in the top band. `answer` is at most 24
  characters; `detail` at most 80. The page labels `umbrella` as **Rain**: the
  useful answer is *when* ("10pm to 1am", "None"), not yes or no.
- `hourly` starts at the current hour, 24 entries at most; the page shows the first
  18 by default. `pop` is probability of precipitation, 0 to 100. `kind` is the
  collector's classification of the hour: `clear`, `cloudy`, `fog`, `rain`, `snow`
  or `storm`. Rain, snow and storm hours are shaded on the strip.
- `alerts.severity` is `advisory`, `watch` or `warning`. `onset` and `ends` are
  optional; when present the alert is drawn across those hours of the strip,
  otherwise across all of them.

### `transit`

```json
{
  "updated_at": "...",
  "station": { "name": "Jay St-MetroTech" },
  "directions": { "N": "Manhattan", "S": "Brooklyn" },
  "lines": [
    {
      "route": "F",
      "directions": {
        "N": { "label": "Manhattan", "arrivals_min": [0.8, 10.8, 19.3] },
        "S": { "label": "Brooklyn",  "arrivals_min": [0.8, 9.3, 17.3] }
      },
      "alerts": [
        { "type": "Delays", "scope": "line",
          "header": "Downtown [E][F] trains are running with delays ..." }
      ]
    }
  ]
}
```

- `route` is the GTFS `route_id`. The page maps it to the official line colour.
- `N` and `S` follow the MTA's platform suffix convention. `directions` gives the
  station-wide column headers; a line's own `label` is shown small beneath its
  times only when it differs (a line that terminates short, say). The page
  emphasises one direction (configurable).
- `arrivals_min` holds up to three values, ascending, minutes from `updated_at`.
  The page drops arrivals sooner than its configured walk time (10 minutes by
  default) before showing the rest, so send the next three regardless. Nothing
  reachable renders as "none in reach".
- `alerts.header` may use `[F]` bracket notation; the page renders it as a bullet.
  `scope` is `line` for line-wide alerts and `station` for ones naming this stop.
  Station-scoped alerts get the stronger treatment.

### `bikes`

```json
{
  "updated_at": "...",
  "stations": [
    { "role": "origin",      "name": "Broadway & W 48 St", "classic": 3, "ebike": 2,
      "docks": 94, "renting": true, "reported_at": "..." },
    { "role": "destination", "name": "Broadway & W 41 St", "classic": 2, "ebike": 10,
      "docks": 37, "renting": true, "reported_at": "..." }
  ]
}
```

- `origin` stations lead with bike counts; `destination` stations lead with docks.
- `classic` excludes e-bikes. (GBFS `num_bikes_available` includes them; the
  collector subtracts.)
- `renting: false` marks the station as not renting.

### `news` (agent-written)

```json
{
  "updated_at": "...",
  "items": [
    { "title": "...", "summary": "...", "source": "Gothamist",
      "published_at": "...", "priority": "high" }
  ]
}
```

- Up to 10 items. The page shows what fits; put the most important first.
- `title` at most 90 characters, `summary` at most 200, `source` at most 40.
- `priority` is `low`, `normal` (default) or `high`. High items get a marker; low
  items are dimmed.

### `notices` (agent-written)

```json
{
  "updated_at": "...",
  "priority": "normal",
  "headline": "Minecraft server is back online",
  "text": "**Homelab**\nproxmox-01 up 41 days\n\n**Friends**\nMinecraft server back online as of 2pm"
}
```

- `text` is free-form, at most 1200 characters. Newlines are preserved. `**bold**`
  is the only markup; everything else is shown literally. HTML is escaped.
- `headline` is optional, at most 60 characters, shown large at the top of the
  agent column. Omit it on quiet days and the space collapses.
- `priority: high` highlights the pane heading.

## Writing the agent slots

The agent replaces one slot at a time with an HTTP PUT.

```
PUT /api/slots/news
PUT /api/slots/notices
Authorization: Bearer <token from config.yaml or HARBINGER_AGENT_TOKEN>
Content-Type: application/json
```

The body is the slot object exactly as shown above. `updated_at` may be omitted;
the server fills it with the receipt time. Partial updates are not supported: send
the whole slot every time. This keeps the agent stateless and makes a bad write easy
to overwrite.

Responses:

| Code | Meaning |
|---|---|
| `204` | Stored. The next `GET /api/state` shows it. |
| `400` | Body is not JSON, or fails the schema. `detail` names the field and the rule. |
| `401` | No bearer token. |
| `403` | Wrong token, or the server has no token configured. |
| `404` | Not an agent-writable slot. Only `news` and `notices` are. |

Example:

```sh
curl -X PUT http://harbinger.local:8080/api/slots/notices \
  -H "Authorization: Bearer $HARBINGER_AGENT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "headline": "Minecraft server is back online",
    "text": "**Friends**\nMinecraft server back online as of 2pm\n\n**Today**\nTrash goes out tonight"
  }'
```

`GET /api/state` returns the whole document and `GET /api/health` returns the age of
each slot in seconds, which is a quick way for the agent to confirm its write landed.
