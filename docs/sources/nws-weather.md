# National Weather Service API

Last verified: 2026-10-03

## Where

- Base: `https://api.weather.gov`
- Documentation: https://www.weather.gov/documentation/services-web-api
  (OpenAPI spec and FAQ on the same page)
- Auth: none. A `User-Agent` header is **required**; requests without one get
  `403`. NWS asks that it identify the application and include contact info.
- Rate limits: not published. The FAQ asks for reasonable use and respecting cache
  headers.
- Coverage: United States only. Fine for Brooklyn.

Three endpoints matter:

| Endpoint | Purpose | Cache (`max-age`) |
|---|---|---|
| `/points/{lat},{lon}` | Resolve a coordinate to a forecast office and grid cell, and get the forecast URLs | 86400 s |
| `/gridpoints/{office}/{x},{y}/forecast/hourly` | Hourly periods, 7 days | 3600 s |
| `/gridpoints/{office}/{x},{y}/forecast` | Twice-daily narrative periods ("This Afternoon", "Tonight") | 3600 s |
| `/gridpoints/{office}/{x},{y}` | Raw gridded layers, including apparent temperature | 3600 s |

## How

Example coordinate: Times Square, `40.7580,-73.9855`.

```sh
UA="harbinger (github.com/fabianhough/harbinger)"
curl -sS -A "$UA" https://api.weather.gov/points/40.7580,-73.9855 \
  | jq '.properties | {gridId, gridX, gridY, forecastHourly, forecastGridData, timeZone}'
curl -sS -A "$UA" https://api.weather.gov/gridpoints/OKX/34,44/forecast/hourly \
  | jq '.properties | {updateTime, periods: .periods[0:3]}'
curl -sS -A "$UA" https://api.weather.gov/gridpoints/OKX/34,44 \
  | jq '.properties.apparentTemperature'
```

## What

**`/points`** resolves the example to office `OKX`, grid `34,44`, time zone
`America/New_York`, and returns the three gridpoint URLs above. This mapping is
stable; cache it for a day as the header suggests.

**`/forecast/hourly`** returns 156 one-hour `periods` (about 6.5 days). Per period:

```json
{
  "startTime": "2026-10-03T15:00:00-04:00",
  "endTime": "2026-10-03T16:00:00-04:00",
  "isDaytime": true,
  "temperature": 71,
  "temperatureUnit": "F",
  "probabilityOfPrecipitation": { "unitCode": "wmoUnit:percent", "value": 0 },
  "dewpoint": { "unitCode": "wmoUnit:degC", "value": 10 },
  "relativeHumidity": { "unitCode": "wmoUnit:percent", "value": 47 },
  "windSpeed": "8 mph",
  "windDirection": "NE",
  "icon": "https://api.weather.gov/icons/land/day/few?size=small",
  "shortForecast": "Sunny"
}
```

Top-level `properties.updateTime` is when the forecast was issued (18:19 UTC on a
19:53 UTC fetch), `generatedAt` is when the response was built. `units: "us"` but
dewpoint is still Celsius. `windSpeed` is a string, sometimes a range
(`"5 to 8 mph"`).

**`/forecast`** returns named half-day periods with a `detailedForecast` sentence
("Mostly sunny. High near 71, with temperatures falling to around 69 in the
afternoon. Northeast wind around 8 mph."). Good for a one-line narrative slot.

**`/gridpoints/{office}/{x},{y}`** is the raw data behind both. Layers present
include `temperature`, `apparentTemperature`, `windChill`, `heatIndex`,
`probabilityOfPrecipitation`, `quantitativePrecipitation`, `snowfallAmount`,
`windSpeed`, `windGust`, `skyCover`, `hazards`, `weather`. Values are SI (`degC`,
`mm`) and run-length encoded: each entry has a `validTime` of the form
`2026-10-03T12:00:00+00:00/PT18H`, meaning the value holds for that duration.

```json
{ "validTime": "2026-10-03T12:00:00+00:00/PT1H", "value": 16.67 }
```

**Mapping to the dashboard question:**

- *Umbrella?* — max `probabilityOfPrecipitation` over the next N hourly periods,
  plus `quantitativePrecipitation` from the gridpoint for "how much".
- *Jacket?* — `apparentTemperature` min and max across the day from the gridpoint
  (not available in the hourly forecast), or hourly `temperature` plus `windSpeed`
  as a cruder proxy.

## Caveats

- Missing `User-Agent` is a hard `403`.
- Mixed units: Fahrenheit temperature, Celsius dewpoint, SI gridpoints. Normalize
  at the collector boundary.
- Gridpoint `validTime` durations vary per layer and must be expanded before
  indexing by hour.
- Forecast issuance (`updateTime`) is roughly hourly; polling more often than the
  `max-age` of 3600 s gains nothing.
- Not verified here, but widely reported: the API returns intermittent `5xx`.
  The collector should retry with backoff and keep the last good response.
