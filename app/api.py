"""Serve facility search to the local CareLens frontend."""

import argparse
import json
from dataclasses import asdict
from functools import partial
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app.facility_data import read_facilities
from app.location_matching import LocationMatcher, rank_by_distance
from app.search_output import fit_score_value
from app.service_search import (
    match_search_intent, match_service, parse_query, parse_query_with_agent, parse_search_intent,
)


def search_facilities(payload, *, facilities, matcher, parse):
    if not isinstance(payload, dict) or ("query" in payload) == ("intent" in payload):
        raise ValueError("Send one query string or one search intent object.")

    if "intent" in payload:
        request = parse_search_intent(payload["intent"])
        matches = match_search_intent(facilities, request)
    else:
        query = payload["query"]
        if not isinstance(query, str) or not query.strip():
            raise ValueError("Enter the care you need and your location.")
        request = parse(query.strip())
        matches = match_service(facilities, request.service_id)

    address = ", ".join(part for part in (request.city, request.pincode) if part)
    location = matcher.resolve(address)
    if location.status != "resolved":
        raise ValueError(f"Could not resolve the location ({location.status}). Check the city, state, and PIN.")
    result = matcher.match(matches, latitude=location.latitude, longitude=location.longitude)
    nearby = rank_by_distance(result["candidates"])
    nearby.sort(key=lambda row: row["service_match"] != "listed_in_dataset")

    return {
        "queryLocation": asdict(location),
        "radiusKm": result["radius_km"],
        "facilities": [
            {
                "id": row["unique_id"],
                "name": row["name_standardized"] or row["name"],
                "type": row.get("facilityTypeId") or row["organization_type"] or None,
                "operatorType": row.get("operatorTypeId") or None,
                "address": ", ".join(dict.fromkeys(
                    row[field] for field in ("address_line1", "address_line2", "address_line3")
                    if row.get(field)
                )) or None,
                "area": ", ".join(filter(None, (row["address_city"], row["address_stateOrRegion"]))) or None,
                "postalCode": row["address_zipOrPostcode"],
                "website": row.get("officialWebsite") or None,
                "latitude": float(row["latitude"]),
                "longitude": float(row["longitude"]),
                "distanceKm": row["distance_km"],
                "fitScore": fit_score_value(row.get("fit_score")),
                "trustScore": None,
                "serviceMatch": row["service_match"],
                "serviceEvidence": row["service_evidence"],
            }
            for row in nearby
        ],
    }


class SearchHandler(BaseHTTPRequestHandler):
    def __init__(self, search, *args, **kwargs):
        self.search = search
        super().__init__(*args, **kwargs)

    def do_POST(self):
        if self.path != "/api/search":
            self.respond(HTTPStatus.NOT_FOUND, {"error": "Search endpoint not found."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 65536:
                raise ValueError("Send a JSON request body of up to 64 KiB.")
            payload = json.loads(self.rfile.read(length))
        except ValueError:
            self.respond(HTTPStatus.BAD_REQUEST, {"error": "Send a valid JSON request body of up to 64 KiB."})
            return
        try:
            result = self.search(payload)
        except ValueError as error:
            self.respond(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return
        self.respond(HTTPStatus.OK, result)

    def respond(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            # The frontend may cancel a search when the user starts another one.
            pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--agent", action="store_true", help="Use the OpenAI API to parse free-text queries")
    args = parser.parse_args()
    parse = parse_query_with_agent if args.agent else parse_query
    search = partial(search_facilities, facilities=tuple(read_facilities()), matcher=LocationMatcher(), parse=parse)
    with ThreadingHTTPServer(("127.0.0.1", args.port), partial(SearchHandler, search)) as server:
        print(f"Facility search API listening on http://127.0.0.1:{server.server_port}/api/search", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
