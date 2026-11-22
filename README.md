# CareLens

CareLens is a healthcare facility search and comparison tool for India. It helps people find nearby care, understand why a facility matched their search, and check the evidence attached to a result. The project uses the Virtue Foundation facility dataset from the Databricks Apps & Agents for Good Hackathon. [Hackathon dataset](https://dais-for-good-2026.devpost.com/resources)
- **Try CareLens** · [Open the public app](https://carelens-public.onrender.com/).
- **Repository** · [cmu-datathon-virtue-healthcare](https://github.com/ningyues/cmu-datathon-virtue-healthcare)
- **Stack** · React, Vite, Leaflet, Python, PostgreSQL 16, and Volcengine Ark
- **Example search** · `Find dialysis near Hyderabad 500003`

## Video presentation

[Watch the CareLens live demo on Google Drive](https://drive.google.com/file/d/1IZL8A6J02tdDjT6skSbMARxwAA_fqeJc/view?usp=drive_link)

[Watch the CareLens presentation on Google Drive](https://drive.google.com/file/d/1YRKJs_y5BEh4WebLYI3Ig7qO5PefJuCi/view?usp=drive_link)

[Browse the presentation figures](#presentation-figures)

## Why we built it

Facility names, addresses, specialty tags, and service descriptions often come from different sources. They can be incomplete or describe different branches of the same hospital. A person looking for dialysis needs to know which facilities are nearby and what supports the claim that a specific branch offers it.

CareLens puts those details in the same workflow. A user can search in plain language, compare results by Fit Score or distance, and open a facility to read the score breakdown, website evidence, and accreditation records.

## What CareLens does

- **Search by care need and location.** Search by specialty or service using a city, district, or six-digit PIN. The default radius is 30 km. Changing the radius reuses the parsed search intent.
- **Compare facilities on a list and map.** Sort by highest Fit Score or nearest straight-line distance. Numbered map markers follow the list ranking, and the map automatically frames the search radius when results arrive.
- **Explain each score.** The detail panel shows Authority, match percentage, specialty points, and the procedure, equipment, and capability matches for each requested service.
- **Check services against the hospital website.** CareLens checks the requested services for facilities on the visible results page. When a page identifies the hospital and explicitly lists the requested service, the **Service points** section shows the source link and a short excerpt. Users can confirm current appointment availability with the facility.
- **Verify hospital website links in advance.** An offline job saves hospital-name and address evidence for dataset links in PostgreSQL. The detail panel reads those saved results and shows **Verified · Hospital match** when there is enough evidence. Authority uses the separately recorded URL reachability share.
- **Show accreditation and ratings.** The NABH check uses the official directory and certificate PDFs. A verified certificate adds a star to the result and a PDF link and preview to the detail panel. When the dataset includes a usable Practo hospital or clinic link, the card can display the institution's rating alongside its Fit Score.

## How ranking works

CareLens resolves the search location, filters facilities by distance, and scores matching records within that area. Specialty and service points come from matching the search terms against the facility dataset.

| Signal | How it contributes |
| --- | --- |
| Specialty | Any matching specialty awards 10 points total. |
| Procedure | Each distinct requested service can earn 2 points for a match. |
| Equipment | Each distinct requested service can earn 2 points for a match. |
| Capability | Each distinct requested service can earn 2 points for a match. |

```text
Possible points = 10 if specialties were requested, plus 6 per distinct requested service
Match percentage = 100 × earned points / possible points
Authority = 1 − 0.30 × address flag − 0.50 × (1 − reachable URL share)
Fit Score = Authority × match percentage
```

The address flag comes from persisted geographic checks. Fit Score displays **Pending** when the reachable URL share is unavailable. The live service check, hospital-link match, NABH status, and Practo rating appear as supporting evidence alongside the score. [Scoring and API details](app/README.md#search-api-with-postgresql-scoring)

## Architecture

```text
React + Vite → Python search API → intent parser → geographic filter → PostgreSQL scoring
                    ├─ live hospital webpage, NABH, and Practo checks
                    └─ reads saved website evidence from PostgreSQL

Raw facility and postal data → cleaning pipeline → compressed snapshots → PostgreSQL
Dataset URLs → offline reachability and hospital identity checks → PostgreSQL
```

The default intent parser uses Volcengine Ark to extract the location, specialties, requested services, and search radius. The API also accepts structured intent and includes a small local parser for common queries. PostgreSQL stores facility and postal records, per-service scoring matches, and website evidence. The frontend uses Leaflet with OpenStreetMap tiles. [API documentation](app/README.md) · [Database schema and scoring](virtue-healthcare/db/README.md) · [Frontend documentation](frontend/README.md)

## Data snapshot

The repository includes **9,989 facility records**, **165,625 India Post office records**, and **19,586 unique PINs**. The cleaning pipeline normalizes list fields, removes duplicate specialty labels within a record, screens coordinates, and records source-backed corrections and open issues. [Cleaning log](data/evidence/CLEANING_LOG.md) · [Evidence and review queue](data/evidence/)

To rebuild the snapshots from the original inputs, run the pipeline from the repository root. The output goes to `build/` for review.

```bash
python3 pipeline/run_clean.py \
  --zip inputs/Datathon.zip \
  --postal inputs/pincodes.csv \
  --out build
```

## Local development

Use **Python 3.10+**, **Node.js 22.13+**, and **Docker Compose**. The commands below use the repository root unless a command explicitly changes directories.

### 1. Start PostgreSQL and load the bundled data

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r app/requirements.txt

(
  cd virtue-healthcare
  test -f .env || cp .env.example .env
  docker compose up -d --wait db
)

export DATABASE_URL='postgresql://healthcare:local-development-only@localhost:5432/healthcare'
(
  cd virtue-healthcare
  python -m app.postgres init
  python -m app.postgres load
)
```

`init` also upgrades an existing schema. `load` imports the facility and postal records along with the bundled website scores and hospital-link evidence. After pulling a new bundle, run `init` and `load` against the database used by your API. [URL scores](data/processed/website_reachability.csv.gz) · [Hospital-link evidence](data/processed/website_facility_matches.csv.gz)

The bundled scores cover all 9,989 facility records. Hospital-link evidence covers 36,330 reachable links, including 5,109 confirmed matches. The import fills missing results for matching records and preserves completed local results. Both imports run entirely offline. [Website score import and export](virtue-healthcare/db/README.md#bundled-website-scores)

### 2. Start the API

For a local demo with the built-in service catalog, run this in the backend terminal with `DATABASE_URL` still exported.

```bash
python -m app.api --local-parser --port 8000
```

The local parser covers dialysis, hemodialysis, peritoneal dialysis, cataract surgery, and MRI. For the default Ark parser and model-assisted NABH verification, copy `agents/.env.example` to `agents/.env`, set `ARK_API_KEY` and `ARK_MODEL`, and start the API with `python -m app.api --port 8000`. Keep agent credentials on the backend. [Agent setup](agents/README.md)

### 3. Start the frontend

In a second terminal, run the following commands.

```bash
cd frontend
npm ci
npm run dev
```

Open the URL printed by Vite, usually `http://localhost:5173`, and try `Find dialysis near Hyderabad 500003`. Vite proxies `/api` requests to port 8000. For a labeled UI-only demo, set `VITE_FACILITIES_API_URL=` in `frontend/.env.local` before starting Vite.

## Smoke checks

Run the CLI demo against the bundled snapshots from the repository root.

```bash
python -m app.demo_location_search --query 'Find dialysis near Hyderabad 500003' --sort distance
```

With the API running, send a structured search that bypasses the model parser. The response contains the applied `radiusKm`, `queryLocation`, and ranked `facilities` with score breakdowns.

```bash
curl -fsS http://127.0.0.1:8000/api/search \
  -H 'Content-Type: application/json' \
  -d '{"intent":{"location":{"city":"Hyderabad","postcode":"500003"},"specialities":["nephrology"],"service":["dialysis"],"range":30}}'
```

For automated checks and a production frontend build, run the following from the repository root.

```bash
python -m unittest discover -s app
python -m unittest discover -s agents
npm --prefix frontend test
npm --prefix frontend run build
```

## Presentation figures

### Healthcare facility data pipeline

![Bronze, Silver, and Gold stages from raw exports to search-ready facility records](docs/presentation/03-data-pipeline.png)

*Page 3.* The pipeline ingests facility and postal exports, removes duplicates, and checks PINs and coordinates. It retained **9,989 facility records** and produced a lookup with **19,586 unique PINs**. The search-ready data includes reviewed facility names and service evidence.

### Data quality before and after cleaning

![Before-and-after comparisons for coordinates, PINs, region agreement, and field completeness](docs/presentation/04-data-quality.png)

*Page 4.* Valid coordinates rose from **98.77% to 99.62%**, and agreement between a facility's PIN and state rose from **92.49% to 94.19%**. The chart also tracks valid PINs and completeness across seven core fields.

### Technical architecture

![React search, Python API, Ark intent parsing, radius filtering, PostgreSQL scoring, and external evidence](docs/presentation/05-technical-architecture.png)

*Page 5.* The React app sends a query to the Python API. The Ark intent agent extracts the care need and location, the location matcher filters by radius, and the scorer reads the prepared data from PostgreSQL. NABH and Practo results appear alongside the Fit Score as separate evidence.

### Product walkthrough

![CareLens search form, nearby results and map, and a hospital's Fit Score breakdown](docs/presentation/06-product-demo.png)

*Page 6.* The screenshots show how to enter a care need and location, adjust the search radius on the results page, and open a facility card to inspect its Fit Score, straight-line distance, and matching evidence.

### Hospital Fit Score

![Authority and service matching components of the Hospital Fit Score](docs/presentation/09-hospital-fit-score.png)

*Page 9.* Fit Score multiplies Authority by the match percentage. The API uses the share of unreachable URLs for the URL deduction. The hospital-match label uses the website's name and branch address evidence. Specialty and per-service points supply the match percentage.

### Authority score distribution

![Authority score distribution for 9,970 hospitals in the presentation snapshot](docs/presentation/10-authority-score-distribution.png)

*Page 10.* In this snapshot of **9,970 hospitals**, the mean Authority Score was **0.61** and the median was **0.60**. The largest concentration was between **0.50 and just under 0.65**, where 58.6% of hospitals scored.

### External verification

![Example NABH accreditation certificate for Xenia Hospitals and a Practo institution rating](docs/presentation/11-external-verification.png)

*Page 11.* CareLens checks the NABH branch identity and certificate validity against the official directory and certificate PDF. Practo provides a rating and source link from a listed institution profile. The example's Practo branch address is pending verification.

## Repository structure

| Path | Contents |
| --- | --- |
| `frontend/` | React search page, ranked results, interactive map, and facility detail panel |
| `app/` | Search API, geographic filtering, CLI demo, offline website jobs, and API tests |
| `agents/` | Search intent extraction, NABH accreditation, website and service checks, and Practo lookups |
| `virtue-healthcare/` | Docker Compose, PostgreSQL schema, snapshot import, and scoring code |
| `pipeline/` | Data cleaning and source-backed correction rules |
| `data/processed/` | Bundled facility and postal snapshots and PIN lookup |
| `data/evidence/` | Cleaning log, reviewed claims, backfills, and outstanding data-quality issues |

## Team and acknowledgements

CareLens is a team Datathon project. Thanks to Virtue Foundation and the Databricks Apps & Agents for Good Hackathon for the facility dataset and challenge, and to the maintainers and contributors behind the geographic and public reference data. [Repository contributors](https://github.com/ningyues/cmu-datathon-virtue-healthcare/graphs/contributors)

- Facility data comes from the Virtue Foundation hackathon dataset. [Dataset description](https://dais-for-good-2026.devpost.com/resources)
- The postal reference comes from India Post through the Open Government Data Platform India. [Postal data](https://data.gov.in/resource/all-india-pincode-directory-till-last-month)
- Geographic screening used geoBoundaries. Live map data is © OpenStreetMap contributors. [geoBoundaries](https://www.geoboundaries.org/) · [OpenStreetMap attribution and terms](https://www.openstreetmap.org/copyright)

## License

Project code licensing is pending team confirmation. The source datasets, map data, and third-party evidence retain their respective terms.
