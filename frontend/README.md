# CareLens frontend

React JSX and plain CSS implementation of the supplied **CareLens / Aurora Glass** Figma page.

## Run locally

Use Node.js 22.12+ (or Node.js 24).

```bash
cd carelens-frontend
npm ci
npm run dev
```

Open the local URL printed by Vite. To validate and build:

```bash
npm test
npm run build
npm run preview
```

The production output is in `dist/`. Serve it with an HTTP server; do not double-click `index.html` as a local file.

## Included behavior

- Landing page with the original gradient, Inter typography, exported orbital artwork, and 8-second floating animation. Reduced-motion preferences disable animation.
- Editable service/location query; submit with Send or Enter (Shift+Enter inserts a new line).
- Default trust ranking and working nearest-distance sorting.
- Four sample hospital cards transcribed from Figma; the result count is calculated dynamically.
- Original exported illustrative map with three clickable markers. Figma supplies no marker for the fourth facility, so no coordinate was invented.
- Facility details with supplied scores, locations, and category placeholders. Close with the × button, Escape, or the dimmed map; keyboard focus is contained in the dialog and restored on close.
- View details expands a truthful explanation of the missing supporting evidence; no scoring methodology or clinical claims have been invented.
- Click the CareLens logo to return to the search page with the query preserved.
- Loading, empty, error, and missing-value states for a future backend.

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

## Connect your agent/backend

The default is a frontend demonstration: **every valid query returns the same four illustrative records**. It does not perform NLP, search a database, verify trust scores, resolve a postcode, or calculate distance. The current map is the design's illustration, not a live geographical map.

1. Copy `.env.example` to `.env.local`.
2. Set `VITE_FACILITIES_API_URL` to your backend search endpoint.
3. Restart Vite (or rebuild for production).

The adapter sends:

```http
POST <VITE_FACILITIES_API_URL>
Content-Type: application/json
```

```json
{ "query": "I need to find a nursing service in 800001" }
```

Expected response shape (this is an illustrative record from the design):

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
      "trustScore": 92,
      "featured": true
    }
  ]
}
```

`id` must be unique and nonempty; `name` must be nonempty. `trustScore` can be a number from 0 to 100 or `null`; `distanceKm` can be a nonnegative number or `null`. Missing values appear as unavailable and sort last. An empty array shows the empty state. Invalid records or failed requests show an error with retry.

The backend should handle query interpretation, postcode/geocoding, matching, evidence and score computation. Backend-supplied results intentionally do not appear on the illustrative map. Replace `FacilityMap.jsx` with a geographical map once real coordinates and a map provider are available. Add the appropriate authentication and CORS handling in the API adapter for your backend. Never put private API keys in Vite environment variables: `VITE_` values are exposed to the browser.

## Design and validation notes

Source: https://www.figma.com/design/NsplDJSkDvmdNcEB5Kw4mU/databricks?node-id=32-238

Primary desktop frames: landing `33:689`, results `33:742`, and detail instances `33:974`, `36:525`, `36:564`. The 1440 × 900 desktop layout is the target. CSS provides narrower-window fallbacks.

The design shows four cards with a count of three and omits the fourth card from some alternate states. This implementation consistently uses all four records in both sorting modes and calculates the count. The duplicate sort-control layer is rendered as one functional select. The supplied names, scores, addresses, and distances are retained. Results are labelled illustrative so the prototype does not present sample values as verified healthcare data.

Production build and automated data/component tests were run. Tests cover ranking, missing values, malformed API records, form validation, sorting, card/marker selection, drawer dismissal, and returning to search. Browser rendering could not be visually verified because this execution environment blocked the local browser launch; check the layout in your browser before treating it as a pixel-perfect handoff.
