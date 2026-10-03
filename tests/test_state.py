import json
from pathlib import Path

import pytest

from harbinger.state import SlotValidationError, StateStore

REPO = Path(__file__).resolve().parent.parent
SAMPLE = REPO / "web" / "sample" / "state.json"


def test_starts_empty(tmp_path):
    store = StateStore(tmp_path / "state.json")
    doc = store.document()
    assert doc["slots"] == {}
    assert "generated_at" in doc
    assert not store.has_data


def test_set_slot_stamps_updated_at_and_snapshots(tmp_path):
    snap = tmp_path / "var" / "state.json"
    store = StateStore(snap)
    saved = store.set_slot("notices", {"text": "hello"})
    assert "updated_at" in saved
    assert snap.exists()
    on_disk = json.loads(snap.read_text())
    assert on_disk["slots"]["notices"]["text"] == "hello"


def test_set_slot_rejects_bad_body(tmp_path):
    store = StateStore(tmp_path / "state.json")
    with pytest.raises(SlotValidationError) as e:
        store.set_slot("notices", {"text": "x", "priority": "urgent"})
    assert "priority" in str(e.value)
    with pytest.raises(SlotValidationError):
        store.set_slot("news", {"items": "not a list"})
    with pytest.raises(SlotValidationError):
        store.set_slot("news", ["not", "an", "object"])


def test_set_slot_unknown_slot(tmp_path):
    store = StateStore(tmp_path / "state.json")
    with pytest.raises(KeyError):
        store.set_slot("calendar", {})


def test_snapshot_reloads(tmp_path):
    snap = tmp_path / "state.json"
    StateStore(snap).set_slot("notices", {"text": "persisted"})
    again = StateStore(snap)
    assert again.get_slot("notices")["text"] == "persisted"


def test_load_sample_document(tmp_path):
    store = StateStore(tmp_path / "state.json")
    store.load(SAMPLE)
    assert set(store.document()["slots"]) == {"weather", "transit", "bikes", "news", "notices"}
    ages = store.ages()
    assert all(v is not None for v in ages.values())


def test_load_rejects_invalid_document(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"generated_at": "2026-10-03T00:00:00-04:00", "slots": {"news": {}}}))
    with pytest.raises(SlotValidationError):
        StateStore(tmp_path / "state.json").load(bad)
