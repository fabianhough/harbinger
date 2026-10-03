# harbinger

A front-entrance pane for seeing what omens I should be prepared to face throughout the day.

One glanceable page on an ultrawide monitor: weather for the next 18 hours, the next
trains you can actually catch, bikes nearby, and whatever an agent decides you should
know. The server runs as a container on any host; the display is any browser pointed
at it.

## Deploy

Needs Docker with the compose plugin, and a port reachable from the display.

```sh
git clone https://github.com/fabianhough/harbinger && cd harbinger
make config        # creates config.yaml and .env from the examples
#   edit config.yaml: your station, lines, coordinates, bike stations
#   edit .env:        HARBINGER_AGENT_TOKEN, TZ
make up            # builds the image and starts it; restarts on its own after reboots
```

Open `http://<host>:8080/` on the display. `make logs` follows the server,
`make down` stops it. To update: `git pull && make up`.

State is snapshotted to `./var/state.json` on the host, so a restart comes back with
the last known board.

## Agent writes

The `news` and `notices` slots are written by an external agent over HTTP. The
contract, with examples, is in [docs/contract.md](docs/contract.md).

```sh
curl -X PUT http://<host>:8080/api/slots/notices \
  -H "Authorization: Bearer $HARBINGER_AGENT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"headline": "Minecraft server is back online", "text": "**Friends**\nback online as of 2pm"}'
```

## Run without Docker

Requires [uv](https://docs.astral.sh/uv/) and Python 3.11+.

```sh
cp config.example.yaml config.yaml
HARBINGER_AGENT_TOKEN=... uv run harbinger serve --seed web/sample/state.json
```

`--seed` fills the state with the sample document first so nothing waits; the
collectors in `config.yaml` take over within a minute.

```sh
uv run harbinger collect nws                   # run one collector once, print its slot
uv run harbinger stations "Broadway & W 48"    # find Citi Bike station IDs by name
uv run harbinger stations --near 40.758,-73.9855
```

## Develop

```sh
make test          # uv run pytest
make screenshot    # render web/mock.html at 2560x1080, fail on overflow
```

`web/mock.html` renders the committed sample with a frozen clock. `web/index.html`
is what the display loads; it polls the server. Display settings live in
`web/config.js`, personal overrides in a gitignored `web/config.local.js`.

Data sources and their quirks are documented under [docs/sources](docs/sources).
