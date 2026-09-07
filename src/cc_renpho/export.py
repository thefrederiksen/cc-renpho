"""Writing measurements out as JSON and CSV."""

from __future__ import annotations

import csv
import json
from pathlib import Path

# The fields that carry information. A raw record has around seventy, but most
# are sync bookkeeping and hardware flags that are empty on every row - see the
# `empty-fields` finding in qa.py.
CSV_COLUMNS = [
    "localCreatedAt",
    "createdAt",
    "weight",
    "bmi",
    "bodyfat",
    "water",
    "muscle",
    "bone",
    "bmr",
    "visfat",
    "subfat",
    "protein",
    "bodyage",
    "sinew",
    "fatFreeWeight",
    "heartRate",
    "resistance",
    "deviceType",
    "mac",
]


def write_json(data, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def write_csv(records: list[dict], path: str | Path) -> Path:
    """One row per weigh-in. `resistance` is kept so the estimated-versus-measured
    distinction survives the export - dropping it would leave a reader unable to
    tell a computed body-fat figure from a sensed one."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            writer.writerow(record)
    return path


def read_json(path: str | Path) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
