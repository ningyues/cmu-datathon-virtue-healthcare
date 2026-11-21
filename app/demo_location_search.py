"""Run a specialty and location search against the checked-in CSV snapshots."""

import argparse
import csv
import gzip
import json
import lzma
from pathlib import Path

from app.location_matching import LocationMatcher, PIN_PATTERN, rank_by_distance
from app.service_search import match_service, parse_query, parse_query_with_agent


FACILITIES = Path(__file__).resolve().parents[1] / "data/processed/facilities_clean.csv.xz"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--specialty", help="Dataset specialty, e.g. nephrology")
    mode.add_argument("--query", help='Service and location, e.g. "dialysis near Hyderabad 500003"')
    parser.add_argument("--agent", action="store_true", help="Use the OpenAI API to parse --query")
    parser.add_argument("--sort", choices=("evidence", "distance"), help="Sort service searches by evidence or distance")
    parser.add_argument("--city", help='City or district, optionally with state, e.g. "Hyderabad, Telangana"')
    parser.add_argument("--pincode", help="Six-digit India PIN code")
    args = parser.parse_args()

    city = (args.city or "").strip()
    pincode = (args.pincode or "").strip()
    specialty = args.specialty.strip().casefold() if args.specialty is not None else None
    service_id = None
    if args.query is not None:
        if city or pincode:
            parser.error("include the location in --query")
        try:
            parse = parse_query_with_agent if args.agent else parse_query
            query = parse(args.query)
        except ValueError as error:
            parser.error(str(error))
        service_id = query.service_id
        city, pincode = query.city, query.pincode
    elif not specialty or args.agent:
        parser.error("provide a specialty or use --agent with --query")
    if not city and not pincode:
        parser.error("provide --city, --pincode, or both")
    if pincode and not PIN_PATTERN.fullmatch(pincode):
        parser.error("--pincode must contain six digits and start with 1–9")

    address = ", ".join(part for part in (city, pincode) if part)
    snapshot = FACILITIES if FACILITIES.is_file() else FACILITIES.with_suffix(".gz")
    opener = lzma.open if snapshot.suffix == ".xz" else gzip.open
    with opener(snapshot, "rt", encoding="utf-8-sig", newline="") as file:
        # The snapshot contains NULs that Python 3.10's CSV reader rejects.
        rows = csv.DictReader(line.replace("\0", "") for line in file)
        if service_id is not None:
            candidates = list(match_service(rows, service_id))
        else:
            candidates = [
                row for row in rows
                if any(item.casefold() == specialty for item in json.loads(row["specialties"] or "[]"))
            ]

    result = LocationMatcher().match(candidates, address)
    location = result["query_location"]
    status = location["status"]
    if status == "location_conflict":
        parser.error(f"could not resolve location ({status}). Check the city, state, and PIN.")
    if status != "resolved":
        parser.error(
            f"could not resolve location ({status}). Try a valid PIN or add the state."
        )

    nearby = rank_by_distance(result["candidates"])
    if service_id is not None and args.sort != "distance":
        nearby.sort(key=lambda row: row["service_match"] != "listed_in_dataset")
    print(f"Origin: {location['label']} ({location['source']}, approximate)")
    if service_id is not None:
        listed = sum(row["service_match"] == "listed_in_dataset" for row in candidates)
        print(f"Service: {service_id}")
        print(f"Dataset service claims: {listed}")
        print(f"Related specialty only: {len(candidates) - listed}")
    else:
        print(f"Dataset specialty matches: {len(candidates)}")
    print(f"Within {result['radius_km']:g} km: {len(nearby)} (straight-line distance)")
    if service_id is not None:
        nearby_listed = sum(row["service_match"] == "listed_in_dataset" for row in nearby)
        print(f"Nearby: {nearby_listed} with dataset claims, {len(nearby) - nearby_listed} specialty only")
    print(f"Distance unavailable: {len(result['unlocated_candidates'])}")
    print("Service availability is unverified.")
    for row in nearby[:10]:
        name = row["name_standardized"] or row["name"]
        print(f"{row['distance_km']:6.1f} km  {name} ({row['address_city']})")
        if service_id is not None:
            evidence = row["service_evidence"]
            if evidence:
                print(f"           Dataset claim ({evidence['field']}): {evidence['text']}")
            else:
                print("           Related specialty only. Service not verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
