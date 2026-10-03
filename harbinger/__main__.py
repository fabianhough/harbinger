"""Command line: `harbinger serve`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import load_config
from .state import StateStore


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="harbinger")
    sub = ap.add_subparsers(dest="cmd", required=True)

    serve = sub.add_parser("serve", help="serve the dashboard and its API")
    serve.add_argument("--config", help="path to config.yaml (default: ./config.yaml or $HARBINGER_CONFIG)")
    serve.add_argument("--seed", help="state document to load when no snapshot exists yet")
    serve.add_argument("--host")
    serve.add_argument("--port", type=int)

    args = ap.parse_args(argv)

    if args.cmd == "serve":
        import uvicorn

        from .api import create_app

        cfg = load_config(args.config)
        store = StateStore(cfg.snapshot)
        if args.seed:
            if store.has_data:
                print(f"snapshot {cfg.snapshot} exists; ignoring --seed", file=sys.stderr)
            else:
                store.load(Path(args.seed))
                store.save()
                print(f"seeded state from {args.seed}", file=sys.stderr)
        if not cfg.agent_token:
            print("agent token not configured; PUT /api/slots/* will be refused", file=sys.stderr)
        app = create_app(cfg, store)
        uvicorn.run(app, host=args.host or cfg.host, port=args.port or cfg.port, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
