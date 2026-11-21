"""Resolve a user location and measure straight-line distances to prefiltered facilities."""

import csv
import gzip
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from math import isfinite
from pathlib import Path
from statistics import median

from pipeline.audit_helpers import km, point, state


POSTAL_OFFICES = (
    Path(__file__).resolve().parents[1] / "data/processed/pincode_offices_clean.csv.gz"
)
DEFAULT_RADIUS_KM = 30.0
PIN_PATTERN = re.compile(r"(?<!\w)[1-9]\d{5}(?!\w)", re.ASCII)
DISTRICT_ALIASES = {
    "ahmedabad": "ahmadabad",
    "bangalore": "bengaluru urban",
    "bengaluru": "bengaluru urban",
    "delhi": "new delhi",
    "gurgaon": "gurugram",
    "vizag": "visakhapatanam",
    "visakhapatnam": "visakhapatanam",
}

Coordinates = tuple[float, float]
StatePoints = dict[str, set[Coordinates]]
Facility = Mapping[str, object]


@dataclass(frozen=True)
class QueryLocation:
    status: str
    source: str | None = None
    label: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    approximate: bool | None = None


def _district_key(place: str) -> str:
    key = " ".join(re.findall(r"\w+", place.casefold()))
    return DISTRICT_ALIASES.get(key, key)


def _safe_point(latitude: object, longitude: object) -> Coordinates | None:
    try:
        return point(latitude, longitude)
    except OverflowError:
        return None


class LocationMatcher:
    """Load the cleaned postal data once and reuse the matcher across requests."""

    def __init__(self, postal_offices_path: str | Path = POSTAL_OFFICES):
        self._pins: dict[str, dict[tuple[str, str], set[Coordinates]]] = defaultdict(
            lambda: defaultdict(set)
        )
        self._districts: dict[str, StatePoints] = defaultdict(lambda: defaultdict(set))
        self._state_names: dict[str, str] = {}

        with gzip.open(postal_offices_path, "rt", encoding="utf-8-sig", newline="") as file:
            offices = csv.DictReader(file)
            for office in offices:
                state_key = office["state_key"]
                pincode = office["pincode"]
                if not state_key or not PIN_PATTERN.fullmatch(pincode):
                    continue

                self._state_names.setdefault(state_key, office["statename"].strip().title())
                district = _district_key(office["district_key"])
                pin_points = self._pins[pincode][state_key, district]
                district_points = self._districts[district][state_key] if district else None
                # Retain state candidates even when their office coordinates are unusable.
                if office["coordinate_status"] != "usable":
                    continue

                coordinates = _safe_point(office["latitude"], office["longitude"])
                if coordinates is not None:
                    pin_points.add(coordinates)
                    if district_points is not None:
                        district_points.add(coordinates)

    def _address_parts(self, address: str, has_pin: bool) -> tuple[set[str], set[str]]:
        parts = []
        for segment in re.split(r"[,;\n]+", PIN_PATTERN.sub(" ", address)):
            words = re.findall(r"\w+", segment.casefold())
            if words[:2] == ["close", "to"]:
                words = words[2:]
            elif words and words[0] in {"near", "around", "in"}:
                words = words[1:]
            if words and words[-1] == "india":
                words.pop()
            if words:
                parts.append(words)

        districts, states = set(), set()
        for words in parts:
            place = " ".join(words)
            state_key = state(place)
            district_key = _district_key(place)
            if state_key in self._state_names and (
                has_pin or len(parts) > 1 or district_key not in self._districts
            ):
                states.add(state_key)
            elif district_key in self._districts:
                districts.add(district_key)
            else:
                # Also accept an area followed by a state without a comma.
                for split in range(1, len(words)):
                    district_key = _district_key(" ".join(words[:split]))
                    state_key = state(" ".join(words[split:]))
                    if district_key in self._districts and state_key in self._state_names:
                        districts.add(district_key)
                        states.add(state_key)
                        break

        return districts, states

    def _postal_location(
        self, areas: StatePoints, source: str, label: str, allowed_states: set[str]
    ) -> QueryLocation:
        matching_states = areas.keys() & allowed_states if allowed_states else areas.keys()
        if not matching_states:
            return QueryLocation("location_conflict")
        if len(matching_states) > 1:
            return QueryLocation("ambiguous_location")

        state_key = next(iter(matching_states))
        points = areas[state_key]
        if not points:
            return QueryLocation("postal_coordinates_unavailable")

        center = (median(lat for lat, _ in points), median(lon for _, lon in points))
        # Use an actual postal-office point near the middle of the area.
        latitude, longitude = min(points, key=lambda origin: (km(center, origin), origin))
        return QueryLocation(
            "resolved", source, f"{label}, {self._state_names[state_key]}",
            latitude, longitude, approximate=True,
        )

    def resolve(
        self,
        address: str | None = None,
        *,
        latitude: float | str | None = None,
        longitude: float | str | None = None,
    ) -> QueryLocation:
        """Accept user-supplied coordinates, an India PIN, or a city/district with optional state."""
        if latitude is not None or longitude is not None:
            coordinates = _safe_point(latitude, longitude)
            if coordinates is None:
                return QueryLocation("invalid_coordinates")
            return QueryLocation(
                "resolved", "coordinates", latitude=coordinates[0],
                longitude=coordinates[1], approximate=False,
            )
        if not address or not address.strip():
            return QueryLocation("missing_location")

        pins = set(PIN_PATTERN.findall(address))
        districts, states = self._address_parts(address, bool(pins))
        if len(pins) > 1 or len(districts) > 1 or len(states) > 1:
            return QueryLocation("ambiguous_location")

        district = next(iter(districts), None)
        if pins:
            pincode = next(iter(pins))
            pin_areas = self._pins.get(pincode)
            if pin_areas is None:
                return QueryLocation("unknown_pin")

            areas: StatePoints = defaultdict(set)
            for (state_key, district_key), points in pin_areas.items():
                if district is None or district_key == district:
                    areas[state_key].update(points)
            return self._postal_location(areas, "postal_pin", pincode, states)
        if district is None:
            return QueryLocation("unrecognized_address")

        return self._postal_location(
            self._districts[district], "postal_district", district.title(), states,
        )

    def match(
        self,
        facilities: Iterable[Facility],
        address: str | None = None,
        *,
        latitude: float | str | None = None,
        longitude: float | str | None = None,
        radius_km: float = DEFAULT_RADIUS_KM,
    ) -> dict:
        """Return nearby facilities in input order and retain unlocated rows for review."""
        if not isfinite(radius_km) or radius_km <= 0:
            raise ValueError("radius_km must be a positive finite number")

        location = self.resolve(address, latitude=latitude, longitude=longitude)
        origin = _safe_point(location.latitude, location.longitude)
        candidates, unlocated_candidates = [], []
        for facility in facilities:
            candidate = _with_distance(facility, origin)
            distance = candidate["distance_km"]
            if distance is None:
                unlocated_candidates.append(candidate)
            elif distance <= radius_km:
                candidates.append(candidate)

        return {
            "query_location": asdict(location),
            "radius_km": radius_km,
            "candidates": candidates,
            "unlocated_candidates": unlocated_candidates,
        }


def _with_distance(facility: Facility, origin: Coordinates | None) -> dict:
    distance = None
    geography_status = facility.get("geography_status")
    facility_point = _safe_point(facility.get("latitude"), facility.get("longitude"))
    if geography_status == "coordinate_location_conflict":
        status = "facility_coordinate_conflict"
    elif facility_point is None:
        status = "facility_coordinates_unavailable"
    elif (
        geography_status != "postal_distance_within_50_km"
        or facility.get("pin_status") != "state_consistent"
    ):
        status = "facility_location_needs_review"
    elif origin is None:
        status = "query_location_unavailable"
    else:
        distance = km(origin, facility_point)
        status = "available"
    return {**facility, "distance_km": distance, "distance_status": status}


def rank_by_distance(candidates: Iterable[dict]) -> list[dict]:
    """Sort nearest first, keeping unrankable candidates at the end in input order."""
    return sorted(
        candidates,
        key=lambda row: float("inf") if row["distance_km"] is None else row["distance_km"],
    )
