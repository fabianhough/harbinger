// Static review settings, used by mock.html: read the committed sample instead of
// the server, and pin the clock to the sample's generated_at.
Object.assign(window.HARBINGER_CONFIG, {
  stateUrl: "sample/state.json",
  clock: "frozen",
});
