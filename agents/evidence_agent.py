"""Simulated Evidence and Audit agent (Agente 4 del PIMS).

Keeps an append-only JSON Lines log where every entry includes the hash of
the previous one. Altering or deleting any line breaks the chain, which
`verify_chain` detects. Entries store hashes and states, never PII.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from agents.common import json_hash

GENESIS_HASH = "0" * 64


class EvidenceAgent:
    name = "evidence-agent-sim"

    def __init__(self, log_path: Path) -> None:
        self.log_path = Path(log_path)
        self._lock = threading.Lock()

    def entries(self, case_id: str | None = None) -> list[dict[str, Any]]:
        if not self.log_path.is_file():
            return []
        items = [
            json.loads(line)
            for line in self.log_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if case_id is not None:
            items = [item for item in items if item["case_id"] == case_id]
        return items

    def record(
        self, case_id: str, event_type: str, payload: dict[str, Any], recorded_at: str
    ) -> dict[str, Any]:
        with self._lock:
            previous = self.entries()
            entry = {
                "sequence": len(previous) + 1,
                "case_id": case_id,
                "event_type": event_type,
                "payload": payload,
                "recorded_at": recorded_at,
                "prev_hash": previous[-1]["entry_hash"] if previous else GENESIS_HASH,
            }
            entry["entry_hash"] = json_hash(entry)
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
            return entry

    def verify_chain(self) -> dict[str, Any]:
        errors = []
        expected_prev = GENESIS_HASH
        try:
            items = self.entries()
        except json.JSONDecodeError:
            return {"valid": False, "entries": 0, "errors": ["Linea de evidencia ilegible"]}
        for position, item in enumerate(items, start=1):
            unsigned = {key: value for key, value in item.items() if key != "entry_hash"}
            if item.get("sequence") != position:
                errors.append(f"Secuencia rota en la entrada {position}")
            if item.get("prev_hash") != expected_prev:
                errors.append(f"Encadenamiento roto en la entrada {position}")
            if json_hash(unsigned) != item.get("entry_hash"):
                errors.append(f"Huella alterada en la entrada {position}")
            expected_prev = item.get("entry_hash")
        return {"valid": not errors, "entries": len(items), "errors": errors}
