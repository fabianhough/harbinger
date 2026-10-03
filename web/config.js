// Display policy for the dashboard page. Nothing in this file is location-specific;
// station names, coordinates and IDs arrive in the state document from the server.
// Personal overrides go in config.local.js (gitignored); see config.local.example.js.
window.HARBINGER_CONFIG = {
  // Target panel. The type scale is derived from viewport height, so a different
  // monitor is mostly a matter of changing these and the layout weights below.
  viewport: { width: 2560, height: 1080 },

  // Where the page polls for state. The static mock reads its sample file; the
  // server will expose /api/state.
  stateUrl: "sample/state.json",
  pollMs: 30000,

  // "live" uses the wall clock. "frozen" pins the clock to state.generated_at so
  // a sample document reads sensibly when reviewing the mock.
  clock: "frozen",

  // Full page reload once a day at this local time (kiosk hygiene). null disables.
  reloadAt: "04:00",

  // Which transit direction gets the large treatment.
  emphasizedDirection: "N",

  // Trains arriving sooner than this cannot be reached on foot and are not shown.
  walkMinutes: 10,

  // How many hours the weather strip covers, starting from the current hour.
  hourlyHours: 18,

  // Seconds after updated_at at which a pane is "stale"; 3x this is "dead".
  freshnessSeconds: {
    weather: 7200,
    transit: 120,
    bikes: 300,
    news: 43200,
    notices: 86400,
  },

  layout: {
    // Left column is what the world measures; right column is what the agent says.
    columns: "2fr 1fr",
    bandHeight: "10vh",
    stripHeight: "28vh",
    // Transit and bikes, left to right, under the strip.
    leftBottom: "60fr 40fr",
  },

  timeZone: "America/New_York",
  locale: "en-US",
};
