import asyncio

import pytest

from harbinger.collectors.base import Collector, backoff_multiplier, run_collector
from harbinger.state import StateStore


def test_backoff_multiplier():
    assert [backoff_multiplier(n) for n in range(0, 7)] == [1, 1, 1, 2, 4, 4, 4]


class Flaky(Collector):
    name = "flaky"
    slot = "notices"
    interval_s = 0.01

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    async def fetch(self, client):
        self.calls += 1
        outcome = self.outcomes.pop(0) if self.outcomes else "ok"
        if outcome == "fail":
            raise RuntimeError("feed down")
        return {"text": f"call {self.calls}"}


@pytest.mark.asyncio
async def test_failures_leave_last_good_slot(tmp_path):
    store = StateStore(tmp_path / "state.json")
    collector = Flaky(["ok", "fail", "fail", "ok"])
    task = asyncio.create_task(run_collector(collector, store, client=None))
    try:
        await asyncio.sleep(0.2)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert collector.calls >= 4
    assert store.get_slot("notices")["text"].startswith("call ")


@pytest.mark.asyncio
async def test_invalid_body_counts_as_failure(tmp_path):
    class Bad(Collector):
        name, slot, interval_s = "bad", "notices", 0.01

        async def fetch(self, client):
            return {"priority": "urgent"}  # fails schema: no text, bad enum

    store = StateStore(tmp_path / "state.json")
    task = asyncio.create_task(run_collector(Bad(), store, client=None))
    await asyncio.sleep(0.05)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert store.get_slot("notices") is None
