# App data entry point

Place the application code in this directory. The existing data can be loaded without running the cleaning pipeline.

From the repository root, this Python example reads the facility snapshot:

```python
import csv
import lzma

with lzma.open("data/processed/facilities_clean.csv.xz", "rt",
               encoding="utf-8-sig", newline="") as file:
    facilities = list(csv.DictReader(line.replace("\0", "") for line in file))
```

## Run the search demo

From the repository root, run:

```bash
python3 -m app.demo_location_search --query "Find dialysis near Hyderabad 500003"
```

The local parser recognizes common service-first queries. The catalog covers dialysis, hemodialysis, peritoneal dialysis, cataract surgery, and MRI. For more flexible phrasing, set `OPENAI_API_KEY` in your shell and add `--agent`. That option sends the query text to the OpenAI API and extracts a catalog service ID, city, and PIN.

The demo can read the user intent JSON produced by an upstream agent and use it to find and rank facilities.

```bash
python3 -m app.demo_location_search --intent search-intent.json
```

```json
{
  "location": {"postcode": null, "city": "Lucknow"},
  "specialities": ["dentistry", "General Dentistry"],
  "service": ["toothache consultation", "dental care"],
  "range": 30
}
```

`range` is the search radius in kilometers, defaults to 30 when omitted, and accepts
finite positive numbers including decimals. The API and `--intent` demo both pass
this value to geographic filtering before ranking. For example, `"range": 5`
limits results to 5 km; invalid values are rejected. API responses report the
applied radius in `radiusKm`, which the frontend uses in its summary and map.
The API also returns the normalized `intent` (`location`, `specialities`, `service`,
`range`). The results-page radius slider resubmits this intent with the selected
`range`; it does not parse the original query again or make another model call.

With a null postcode, the demo uses the city as the approximate origin. It matches `specialities` against dataset specialty labels and `service` against exact normalized claim text. Use `--intent -` to read JSON from stdin.

The matcher reads `procedure` and `capability` for claims about the requested service. Results include the source field and original claim text when present. Facilities matched through `specialties` alone are labeled as related specialty matches.

Results show Fit Score and straight-line distance. The default orders supplied `fit_score` values from highest to lowest, using distance to break ties. Missing scores display as `Pending`. When every score is pending, service searches put dataset claims first and sort by distance within each group, and specialty searches sort by distance. Use `--sort evidence` to select the service evidence ordering or `--sort distance` to order results nearest first.

To run the specialty-only baseline:

```bash
python3 -m app.demo_location_search --specialty nephrology --city Hyderabad --pincode 500003
```

| Field | How to use it |
| --- | --- |
| `unique_id` | Primary key for a facility record and join key to evidence. Distinct records may still describe the same facility. |
| `name_standardized` and `name` | Display name and original source name. |
| `address_zipOrPostcode` | PIN stored as text. Join it to the unique `pincode` column in `data/processed/pincode_lookup.csv`. |
| `latitude`, `longitude`, `geography_status` | Coordinates and screening status. Keep null coordinates out of distance calculations and display unresolved geographic conflicts. |
| `officialWebsite` and `source_urls` | Website candidate and a JSON list of source pages. A listed URL alone does not verify branch ownership. |
| `data/evidence/verified_service_claims.csv` | Individual source-supported service claims, joined by `unique_id`. Current availability is a separate fact. |

## Search API with PostgreSQL scoring

The API resolves the query location, selects all geographically eligible hospitals,
then passes only those IDs to the Python scorer. It does not discard equipment-only
matches through the older service prefilter. PostgreSQL supplies the persisted
hospital authority and per-service cache. All candidates are scored before ordering
by Fit Score descending, then distance ascending. There is no early top-20 truncation.

### Run the complete query workflow

The default flow is now:

```text
Frontend query box → POST /api/search {query}
→ agents.intent_agent.parse_intent (Ark)
→ {location, specialities, service, range}
→ parse_search_intent → LocationMatcher (range km, default 30)
→ PostgreSQL scoring → facility cards and map
```

The agent's entire expanded `specialities` array and all requested `service` values
are passed to the existing scorer. No intermediate JSON file or manual copy is needed.
Each free-text search makes one request to the intention model. Structured
`intent` requests bypass that model. The frontend starts separate NABH checks
after a live search response arrives.

Run commands from the **repository root**, using Python 3.10+:

```sh
# Reuse the environment created for the agents.
source agents/.venv/bin/activate
python -m pip install -r app/requirements.txt
# First-time setup only; edit agents/.env with your actual ARK_API_KEY and ARK_MODEL.
cp -n agents/.env.example agents/.env
```

Initialize and load PostgreSQL once using [the database instructions](../virtue-healthcare/db/README.md).
Then, in the same terminal, start the API with your database connection:

```sh
export DATABASE_URL='postgresql://healthcare:local-development-only@localhost:5432/healthcare'
python -m app.api --port 8000
```

`python -m app.api` defaults to the project's Ark intention agent. It reads
`agents/.env` regardless of the working directory; file values override shell
variables. To select another file, use `--env-file /path/to/custom.env`.
`DATABASE_URL` must be exported before starting the API; the agent config is read
when parsing a query. `--intent-agent` remains a compatible explicit alias.
Use `--local-parser` for the offline, small service catalog, or `--agent` for the
older OpenAI parser with `OPENAI_API_KEY`.

Start the UI in a **second terminal**, from the repository root:

```sh
cd frontend
npm ci
npm run dev
```

Open the URL printed by Vite. Enter, for example,
`Which hospital near Lucknow can handle an emergency C-section?`.
Vite proxies `/api/search` to port 8000. Remove any `VITE_FACILITIES_API_URL=` setting
in `frontend/.env.local` to use the default live API instead of sample records.
The Ark key stays in the Python process; do not put it in frontend configuration.

If location or the main medical need is missing or ambiguous, the API returns
HTTP 422 with an `error` object containing `code`, `message`, and
`clarification_question`. The UI returns to the editable query box, preserves the
input and shows the question. Refine the full request and send it again; this is
one-query-at-a-time search rather than a conversation with stored chat history.
Configuration/catalog failures return 503, model failures return 502; neither is
presented as an empty search result.

Structured intent requests bypass the parser:

```sh
curl -X POST http://127.0.0.1:8000/api/search -H 'Content-Type: application/json' \
  -d '{"intent":{"location":{"city":"Lucknow","postcode":null},"specialities":["dentistry"],"service":["dental care"]}}'
```

The backend requires an initialized and populated scoring database; follow
`virtue-healthcare/db/README.md` once before starting it. Missing database records
or connection failures return HTTP 503, not fabricated or pending scores. There
are at most eight concurrent scoring database connections per API process, with
a five-second admission/connect timeout and a thirty-second SQL statement timeout.

Each result contains `fitScore` (0–100), `distanceKm`, `scoreBreakdown`, location,
and existing evidence fields. The breakdown contains authority, specialty points,
service points, the query maximum, per-input matches, and `urlDomainVerifiedRatio`.
In the API, Authority is `1 - 0.3 * address_flag - 0.5 * (1 - verified_url_ratio)`.
Authority and Fit Score are `null` until website verification is complete.
`text_match` denotes
scoring-only text matches and is separate from an explicit dataset claim.

```sh
TEST_DATABASE_URL="$DATABASE_URL" python -m unittest app.test_api_scoring -v
```

## Workflow regression checks

Run from the repository root:

```sh
agents/.venv/bin/python -m unittest app.test_intent_workflow app.test_api_scoring -v
agents/.venv/bin/python -m unittest discover -s agents -v
cd frontend
npm test
npm run build
```

The HTTP workflow tests use the real intent expansion and location matcher, with
model and database scoring substituted for deterministic offline checks. Set
`TEST_DATABASE_URL` to a populated test database to also run the actual database
integration test. A live Ark request requires valid credentials and model access.

## NABH verification from facility details

After a live search returns facilities, the frontend calls
`POST /api/nabh/verify` for each facility with
`{"facilityId":"<unique_id>"}`. The server looks up that record in the loaded
snapshot and passes its display name and full street/city/state/PIN address to
`agents.verify.verify_facility`. Client-supplied names and addresses are ignored.

Both agents use `agents/.env`, or the API's `--env-file` override. Configure
`ARK_API_KEY` and `ARK_MODEL` there and restart the API and Vite after this update.
NABH verification queries the official directory and PDFs and may make a paid Ark
model call. The frontend checks up to two facilities concurrently, including
facilities on later results pages. Leaving search results cancels pending
browser requests. Work already running on the server may finish.

An overall `verified` result with an approved certificate URL displays
**Verified** and PDF links in facility details and adds a star beside the
facility name in search results. Missing, expired, ambiguous, or insufficient
proof displays **Unable to verify** with a reason. Configuration, source, and
model failures display the same status with an availability explanation.
Returned fields are `status` (`verified`, `unverified`, `unavailable`),
`message`, `reason`, and `certificateUrls`. Illustrative facilities skip verification.

Run offline endpoint tests from the repository root:

```sh
agents/.venv/bin/python -m unittest app.test_nabh_verification -v
```

## Facility website verification

From the repository root, prepare website scores after importing the snapshot.

```bash
python -m app.website_verification
```

Use `--city Hyderabad`, `--facility-id '<unique_id>'`, or `--limit 20` to prepare a
subset. The batch reuses saved results and checks missing public URLs. Each
finished facility is saved independently, so another run continues from the
remaining facilities. Distinct URLs are fetched once per batch, and requests
to the same hostname are sequential.

Search responses include `websiteUrls`, saved checks in
`websiteVerificationResults`, and a `urlDomainVerifiedRatio` from 0 to 1.
The ratio is `null` when checks are incomplete or there are no usable links.
Facility details and the website endpoint read saved results. The address flag
in the Authority formula uses simulated data. Run the database `init` command
to migrate an older database before deploying this API.

## Practo rating during website verification

Search results include `hasPractoLink`, derived only from hospital/clinic Practo
URLs in the snapshot record's `websites` and `source_urls`. Cards with a usable
link start `/api/practo/rating` automatically when search results load, with two
requests at a time. Cards without a link immediately show **Rating unavailable**
and do not issue a Practo request. Opening details does not start another lookup.

The endpoint resolves the snapshot-bound `facilityId` and calls `PractoAgent`
from `agents/practo.py`. It reads only the stored links, preferring institution
JSON-LD and falling back to the profile heading. Institution names are checked
because some records contain unrelated links; branch/address/PIN verification
is deferred. Doctor scores are never substituted for hospital ratings.

Practo lookup no longer uses Ark, web search, guessed URLs or a separate profile
map. The `--practo-profiles` option has been removed. `--env-file` still configures
other agents, but Practo itself needs no model credentials or search activation.

```sh
agents/.venv/bin/python -m app.api --port 8000
```

Scores appear below Fit Score in hospital list entries; Practo ratings are not
displayed in the detail drawer. Missing links, blocked access or an unreadable/missing
score all display **Rating unavailable**. The API retains the reason, source link
and optional rating/patient-story counts. Successful reads use
`sourceType="live_page"`, and `checkedAt` records the lookup time.

Available ratings are cached for six hours, other outcomes for five minutes, with
at most 256 cached facilities. Concurrent requests for one facility share a single
lookup and at most two different facilities are fetched at once. Restart the
backend after updating code to clear earlier cached results. No database migration
is required. Practo remains independent of Fit Score, website checks and NABH.

```sh
agents/.venv/bin/python -m unittest agents.test_practo app.test_practo_rating -v
```
