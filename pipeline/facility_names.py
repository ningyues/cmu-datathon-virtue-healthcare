"""Read the reviewed display-name decisions shared by cleaning and search."""

import csv
from pathlib import Path


def read_name_decisions():
    path = Path(__file__).with_name("facility_name_decisions.csv")
    decisions = {}
    with path.open(encoding="utf-8", newline="") as file:
        for decision in csv.DictReader(file):
            uid = decision["unique_id"]
            cleaned_name = decision["cleaned_name"].strip()
            if uid in decisions:
                raise ValueError(f"Duplicate facility name decision: {uid}")
            if not cleaned_name or cleaned_name == decision["expected_name"]:
                raise ValueError(f"Invalid facility name decision: {uid}")
            decision["cleaned_name"] = cleaned_name
            decisions[uid] = decision
    return decisions
