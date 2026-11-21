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
