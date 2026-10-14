"""Simulated Data Inventory agent (Agente 1 del PIMS).

Locates the records of a data subject only in the systems registered in the
inventory (a minimal record of processing activities) and keeps provenance.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from agents.common import read_json


class InventoryAgent:
    name = "inventory-agent-sim"

    def __init__(self, inventory_path: Path, records_path: Path) -> None:
        self.inventory_path = Path(inventory_path)
        self.records_path = Path(records_path)

    def systems(self) -> list[dict[str, Any]]:
        return read_json(self.inventory_path)["systems"]

    def records_sha256(self) -> str:
        return hashlib.sha256(self.records_path.read_bytes()).hexdigest()

    def known_principals(self) -> list[str]:
        return sorted({item["principal_id"] for item in read_json(self.records_path)})

    def locate(self, principal_id: str) -> dict[str, Any]:
        systems = {item["system_id"] for item in self.systems()}
        records = [
            item
            for item in read_json(self.records_path)
            if item.get("principal_id") == principal_id
            and item.get("source_system") in systems
        ]
        return {
            "agent": self.name,
            "systems_consulted": sorted(systems),
            "records": records,
            "records_sha256": self.records_sha256(),
        }
