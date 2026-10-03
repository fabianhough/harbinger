.DEFAULT_GOAL := help
.PHONY: help config up logs down test screenshot

help:  ## list targets
	@grep -E '^[a-z]+:.*## ' $(MAKEFILE_LIST) | awk -F ':.*## ' '{printf "  make %-11s %s\n", $$1, $$2}'

config:  ## create config.yaml and .env from the examples (never overwrites)
	@test -f config.yaml || { cp config.example.yaml config.yaml; echo "created config.yaml: set your station, lines, coordinates and bike stations"; }
	@test -f .env || { cp .env.example .env; echo "created .env: set HARBINGER_AGENT_TOKEN"; }

up:  ## build and start, or apply an update after git pull
	docker compose up -d --build

logs:  ## follow the server log
	docker compose logs -f

down:  ## stop
	docker compose down

test:  ## run the test suite (dev machine, needs uv)
	uv run pytest -q

screenshot:  ## render the mock at kiosk resolution (dev machine, needs uv)
	uv run tools/screenshot.py --out preview.png
