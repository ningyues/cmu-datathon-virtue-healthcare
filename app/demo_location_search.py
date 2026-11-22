"""Run a specialty and location search against the checked-in CSV snapshots."""

import argparse
import json
import sys
from pathlib import Path

from app.facility_data import FACILITIES, read_facilities
from app.location_matching import LocationMatcher, PIN_PATTERN
from app.search_output import print_nearby_results
from app.service_search import (
    match_search_intent, match_service, parse_query, parse_query_with_agent, parse_search_intent,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--specialty", help="Dataset specialty, e.g. nephrology")
    mode.add_argument("--query", help='Service and location, e.g. "dialysis near Hyderabad 500003"')
    mode.add_argument(
        "--intent", "--search-output", metavar="FILE",
        help="Read agent-parsed search intent JSON from a file or - for stdin",
    )
    parser.add_argument("--agent", action="store_true", help="Use the OpenAI API to parse --query")
    parser.add_argument(
        "--sort", choices=("fit", "evidence", "distance"), default="fit",
        help="Rank by Fit Score (default), dataset service evidence, or distance",
    )
    parser.add_argument("--city", help='City or district, optionally with state, e.g. "Hyderabad, Telangana"')
    parser.add_argument("--pincode", help="Six-digit India PIN code")
    args = parser.parse_args()

    city = (args.city or "").strip()
    pincode = (args.pincode or "").strip()
    specialty = args.specialty.strip().casefold() if args.specialty is not None else None
    service_id = None
    intent = None
    if args.intent is not None:
        if args.agent:
            parser.error("--agent requires --query")
        if city or pincode:
            parser.error("provide the location in the intent JSON")
        try:
            if args.intent == "-":
                payload = json.load(sys.stdin)
            else:
                payload = json.loads(Path(args.intent).read_text(encoding="utf-8-sig"))
            intent = parse_search_intent(payload)
        except (OSError, ValueError) as error:
            parser.error(f"could not read search intent ({error})")
        city, pincode = intent.city, intent.pincode
    elif args.query is not None:
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
    rows = read_facilities(FACILITIES)
    if intent is not None:
        candidates = list(match_search_intent(rows, intent))
    elif service_id is not None:
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

    nearby = result["candidates"]
    service_label = ", ".join(intent.service) if intent is not None else service_id
    print(f"Origin: {location['label']} ({location['source']}, approximate)")
    if service_label:
        listed = sum(row["service_match"] == "listed_in_dataset" for row in candidates)
        print(f"Service: {service_label}")
        print(f"Dataset service claims: {listed}")
        print(f"Related specialty only: {len(candidates) - listed}")
    else:
        print(f"Dataset specialty matches: {len(candidates)}")
    print(f"Within {result['radius_km']:g} km: {len(nearby)} (straight-line distance)")
    if service_label:
        nearby_listed = sum(row["service_match"] == "listed_in_dataset" for row in nearby)
        print(f"Nearby: {nearby_listed} with dataset claims, {len(nearby) - nearby_listed} specialty only")
    print(f"Distance unavailable: {len(result['unlocated_candidates'])}")
    print("Service availability is unverified.")
    print_nearby_results(nearby, sort_by=args.sort, service_search=bool(service_label))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
