"""JSON repository for DSAR cases, shaped after the `dsar_requests` table.

Each case lives in `<root>/<case_id>/` with `request.json` and
`case-package.json`, the same layout produced by the console simulator.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any


CASE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


class CaseNotFound(KeyError):
    """Raised when a case identifier does not exist in the store."""


def check_case_id(case_id: str) -> str:
    if not isinstance(case_id, str) or not CASE_ID_RE.match(case_id):
        raise ValueError(
            "request_id solo admite letras, numeros, punto, guion y guion bajo"
        )
    return case_id


def write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        os.replace(temp_name, path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise


class CaseStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def case_dir(self, case_id: str) -> Path:
        return self.root / check_case_id(case_id)

    def exists(self, case_id: str) -> bool:
        return (self.case_dir(case_id) / "case-package.json").is_file()

    def save(self, request: dict[str, Any], package: dict[str, Any]) -> None:
        directory = self.case_dir(package["case_id"])
        write_json_atomic(directory / "request.json", request)
        write_json_atomic(directory / "case-package.json", package)

    def load(self, case_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        try:
            directory = self.case_dir(case_id)
        except ValueError:
            raise CaseNotFound(case_id) from None
        if not (directory / "case-package.json").is_file():
            raise CaseNotFound(case_id)
        request = json.loads((directory / "request.json").read_text(encoding="utf-8"))
        package = json.loads(
            (directory / "case-package.json").read_text(encoding="utf-8")
        )
        return request, package

    def list(self) -> list[dict[str, Any]]:
        if not self.root.is_dir():
            return []
        packages = []
        for path in self.root.glob("*/case-package.json"):
            packages.append(json.loads(path.read_text(encoding="utf-8")))
        packages.sort(key=lambda item: (item["received_at"], item["case_id"]), reverse=True)
        return packages
