"""The collector loop: fetch, store, sleep. Failures leave the last good slot alone."""

from __future__ import annotations

import asyncio
import logging

import httpx2 as httpx

from ..config import DEFAULT_USER_AGENT
from ..state import StateStore

log = logging.getLogger("harbinger.collectors")


class Collector:
    name: str = ""
    slot: str = ""
    interval_s: float = 60.0

    async def fetch(self, client: httpx.AsyncClient) -> dict:
        """Return the slot body. Raise on any failure; the loop keeps the old slot."""
        raise NotImplementedError


def make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=30, headers={"User-Agent": DEFAULT_USER_AGENT})


def backoff_multiplier(failures: int) -> int:
    """1 until the third consecutive failure, then doubling, capped at 4 intervals."""
    if failures < 3:
        return 1
    return min(2 ** (failures - 2), 4)


async def run_collector(collector: Collector, store: StateStore, client: httpx.AsyncClient) -> None:
    failures = 0
    while True:
        try:
            body = await collector.fetch(client)
            store.set_slot(collector.slot, body)
            if failures:
                log.info("%s: recovered after %d failures", collector.name, failures)
            failures = 0
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 - any failure means keep the old slot and retry
            failures += 1
            log.warning("%s: fetch failed (%d in a row): %s", collector.name, failures, e)
        await asyncio.sleep(collector.interval_s * backoff_multiplier(failures))
