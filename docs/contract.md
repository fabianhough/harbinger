# State contract

Last updated: 2026-10-03

Every pane on the dashboard renders from one JSON document, the **state**. Internal
collectors produce most of it. An external agent writes the rest. This page is the
contract between them and the page, written for whoever builds the agent side.

The machine-readable version is `schema/state.schema.json` (JSON Schema 2020-12).
A complete example, using placeholder locations and fictional news, is
`web/sample/state.json`.

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
    "umbrella": { "answer": "No",    "detail": "0% chance of rain through midnight" },
    "jacket":   { "answer": "Light", "detail": "57° tonight, feels like 52° after 10pm" }
  },
  "now":    { "temp_f": 71, "feels_f": 65, "short": "Sunny", "wind": "8 mph NE" },
  "hourly": [ { "t": "...", "temp_f": 71, "pop": 0, "short": "Sunny" } ],
  "today":  { "high_f": 71, "low_f": 57, "narrative": "Mostly sunny ..." },
  "alerts": [ { "headline": "Wind Advisory until 6 PM", "severity": "advisory" } ]
}
```

- `verdicts` are the words shown in the top band. `answer` is at most 24
  characters; `detail` at most 80.
- `hourly` is the next 12 hours, 24 at most. `pop` is probability of precipitation,
  0 to 100.
- `alerts.severity` is `advisory`, `watch` or `warning`.

### `transit`

```json
{
  "updated_at": "...",
  "station": { "name": "Jay St-MetroTech" },
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
- `N` and `S` follow the MTA's platform suffix convention. `label` is the
  destination word to display. The page emphasises one direction (configurable).
- `arrivals_min` holds up to three values, ascending, minutes from `updated_at`.
  Values under 1 render as "now". An empty array renders as "no trains".
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

- Up to 8 items. The page shows what fits; put the most important first.
- `title` at most 90 characters, `summary` at most 200, `source` at most 40.
- `priority` is `low`, `normal` (default) or `high`. High items get a marker; low
  items are dimmed.

### `notices` (agent-written)

```json
{
  "updated_at": "...",
  "priority": "normal",
  "text": "**Homelab**\nproxmox-01 up 41 days\n\n**Friends**\nMinecraft server: offline since Thursday"
}
```

- Free-form text, at most 1200 characters. Newlines are preserved. `**bold**` is
  the only markup; everything else is shown literally. HTML is escaped.
- `priority: high` highlights the pane heading.

## Writing the agent slots

Planned for the server leg: the agent replaces one slot at a time with an HTTP PUT.

```
PUT /api/slots/news
PUT /api/slots/notices
Authorization: Bearer <token from the server's local config>
Content-Type: application/json
```

The body is the slot object exactly as shown above. `updated_at` may be omitted;
the server fills it with the receipt time. The server validates against the schema
and answers `400` with the validation message on a bad body.

Partial updates are not supported: send the whole slot every time. This keeps the
agent stateless and makes a bad write easy to overwrite.
