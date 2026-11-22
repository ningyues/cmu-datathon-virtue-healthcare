"""Read the facility snapshot used by both search entry points."""

import csv
import gzip
import lzma
from pathlib import Path


FACILITIES = Path(__file__).resolve().parents[1] / "data/processed/facilities_clean.csv.xz"


def read_facilities(path: Path = FACILITIES):
    snapshot = path if path.is_file() else path.with_suffix(".gz")
    opener = lzma.open if snapshot.suffix == ".xz" else gzip.open
    with opener(snapshot, "rt", encoding="utf-8-sig", newline="") as file:
        # Python 3.10's CSV reader rejects the NULs present in the snapshot.
        yield from csv.DictReader(line.replace("\0", "") for line in file)
