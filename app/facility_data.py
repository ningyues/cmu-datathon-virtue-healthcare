"""Read the facility snapshot used by both search entry points."""

import csv
import gzip
import lzma
from pathlib import Path

from pipeline.facility_names import read_name_decisions


FACILITIES = Path(__file__).resolve().parents[1] / "data/processed/facilities_clean.csv.xz"


def read_facilities(path: Path = FACILITIES):
    name_decisions = read_name_decisions()
    snapshot = path if path.is_file() else path.with_suffix(".gz")
    opener = lzma.open if snapshot.suffix == ".xz" else gzip.open
    with opener(snapshot, "rt", encoding="utf-8-sig", newline="") as file:
        # Python 3.10's CSV reader rejects the NULs present in the snapshot.
        for row in csv.DictReader(line.replace("\0", "") for line in file):
            decision = name_decisions.get((row.get("unique_id") or "").lower())
            if decision and row.get("name_standardized") == decision["expected_name"]:
                row["name_standardized"] = decision["cleaned_name"]
            yield row
