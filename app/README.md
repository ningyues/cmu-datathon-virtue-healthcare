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
  "service": ["toothache consultation", "dental care"]
}
```

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
→ {location, specialities, service}
→ parse_search_intent → LocationMatcher (30 km)
→ PostgreSQL scoring → facility cards and map
```

The agent's entire expanded `specialities` array and all requested `service` values
are passed to the existing scorer. No intermediate JSON file or manual copy is needed.
Each free-text submission makes one model request. Structured `intent` requests
still bypass the model. This integrates the user intention agent; NABH `verify.py`
is a separate verification command and is not called for every search result.

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
service points, the query maximum and per-input matches. `trustScore` stays null:
synthetic authority is not a measured hospital trust rating. `text_match` denotes
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
