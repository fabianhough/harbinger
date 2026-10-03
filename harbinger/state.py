"""The state document: one in-memory copy, validated on every write, snapshotted to disk."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema" / "state.schema.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class SlotValidationError(ValueError):
    """The slot body does not match the schema. The message names the field."""


class StateStore:
    def __init__(self, snapshot: Path | None = None, schema_path: Path = SCHEMA_PATH):
        self._schema = json.loads(Path(schema_path).read_text())
        self._doc_validator = Draft202012Validator(self._schema, format_checker=FormatChecker())
        self._slot_validators: dict[str, Draft202012Validator] = {}
        self._slots: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._snapshot = Path(snapshot) if snapshot else None
        if self._snapshot and self._snapshot.exists():
            self.load(self._snapshot)

    # ---------- introspection ----------

    @property
    def slot_names(self) -> list[str]:
        return list(self._schema["properties"]["slots"]["properties"])

    @property
    def has_data(self) -> bool:
        return bool(self._slots)

    def _validator_for(self, slot: str) -> Draft202012Validator:
        if slot not in self._slot_validators:
            sub = {
                "$schema": self._schema["$schema"],
                "$defs": self._schema["$defs"],
                "$ref": f"#/$defs/{slot}",
            }
            self._slot_validators[slot] = Draft202012Validator(sub, format_checker=FormatChecker())
        return self._slot_validators[slot]

    # ---------- read ----------

    def document(self) -> dict:
        """The full state as the page consumes it. generated_at is assembly time."""
        with self._lock:
            return {"generated_at": now_iso(), "slots": deepcopy(self._slots)}

    def get_slot(self, name: str) -> dict | None:
        with self._lock:
            return deepcopy(self._slots.get(name))

    def ages(self) -> dict[str, float | None]:
        """Seconds since each slot's updated_at; None for slots not yet written."""
        now = datetime.now(timezone.utc)
        out: dict[str, float | None] = {}
        with self._lock:
            for name in self.slot_names:
                slot = self._slots.get(name)
                if slot is None:
                    out[name] = None
                else:
                    out[name] = (now - datetime.fromisoformat(slot["updated_at"])).total_seconds()
        return out

    # ---------- write ----------

    def set_slot(self, name: str, body: dict) -> dict:
        """Replace one slot. Fills updated_at when absent, validates, snapshots."""
        if name not in self.slot_names:
            raise KeyError(name)
        if not isinstance(body, dict):
            raise SlotValidationError("slot body must be a JSON object")
        obj = dict(body)
        obj.setdefault("updated_at", now_iso())
        errors = sorted(self._validator_for(name).iter_errors(obj), key=lambda e: list(e.path))
        if errors:
            raise SlotValidationError("; ".join(
                f"{'/'.join(str(p) for p in e.path) or '(root)'}: {e.message}" for e in errors
            ))
        with self._lock:
            self._slots[name] = obj
            self._write_snapshot()
        return obj

    def load(self, path: Path) -> None:
        """Replace all slots from a full state document on disk (snapshot or seed)."""
        doc = json.loads(Path(path).read_text())
        errors = sorted(self._doc_validator.iter_errors(doc), key=lambda e: list(e.path))
        if errors:
            raise SlotValidationError(f"{path}: " + "; ".join(
                f"{'/'.join(str(p) for p in e.path) or '(root)'}: {e.message}" for e in errors
            ))
        with self._lock:
            self._slots = deepcopy(doc["slots"])

    def save(self) -> None:
        with self._lock:
            self._write_snapshot()

    def _write_snapshot(self) -> None:
        """Caller holds the lock. Temp file then rename, so a crash never leaves a torn file."""
        if not self._snapshot:
            return
        self._snapshot.parent.mkdir(parents=True, exist_ok=True)
        doc = {"generated_at": now_iso(), "slots": self._slots}
        fd, tmp = tempfile.mkstemp(dir=self._snapshot.parent, prefix=".state-", suffix=".json")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(doc, f, indent=2)
            os.replace(tmp, self._snapshot)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
