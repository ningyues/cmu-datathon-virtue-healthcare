# CareLens frontend

React JSX and plain CSS implementation of the supplied **CareLens / Aurora Glass** Figma page.

## Run locally

Use Node.js 22.13+ (or Node.js 24).

Configure `agents/.env` and initialize the PostgreSQL database following [the app setup](../app/README.md#run-the-complete-query-workflow). Start the Python API from the repository root.

```bash
source agents/.venv/bin/activate
python -m pip install -r app/requirements.txt
export DATABASE_URL='postgresql://healthcare:local-development-only@localhost:5432/healthcare'
python -m app.api
```

In a second terminal, start Vite.

```bash
cd frontend
npm ci
npm run dev
```

Open the local URL printed by Vite and search for `Find dialysis near Hyderabad 500003`.

Validate and build the frontend with these commands.

```bash
npm test
npm run build
npm run preview
```

The production output is in `dist/`. Serve it with an HTTP server; do not double-click `index.html` as a local file.

## Included behavior

- Landing page with the original gradient, Inter typography, exported orbital artwork, and 8-second floating animation. Reduced-motion preferences disable animation.
- Editable service/location query; submit with Send or Enter (Shift+Enter inserts a new line).
- Default Fit Score ranking for live results, with evidence order while scores are pending and a nearest-distance option.
- Four sample hospital cards transcribed from Figma; the result count is calculated dynamically.
- Original exported illustrative map with three clickable markers. Figma supplies no marker for the fourth facility, so no coordinate was invented.
- Facility details with supplied scores, locations, and category placeholders. Close with the × button, Escape, or the dimmed map; keyboard focus is contained in the dialog and restored on close.
- View details expands a truthful explanation of the missing supporting evidence; no scoring methodology or clinical claims have been invented.
- Click the CareLens logo to return to the search page with the query preserved.
- Live search through the local Python API, with loading, empty, error, and missing-value states.

## Edit these files

| File | Purpose |
| --- | --- |
| `src/App.jsx` | Search state and page switching |
| `src/styles.css` | All styling, design tokens, responsive rules, and animation |
| `src/components/LandingPage.jsx` | Landing screen and search form |
| `src/components/ResultsPage.jsx` | Results layout and sort dropdown |
| `src/components/FacilityCard.jsx` | Reusable hospital card |
| `src/components/FacilityMap.jsx` | India street map, illustrative demo map, and marker interactions |
| `src/components/DetailDrawer.jsx` | Trust score and facility details |
| `src/components/Navigation.jsx` | Shared header |
| `src/data/facilities.js` | Figma sample records and sorting helpers |
| `src/services/search.js` | API adapter and response validation |
| `public/assets/` | Original Figma PNG/SVG exports |

No Tailwind is required. Font files are bundled locally through `@fontsource/inter`. Figma asset URLs are not used at runtime.

## Search API

The frontend sends requests to `/api/search`. Vite forwards them to `127.0.0.1:8000` during development and preview. A deployment can serve the API at the same path or set `VITE_FACILITIES_API_URL` to another compatible endpoint. Set `VITE_FACILITIES_API_URL=` explicitly in `.env.local` to use the labelled Figma sample records.

The frontend sends this request.

```http
POST /api/search
Content-Type: application/json
```

```json
{ "query": "Find dialysis near Hyderabad 500003" }
```

An upstream agent can send a parsed intent to the same endpoint.

```json
{
  "intent": {
    "location": {"postcode": null, "city": "Lucknow"},
    "specialities": ["dentistry", "General Dentistry"],
    "service": ["toothache consultation", "dental care"],
    "range": 30
  }
}
```

The API responds with a `facilities` array. This example shows the response fields.

```json
{
  "facilities": [
    {
      "id": "ganga",
      "name": "Ganga Community Hospital",
      "type": "Charitable hospital",
      "area": "Gandhi Maidan, Patna",
      "postalCode": "800001",
      "distanceKm": 3.2,
      "trustScore": null,
      "serviceEvidence": null
    }
  ]
}
```

The live endpoint uses these backend fields.

| Backend field | API field and frontend use |
| --- | --- |
| `unique_id`, `name_standardized`, `name` | `id` and `name` identify cards and map points. |
| `facilityTypeId`, `operatorTypeId` | `type` and `operatorType` display the facility category and how it is operated. |
| `address_line1`–`address_line3`, `address_city`, `address_stateOrRegion`, `address_zipOrPostcode` | `address`, `area`, and `postalCode` populate the card and detail drawer. |
| `officialWebsite` | `website` is displayed as a dataset link when it resolves to an HTTP(S) URL. |
| `latitude`, `longitude`, `QueryLocation`, `radius_km` | Facility coordinates, `queryLocation`, and `radiusKm` drive the location plot and results summary. |
| `distance_km`, `fit_score` | `distanceKm` and `fitScore` support nearest-distance and Fit Score sorting. |
| `service_match`, `service_evidence` | `serviceMatch` labels each card, and `serviceEvidence` supplies the original claim in the drawer. |

`fitScore` displays as `Pending` when the dataset has no score. `trustScore` is a separate optional 0–100 value. When Fit Scores are pending, the frontend keeps the API's order, which prioritizes dataset service claims and uses straight-line distance within each group. Service availability remains unverified.

The API defaults to the project's Ark intention agent in `agents/intent_agent.py`, loading `agents/.env`. Its output supplies the location, expanded specialty labels and services to the facility query and PostgreSQL scorer. Missing location or ambiguous requests return a clarification question in the query form, with the original input preserved. Edit the full request and submit again. Use `--local-parser` to opt into the offline service-catalog parser. To use the existing OpenAI parser, start it with `python3 -m app.api --agent` and configure `OPENAI_API_KEY` in the Python process. The API sends free-text queries to OpenAI in this mode. Live map points use the dataset coordinates and open the same detail drawer as the facility cards. The interactive Leaflet map uses OpenStreetMap street tiles, starts on India, and zooms to the backend search origin and facility coordinates. Gold marks the origin; numbered markers match the sorted cards and open their details. Internet access is required for map tiles.

## Design and validation notes

Source: https://www.figma.com/design/NsplDJSkDvmdNcEB5Kw4mU/databricks?node-id=32-238

Primary desktop frames: landing `33:689`, results `33:742`, and detail instances `33:974`, `36:525`, `36:564`. The 1440 × 900 desktop layout is the target. CSS provides narrower-window fallbacks.

The design shows four cards with a count of three and omits the fourth card from some alternate states. This implementation consistently uses all four records in both sorting modes and calculates the count. The duplicate sort-control layer is rendered as one functional select. The supplied names, scores, addresses, and distances are retained. Results are labelled illustrative so the prototype does not present sample values as verified healthcare data.

Production build and automated data/component tests were run. Tests cover ranking, missing values, malformed API records, form validation, sorting, card/marker selection, drawer dismissal, and returning to search. Browser rendering could not be visually verified because this execution environment blocked the local browser launch; check the layout in your browser before treating it as a pixel-perfect handoff.

## Integrated scoring

Start the repository-root API with `DATABASE_URL` configured (see `app/README.md`),
then run `npm ci` and `npm run dev` here. Vite proxies `/api/search` to port 8000.
`python -m app.api` uses the project's expanded specialty intention agent by default.
`--intent-agent` remains an explicit alias; `--local-parser` selects the small offline catalog.

Live results default to highest Fit Score, with nearest distance breaking ties.
Scores display on a 0–100 scale. The map uses the same ordering as the list, and
facility details show authority, specialty points and each service's contribution.
Missing services and API failures
never fall back to illustrative hospital records. `searchFacilities(intent)` can
also send a structured intent object instead of free text.

## NABH certificate verification

When live search results arrive, the frontend starts checking every returned
facility against official NABH records and certificate PDFs. The results page
shows progress across all pages. As each check succeeds, a star appears before
the facility's rank. Its detail panel shows the first page of each certificate
alongside the **View certificate PDF** link. The link also works when preview
rendering is unavailable.
Other outcomes show **Unable to verify** with an explanation. Sample facilities
skip verification.

Vite proxies both search and verification under `/api` to port 8000. For another
backend origin, set `VITE_NABH_API_URL` to its `/api/nabh/verify` endpoint in addition
to the search URL. Keep Ark credentials in `agents/.env` on the backend. See
[backend verification setup](../app/README.md#nabh-verification-from-facility-details).

## Adjust the search radius

The intent agent extracts an optional distance radius from the query (for example,
`Find dialysis within 5 km of Lucknow`). Its `range` output defaults to 30 km.
The API uses that radius to filter candidates and returns it as `radiusKm` for
the result summary and map. Structured intent requests may also supply `range`.

Live results include a **Search radius** slider initialized from the agent's
`range` (30 km by default). Drag to preview a value, then release to apply it;
keyboard adjustment and leaving the control also commit changes. The usual span
is 1–200 km and expands to accommodate an initial radius outside that span.
The current result summary continues to show the applied radius until the new
request completes.

The API returns the normalized `intent` with each search response. Radius changes
submit that same location, specialties and services with an updated `range`,
bypassing another model call. Results, counts and map markers refresh together,
and pagination resets to the first page. New requests cancel previous browser
requests. If a search fails, **Try again** retries the selected radius. Sample
results and older API responses without `intent` do not show the slider.

## Website verification

The **Website verification** section lists links from `officialWebsite` and
`websites` in the facility snapshot. The frontend starts checking all of those
links when the drawer opens.
**Verified** means the link opened successfully. **Unable to verify** shows why
the check could not complete. The Authority section shows the verified share
of usable, distinct dataset links once all links have been checked.

Vite proxies `/api/website/verify` to the Python API. Set
`VITE_WEBSITE_VERIFICATION_API_URL` when the frontend uses a separate API origin.
