# harbinger

A front-entrance pane for seeing what omens I should be prepared to face throughout the day.

One glanceable page on an ultrawide monitor: weather for the next 18 hours, the next
trains you can actually catch, bikes nearby, and whatever an agent decides you should
know. Served from a Raspberry Pi.

## Run

Requires [uv](https://docs.astral.sh/uv/) and Python 3.11+.

```sh
cp config.example.yaml config.yaml      # set the agent token
uv run harbinger serve --seed web/sample/state.json
```

Then open http://localhost:8080. The `--seed` fills the state with the sample document
on first run; without it every pane waits for data. The current state is snapshotted
to `var/state.json` after every write and restored on restart.

## Agent writes

The `news` and `notices` slots are written by an external agent over HTTP. The
contract, with examples, is in [docs/contract.md](docs/contract.md).

```sh
curl -X PUT http://localhost:8080/api/slots/notices \
  -H "Authorization: Bearer $HARBINGER_AGENT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"headline": "Minecraft server is back online", "text": "**Friends**\nback online as of 2pm"}'
```

## Develop

```sh
uv run pytest                       # server tests
uv run tools/screenshot.py          # render the mock at 2560x1080, fail on overflow
```

`web/mock.html` renders the committed sample with a frozen clock. `web/index.html`
is what the kiosk loads; it polls the server. Display settings live in
`web/config.js`, personal overrides in a gitignored `web/config.local.js`.

Data sources and their quirks are documented under [docs/sources](docs/sources).
