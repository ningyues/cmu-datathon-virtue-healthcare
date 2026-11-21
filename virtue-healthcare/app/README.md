# App data entry point

The PostgreSQL command-line backend is in `postgres.py`. Run it from the project
directory with `python -m app.postgres init`, `load`, or `search`. See
[database documentation](../db/README.md) for setup and scoring details.
The existing data can be loaded without running the cleaning pipeline.

From the repository root, this Python example reads the facility snapshot:

```python
import csv
import gzip

with gzip.open("data/processed/facilities_clean.csv.gz", "rt",
               encoding="utf-8-sig", newline="") as file:
    facilities = list(csv.DictReader(file))
```

| Field | How to use it |
| --- | --- |
| `unique_id` | Primary key for a facility record and join key to evidence. Distinct records may still describe the same facility. |
| `name_standardized` and `name` | Display name and original source name. |
| `address_zipOrPostcode` | PIN stored as text. Join it to the unique `pincode` column in `data/processed/pincode_lookup.csv`. |
| `latitude`, `longitude`, `geography_status` | Coordinates and screening status. Keep null coordinates out of distance calculations and display unresolved geographic conflicts. |
| `officialWebsite` and `source_urls` | Website candidate and a JSON list of source pages. A listed URL alone does not verify branch ownership. |
| `data/evidence/verified_service_claims.csv` | Individual source-supported service claims, joined by `unique_id`. Current availability is a separate fact. |
