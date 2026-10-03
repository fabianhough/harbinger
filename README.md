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

Then open http://localhost:8080. The collectors configured in `config.yaml` (Citi
Bike, NWS weather, MTA subway) start with the server and fill their panes within a
minute; `--seed` fills the state with the sample document first so nothing waits.
The current state is snapshotted to `var/state.json` after every write and restored
on restart.

```sh
uv run harbinger collect nws                   # run one collector once, print its slot
uv run harbinger stations "Broadway & W 48"    # find Citi Bike station IDs by name
uv run harbinger stations --near 40.758,-73.9855
```

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
