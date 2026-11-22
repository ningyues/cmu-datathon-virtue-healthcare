"""Serve facility search to the local CareLens frontend."""

import argparse
import json
from dataclasses import asdict
from functools import partial
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from pathlib import Path

from agents.env_config import DEFAULT_ENV_FILE
from app.facility_data import read_facilities
from app.nabh_verification import verification_service
from app.location_matching import LocationMatcher, rank_by_distance
from app.search_output import fit_score_value
from app.scoring_backend import PostgresScorer, ScoringUnavailable
from app.service_search import (
    SERVICES, SearchIntent, match_search_intent, parse_query, parse_query_with_agent, parse_search_intent,
)


class IntentParsingError(ValueError):
    """Preserve actionable agent errors across the HTTP boundary."""

    def __init__(self, error):
        self.details = error.as_dict()["error"]
        self.code = error.code
        super().__init__(error.clarification_question or str(error))

    @property
    def status(self):
        if self.code in {"configuration_error", "catalog_error"}:
            return HTTPStatus.SERVICE_UNAVAILABLE
        if self.code in {"model_error", "invalid_model_output"}:
            return HTTPStatus.BAD_GATEWAY
        return HTTPStatus.UNPROCESSABLE_ENTITY


def intent_agent_parser(env_file=DEFAULT_ENV_FILE):
    from agents.intent_agent import IntentError, SpecialityCatalog, parse_intent
    catalog = SpecialityCatalog()

    def parse(text):
        try:
            return parse_search_intent(parse_intent(text, catalog=catalog, env_file=env_file))
        except IntentError as error:
            raise IntentParsingError(error) from error
    return parse


def search_facilities(payload, *, facilities, matcher, parse, score):
    if not isinstance(payload, dict) or ("query" in payload) == ("intent" in payload):
        raise ValueError("Send one query string or one search intent object.")

    if "intent" in payload:
        request = parse_search_intent(payload["intent"])
    else:
        query = payload["query"]
        if not isinstance(query, str) or not query.strip():
            raise ValueError("Enter the care you need and your location.")
        request = parse(query.strip())
        if not isinstance(request, SearchIntent):
            request = SearchIntent(request.city, request.pincode,
                                   SERVICES[request.service_id].specialties,
                                   (request.service_id.replace('_', ' '),))

    address = ", ".join(part for part in (request.city, request.pincode) if part)
    location = matcher.resolve(address)
    if location.status != "resolved":
        raise ValueError(f"Could not resolve the location ({location.status}). Check the city, state, and PIN.")
    result = matcher.match(facilities, latitude=location.latitude, longitude=location.longitude)
    candidates = list(result['candidates'])
    scores = {row['unique_id']: row for row in score(candidates, request)}
    evidence = {row['unique_id']: row for row in match_search_intent(candidates, request)}
    nearby = []
    for row in candidates:
        details = scores.get(row['unique_id'])
        if details is None:
            continue
        proof = evidence.get(row['unique_id'], {})
        nearby.append({**row, 'fit_score': float(details['final_score']),
                       'score_details': details,
                       'service_match': 'listed_in_dataset' if proof.get('service_evidence') else (
                           'text_match' if details['service_score'] else 'related_specialty_only'),
                       'service_evidence': proof.get('service_evidence')})
    nearby = rank_by_distance(nearby)
    nearby.sort(key=lambda row: -row['fit_score'])

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
                "scoreBreakdown": {
                    "authority": float(row['score_details']['authority']),
                    "authoritySource": row['score_details']['flags_origin'],
                    "specialtyScore": row['score_details']['specialty_score'],
                    "serviceScore": row['score_details']['service_score'],
                    "rawScore": row['score_details']['raw_score'],
                    "maxRawScore": row['score_details']['max_raw_score'],
                    "matchScore100": float(row['score_details']['match_score_100']),
                    "specialties": row['score_details']['specialty_details'],
                    "services": row['score_details']['service_details'],
                },
                "trustScore": None,
                "serviceMatch": row["service_match"],
                "serviceEvidence": row["service_evidence"],
            }
            for row in nearby
        ],
    }


class SearchHandler(BaseHTTPRequestHandler):
    def __init__(self, search, *args, verify=None, **kwargs):
        self.search = search
        self.verify = verify
        super().__init__(*args, **kwargs)

    def do_POST(self):
        if self.path not in {"/api/search", "/api/nabh/verify"}:
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
            if self.path == "/api/nabh/verify":
                if self.verify is None:
                    self.respond(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "Verification is unavailable."})
                    return
                result = self.verify(payload)
            else:
                result = self.search(payload)
        except IntentParsingError as error:
            self.respond(error.status, {"error": error.details})
            return
        except ValueError as error:
            self.respond(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return
        except ScoringUnavailable as error:
            self.respond(HTTPStatus.SERVICE_UNAVAILABLE, {"error": str(error)})
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
    parsers = parser.add_mutually_exclusive_group()
    parsers.add_argument("--agent", action="store_true", help="Use the OpenAI API to parse free-text queries")
    parsers.add_argument("--intent-agent", action="store_true", help="Use the project's intent agent (default)")
    parsers.add_argument("--local-parser", action="store_true", help="Use the offline service-catalog parser")
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE,
                        help="Agent configuration file (default: agents/.env)")
    args = parser.parse_args()
    parse = (parse_query if args.local_parser else parse_query_with_agent if args.agent
             else intent_agent_parser(args.env_file))
    facilities = tuple(read_facilities())
    verify = verification_service(facilities, env_file=args.env_file)
    search = partial(search_facilities, facilities=facilities, matcher=LocationMatcher(),
                     parse=parse, score=PostgresScorer())
    with ThreadingHTTPServer(("127.0.0.1", args.port), partial(SearchHandler, search, verify=verify)) as server:
        print(f"Facility search API listening on http://127.0.0.1:{server.server_port}/api/search", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
