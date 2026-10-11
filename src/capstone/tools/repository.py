"""Read immutable seed tables; keep mutable state in a separate runtime copy (M2)."""

import csv
import json
import shutil
from pathlib import Path

from capstone.settings import get_settings

# Tables that actions append to. Everything else is read-only reference data.
MUTABLE_TABLES = {"refunds", "replacements", "goodwill_credits", "human_queue"}
HUMAN_QUEUE_FIELDS = ["queue_id", "customer_ref", "order_ref", "trigger", "note"]


class Repository:
    def __init__(self, seed_dir: Path, state_dir: Path):
        self.seed_dir = Path(seed_dir)
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, table: str) -> Path:
        runtime = self.state_dir / f"{table}.csv"
        if table in MUTABLE_TABLES:
            if not runtime.exists():
                seed = self.seed_dir / f"{table}.csv"
                if seed.exists():
                    shutil.copyfile(seed, runtime)
                elif table == "human_queue":
                    runtime.write_text(",".join(HUMAN_QUEUE_FIELDS) + "\n")
            return runtime
        return self.seed_dir / f"{table}.csv"

    def rows(self, table: str) -> list[dict]:
        with open(self._path(table), newline="") as f:
            return list(csv.DictReader(f))

    def find(self, table: str, **equals) -> list[dict]:
        return [r for r in self.rows(table) if all(r.get(k) == v for k, v in equals.items())]

    def get(self, table: str, **equals) -> dict | None:
        found = self.find(table, **equals)
        return found[0] if found else None

    def append(self, table: str, row: dict) -> None:
        if table not in MUTABLE_TABLES:
            raise ValueError(f"{table} is read-only reference data")
        path = self._path(table)
        with open(path, newline="") as f:
            fields = csv.DictReader(f).fieldnames
        with open(path, "a", newline="") as f:
            csv.DictWriter(f, fieldnames=fields).writerow({k: row.get(k, "") for k in fields})

    def next_id(self, table: str, id_field: str, prefix: str, width: int) -> str:
        numbers = [int(r[id_field].rsplit("-", 1)[1]) for r in self.rows(table)]
        return f"{prefix}-{max(numbers, default=0) + 1:0{width}d}"

    # Idempotency ledger: a retried call with the same key returns the original result.
    def _ledger_path(self) -> Path:
        return self.state_dir / "idempotency.json"

    def ledger_get(self, key: str) -> dict | None:
        path = self._ledger_path()
        return json.loads(path.read_text()).get(key) if path.exists() else None

    def ledger_put(self, key: str, result: dict) -> None:
        path = self._ledger_path()
        ledger = json.loads(path.read_text()) if path.exists() else {}
        ledger[key] = result
        path.write_text(json.dumps(ledger, indent=2))

    def reset(self) -> None:
        """Discard all mutable runtime state and re-seed from the immutable tables."""
        shutil.rmtree(self.state_dir, ignore_errors=True)
        self.state_dir.mkdir(parents=True, exist_ok=True)


def get_repository() -> Repository:
    s = get_settings()
    return Repository(s.seed_dir, s.state_dir)
