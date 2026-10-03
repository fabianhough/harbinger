"""Collectors fill the measured slots: one per external feed, each on its own cadence."""

from __future__ import annotations

from ..config import Config
from .base import Collector, make_client, run_collector
from .citibike import CitiBikeCollector
from .nws import NWSCollector

__all__ = ["Collector", "build_collectors", "make_client", "run_collector"]


def build_collectors(cfg: Config) -> list[Collector]:
    """One collector per configured section. No section, no collector."""
    out: list[Collector] = []
    if cfg.bikes:
        out.append(CitiBikeCollector(cfg.bikes))
    if cfg.weather:
        out.append(NWSCollector(cfg.weather))
    return out
