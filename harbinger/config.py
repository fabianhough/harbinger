"""Configuration: config.yaml next to the checkout, with env overrides for secrets."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_WRITABLE_SLOTS = ["news", "notices"]


@dataclass
class Config:
    host: str = "0.0.0.0"
    port: int = 8080
    agent_token: str | None = None
    writable_slots: list[str] = field(default_factory=lambda: list(DEFAULT_WRITABLE_SLOTS))
    snapshot: Path = Path("var/state.json")
    web_dir: Path = Path("web")


def load_config(path: str | os.PathLike | None = None) -> Config:
    """Load config.yaml (or $HARBINGER_CONFIG, or the given path).

    Relative paths inside the file resolve against the file's own directory. When no
    file exists the defaults apply, relative to the current directory. The agent
    token may also come from HARBINGER_AGENT_TOKEN, which wins over the file.
    """
    p = Path(path or os.environ.get("HARBINGER_CONFIG") or "config.yaml")
    data: dict = {}
    root = Path.cwd()
    if p.exists():
        data = yaml.safe_load(p.read_text()) or {}
        root = p.resolve().parent

    server = data.get("server") or {}
    agent = data.get("agent") or {}
    state = data.get("state") or {}
    web = data.get("web") or {}

    token = os.environ.get("HARBINGER_AGENT_TOKEN") or agent.get("token")
    if token in ("", "change-me"):
        token = None

    return Config(
        host=str(server.get("host", "0.0.0.0")),
        port=int(server.get("port", 8080)),
        agent_token=token,
        writable_slots=list(agent.get("writable_slots", DEFAULT_WRITABLE_SLOTS)),
        snapshot=root / state.get("snapshot", "var/state.json"),
        web_dir=root / web.get("dir", "web"),
    )
