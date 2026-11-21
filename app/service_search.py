"""Map search requests to a service catalog and collect facility-level evidence."""

from dataclasses import dataclass
import json
import os
import re
from urllib.error import URLError
from urllib.request import Request, urlopen

from app.location_matching import PIN_PATTERN


@dataclass(frozen=True)
class Service:
    terms: tuple[str, ...]
    specialties: tuple[str, ...]


HEMODIALYSIS = ("hemodialysis", "haemodialysis", "hemo dialysis", "haemo dialysis")
PERITONEAL_DIALYSIS = ("peritoneal dialysis",)
SERVICES = {
    "dialysis": Service(("dialysis", "kidney dialysis", "透析", *HEMODIALYSIS,
                        *PERITONEAL_DIALYSIS), ("nephrology",)),
    "hemodialysis": Service((*HEMODIALYSIS, "血液透析"), ("nephrology",)),
    "peritoneal_dialysis": Service((*PERITONEAL_DIALYSIS, "腹膜透析"), ("nephrology",)),
    "cataract_surgery": Service(("cataract surgery", "cataract operation", "白内障手术"),
                                ("ophthalmology",)),
    "mri": Service(("mri", "mri scan", "mri scans", "mri scanning", "magnetic resonance imaging",
                    "磁共振"), ("radiology", "diagnosticradiology")),
}
REFERRAL_OR_UNCERTAIN = re.compile(
    r"\b(?:refer(?:s|red|ral|rals|ring)?|transfer(?:s|red|ring)?|off[- ]site|"
    r"elsewhere|unavailable|not (?:currently )?(?:available|offered|provided)|"
    r"(?:no|without) (?:on[- ]site )?(?:[a-z]+ ){0,2}(?:dialysis|ha?emodialysis|mri|cataract surgery)|"
    r"(?:does|do) not (?:offer|provide|perform)|"
    r"planned|proposed|formerly|historically|under construction|"
    r"trained in|training in|research on)\b",
    re.IGNORECASE,
)
OFFERING = re.compile(
    r"^(?:offers?|provides?|performs?|conducts?|speciali[sz]es? in|houses?)\b"
    r"|\b(?:is |are )?(?:available|offered|provided|performed|on[- ]site)\b",
    re.IGNORECASE,
)
OTHER_SITE = re.compile(
    r"\b(?:at|by) (?!this (?:hospital|facility|clinic|centre|center)\b|"
    r"our (?:hospital|facility|clinic|centre|center)\b)\S+.*"
    r"\b(?:hospital|clinic|institute|medical cent(?:er|re))\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SearchQuery:
    service_id: str
    city: str | None
    pincode: str | None


@dataclass(frozen=True)
class SearchIntent:
    city: str | None
    pincode: str | None
    specialities: tuple[str, ...]
    service: tuple[str, ...]


def parse_search_intent(payload: object) -> SearchIntent:
    """Read the search intent produced by an upstream agent."""
    if not isinstance(payload, dict) or not isinstance(payload.get("location"), dict):
        raise ValueError("Search intent must contain a location object.")

    location = payload["location"]
    city, postcode = location.get("city"), location.get("postcode")
    if any(value is not None and not isinstance(value, str) for value in (city, postcode)):
        raise ValueError("location.city and location.postcode must be strings or null.")
    city = (city or "").strip() or None
    postcode = (postcode or "").strip() or None
    if postcode and not PIN_PATTERN.fullmatch(postcode):
        raise ValueError("location.postcode must be a valid six-digit PIN.")
    if not (city or postcode):
        raise ValueError("Search intent must include a city or postcode.")

    terms = {}
    for field in ("specialities", "service"):
        values = payload.get(field)
        if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
            raise ValueError(f"{field} must be an array of strings.")
        terms[field] = tuple(value.strip() for value in values if value.strip())
    if not (terms["specialities"] or terms["service"]):
        raise ValueError("Search intent must include at least one speciality or service.")

    return SearchIntent(city, postcode, terms["specialities"], terms["service"])


def _contains(text, term):
    if not term.isascii():
        return term in text
    return re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text) is not None


def _resolve_catalog(phrase):
    normalized = phrase.casefold().replace("-", " ")
    matches = {
        service_id
        for service_id, service in SERVICES.items()
        if any(_contains(normalized, term) for term in service.terms)
    }
    if matches & {"hemodialysis", "peritoneal_dialysis"}:
        matches.discard("dialysis")
    if len(matches) != 1:
        return None
    return next(iter(matches))


def parse_query(query):
    """Handle common service-first queries locally, without an API credential."""
    parts = re.split(
        r"\s+(?:near|around|in|close to)\s+|\s*,\s*",
        query.strip(), maxsplit=1, flags=re.IGNORECASE,
    )
    service_id = _resolve_catalog(parts[0])
    address = parts[1] if len(parts) == 2 else ""
    pins = set(PIN_PATTERN.findall(query))
    if len(pins) > 1:
        raise ValueError("Please provide one search PIN.")
    city = PIN_PATTERN.sub("", address).strip(" ,?!.") or None
    return _validated_query(service_id, city, next(iter(pins), None))


def _validated_query(service_id, city, pincode):
    if service_id not in SERVICES:
        raise ValueError("Please specify one supported service: " + ", ".join(SERVICES))
    if pincode and not PIN_PATTERN.fullmatch(pincode):
        raise ValueError("Please provide a valid six-digit PIN.")
    if not (city or pincode):
        raise ValueError("Please add your city or six-digit PIN.")
    return SearchQuery(service_id, city, pincode)


def parse_query_with_agent(query):
    """Extract an allowlisted service and location through OpenAI Structured Outputs."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("Set OPENAI_API_KEY to use --agent.")
    catalog = {key: service.terms for key, service in SERVICES.items()}
    payload = {
        "model": os.environ.get("OPENAI_SERVICE_MODEL", "gpt-5-mini"),
        "store": False,
        "instructions": (
            "Extract a facility search request from the user text. "
            "Use an exact service ID from this catalog: " + json.dumps(catalog, ensure_ascii=False)
            + ". Use null if unsupported, ambiguous, or only symptoms are mentioned. "
            "Preserve specific dialysis subtypes. Extract city and state as one city string "
            "only when explicitly supplied, and copy a PIN only if it appears in the request. "
            "Use null for absent fields. Return a single search."
        ),
        "input": query,
        "text": {"format": {
            "type": "json_schema", "name": "facility_search", "strict": True,
            "schema": {
                "type": "object", "additionalProperties": False,
                "properties": {
                    "service_id": {"type": ["string", "null"], "enum": [*SERVICES, None]},
                    "city": {"type": ["string", "null"]},
                    "pincode": {"type": ["string", "null"]},
                },
                "required": ["service_id", "city", "pincode"],
            },
        }},
    }
    request = Request(
        "https://api.openai.com/v1/responses", data=json.dumps(payload).encode(),
        headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=20) as response:
            result = json.load(response)
        if result.get("status") != "completed":
            raise ValueError("The agent did not complete the extraction. Try a shorter query.")
        outputs = [
            part["text"]
            for item in result.get("output", [])
            for part in item.get("content", [])
            if part.get("type") == "output_text"
        ]
        if len(outputs) != 1:
            raise ValueError("The agent could not extract a search request.")
        parsed = json.loads(outputs[0])
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        raise ValueError("The service agent could not respond. Try again or omit --agent.") from error
    pins = set(PIN_PATTERN.findall(query))
    if len(pins) > 1:
        raise ValueError("Please provide one search PIN.")
    if parsed["pincode"] and parsed["pincode"] not in pins:
        raise ValueError("Please specify the search PIN directly.")
    return _validated_query(parsed["service_id"], parsed["city"], next(iter(pins), None))


def match_service(facilities, service_id):
    """Return one candidate per input facility row, with dataset evidence attached."""
    return _match_service(facilities, SERVICES[service_id])


def _normalize_service_term(value: str) -> str:
    return " ".join(value.casefold().replace("-", " ").split()).strip(" .")


def match_search_intent(facilities, intent: SearchIntent):
    """Match supplied labels exactly after normalization, outside the service catalog."""
    terms = tuple(filter(None, map(_normalize_service_term, intent.service)))
    specialties = tuple(value.casefold() for value in intent.specialities)
    return _match_service(facilities, Service(terms, specialties), exact_terms=True)


def _match_service(facilities, service: Service, *, exact_terms: bool = False):
    specialties = set(service.specialties)
    service_terms = set(service.terms)
    fields = ("procedure", "capability") if service_terms else ()
    for row in facilities:
        evidence = None
        for field in fields:
            for claim in json.loads(row[field] or "[]"):
                text = _normalize_service_term(claim)
                exact_match = text in service_terms
                if not exact_match and (exact_terms or not any(_contains(text, term) for term in service.terms)):
                    continue
                if REFERRAL_OR_UNCERTAIN.search(claim) or OTHER_SITE.search(claim):
                    continue
                if exact_match or any(text.startswith(term + " unit") for term in service.terms) or OFFERING.search(claim):
                    evidence = {"field": field, "text": claim}
                    break
            if evidence:
                break
        if evidence:
            yield {**row, "service_match": "listed_in_dataset", "service_evidence": evidence}
        elif any(s.casefold() in specialties for s in json.loads(row["specialties"] or "[]")):
            yield {**row, "service_match": "related_specialty_only", "service_evidence": None}
