# CareLens frontend

React JSX and plain CSS implementation of the supplied **CareLens / Aurora Glass** Figma page.

## Run locally

Use Node.js 22.12+ (or Node.js 24).

Start the Python API from the repository root.

```bash
python3 -m app.api
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
| `src/components/FacilityMap.jsx` | Original map artwork and marker interactions |
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
    "service": ["toothache consultation", "dental care"]
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

The API uses the local service-catalog parser for free-text queries. To use the existing OpenAI parser, start it with `python3 -m app.api --agent` and configure `OPENAI_API_KEY` in the Python process. The API sends free-text queries to OpenAI in this mode. Live map points use the dataset coordinates and open the same detail drawer as the facility cards. The point plot uses a coordinate grid without a street basemap.

## Design and validation notes

Source: https://www.figma.com/design/NsplDJSkDvmdNcEB5Kw4mU/databricks?node-id=32-238

Primary desktop frames: landing `33:689`, results `33:742`, and detail instances `33:974`, `36:525`, `36:564`. The 1440 × 900 desktop layout is the target. CSS provides narrower-window fallbacks.

The design shows four cards with a count of three and omits the fourth card from some alternate states. This implementation consistently uses all four records in both sorting modes and calculates the count. The duplicate sort-control layer is rendered as one functional select. The supplied names, scores, addresses, and distances are retained. Results are labelled illustrative so the prototype does not present sample values as verified healthcare data.

Production build and automated data/component tests were run. Tests cover ranking, missing values, malformed API records, form validation, sorting, card/marker selection, drawer dismissal, and returning to search. Browser rendering could not be visually verified because this execution environment blocked the local browser launch; check the layout in your browser before treating it as a pixel-perfect handoff.
