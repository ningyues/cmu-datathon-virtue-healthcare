"""Run a specialty and location search against the checked-in CSV snapshots."""

import argparse
import csv
import gzip
import json
from pathlib import Path

from app.location_matching import LocationMatcher, PIN_PATTERN, rank_by_distance


FACILITIES = Path(__file__).resolve().parents[1] / "data/processed/facilities_clean.csv.gz"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--specialty", required=True, help="Dataset specialty, e.g. nephrology")
    parser.add_argument("--city", help='City or district, optionally with state, e.g. "Hyderabad, Telangana"')
    parser.add_argument("--pincode", help="Six-digit India PIN code")
    args = parser.parse_args()

    city = (args.city or "").strip()
    pincode = (args.pincode or "").strip()
    specialty = args.specialty.strip().casefold()
    if not specialty:
        parser.error("--specialty cannot be empty")
    if not city and not pincode:
        parser.error("provide --city, --pincode, or both")
    if pincode and not PIN_PATTERN.fullmatch(pincode):
        parser.error("--pincode must contain six digits and start with 1–9")

    address = ", ".join(part for part in (city, pincode) if part)
    with gzip.open(FACILITIES, "rt", encoding="utf-8-sig", newline="") as file:
        # The snapshot contains NULs that Python 3.10's CSV reader rejects.
        rows = csv.DictReader(line.replace("\0", "") for line in file)
        specialty_candidates = [
            row for row in rows
            if any(
                item.casefold() == specialty
                for item in json.loads(row["specialties"] or "[]")
            )
        ]

    result = LocationMatcher().match(specialty_candidates, address)
    location = result["query_location"]
    status = location["status"]
    if status == "location_conflict":
        parser.error(f"could not resolve location ({status}). Check the city, state, and PIN.")
    if status != "resolved":
        parser.error(
            f"could not resolve location ({status}). Try a valid PIN or add the state."
        )

    nearby = rank_by_distance(result["candidates"])
    print(f"Origin: {location['label']} ({location['source']}, approximate)")
    print(f"Dataset specialty matches: {len(specialty_candidates)}")
    print(f"Within {result['radius_km']:g} km: {len(nearby)} (straight-line distance)")
    print(f"Distance unavailable: {len(result['unlocated_candidates'])}")
    print("Service availability is unverified.")
    for row in nearby[:10]:
        name = row["name_standardized"] or row["name"]
        print(f"{row['distance_km']:6.1f} km  {name} ({row['address_city']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
