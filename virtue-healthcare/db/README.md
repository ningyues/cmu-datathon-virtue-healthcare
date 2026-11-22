# PostgreSQL search backend

This backend preserves the CSV pipeline and imports its processed snapshot into
PostgreSQL 16. Python implements literal, case-insensitive substring matching, not
semantic search or independent service verification. No service catalog is required.

## Scoring contract

- Authority is a persisted value in [0, 1], initialized as 1 minus the flag penalties.
- Multiple specialties are accepted. Any match awards 10 points total, never 10 per term.
- For each service, capability, equipment and procedure each award 2 points on a match.
- Each individual service scores at most 6 points. Different services are summed,
  even when they match the same field. Repeated occurrences within a field do not add points.
- Inputs are lowercased, whitespace-normalized, deduplicated and stripped of empty terms.
- `raw_score = specialty_score + sum(individual_service_scores)`.
- `max_raw_score = (10 if specialties were supplied else 0) + 6 * unique_service_count`.
- `match_score_100 = 100 * raw_score / max_raw_score`.
- `final_score = authority * match_score_100`, ranging from 0 to 100.
- Empty queries are rejected. Specialty-only and service-only queries use their own denominator.
- Results with zero raw score are omitted. Authority-zero matches remain visible with score 0.
- Rank by unrounded final score, raw score, then ID. Display scores rounded to two decimals.
- Matching remains literal, case-insensitive substring matching within individual array items.
- Percent and underscore are literal characters. Synonyms are not merged.
- Postcode matches exactly; city matches exactly after case/whitespace normalization.
  When both are supplied, both filters must match.

Authority is a writable NUMERIC(5,4) column constrained to [0, 1]. Its initial
value is computed once on import using the original seeded inputs, with
`flags_origin` set to `synthetic`. Search uses the stored Authority value.
The requested spelling `cordination` is retained for the synthetic postcode flag.

`url_domain_invalid` now stores the verified share of a facility's distinct
dataset URLs, from 0 to 1. It is NULL until all listed URLs have been checked,
and remains NULL when the facility has no usable URLs. The website preparation
batch saves the checks and the browser search API uses the ratio for scoring.
A higher ratio means more links opened. The database CLI uses the stored
Authority value.

## Start locally

Run these commands from the `virtue-healthcare` directory. Docker Compose and
Python 3.9+ are required. `.env` is for local development; do not commit credentials.
On the `xjy` layout, data is read from the repository-level `data/processed`
directory automatically. Both gzip and xz facility snapshots are supported.

```sh
cp .env.example .env
docker compose up -d db
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL='postgresql://healthcare:local-development-only@localhost:5432/healthcare'
python -m app.postgres init
python -m app.postgres load
python -m app.postgres search --postcode 560001 --specialty nephrology --service dialysis
python -m app.postgres search --specialty cardiology --service angiography --service echocardiography
```

The database uses a named Docker volume. `docker compose down` retains it;
`docker compose down -v` deletes it. Change the development password before exposing
the database beyond localhost. For an existing PostgreSQL server, set DATABASE_URL
and skip Docker. Password changes in `.env` do not rotate an existing database password.

## Legacy SQL usage

The function below is a legacy 0-to-16 scoring interface retained for compatibility.
It does not implement the new percentage scale or multi-specialty aggregation.
Use Python `search` for the current scoring contract.
The Python `search` command now uses `app/scoring.py` and the per-service score table
instead. Use the Python command for cached lookup and automatic cache population.

```sql
SELECT * FROM healthcare.search_facilities(
    p_postcode => '560001',
    p_specialty => 'nephrology',
    p_services => ARRAY['dialysis', 'hemodialysis'],
    p_limit => 20,
    p_offset => 0
);

SELECT authority, count(*) FROM healthcare.facilities GROUP BY authority;
SELECT postcode_address_cordination_unmatch, count(*)
FROM healthcare.facilities GROUP BY postcode_address_cordination_unmatch;
```

## Import and concurrency

`init` can be repeated and upgrades earlier schemas. It clears the old synthetic
URL flags when converting the column to a ratio and preserves stored Authority.
Run `load` when importing source columns or a new snapshot. Legacy
`postcode` and `pincode_lookup` objects, if present, are retained but no longer used.
`load` validates arrays, bulk copies into temporary tables and upserts in one
transaction. Importers use an advisory lock to avoid interleaved imports. Readers
see committed data; they never see partially loaded snapshots. Failed imports roll
back. Re-importing preserves existing Authority, including manual changes.
Changing a facility's imported website fields clears its stored checks and ratio.
Rows missing from a later input are retained; imports never silently delete hospitals.

All 60 original facility columns exist independently in `healthcare.facilities`.
Original case-sensitive names are preserved; use double quotes for camelCase columns.
The four matching fields use text arrays; coordinates use double precision and source
record numbers use bigint. Other source fields remain text to preserve source values.
`raw_record` is an additional audit copy, not a replacement for separate columns.
All 15 original postal columns are loaded into `healthcare.pincode_offices` (165,625
rows in the bundled snapshot), keyed by `source_record`. The tables can be joined on
`facilities."address_zipOrPostcode" = pincode_offices.pincode`. A PIN has multiple
post offices; use EXISTS for filtering to avoid multiplying hospital rows. Source NUL
bytes are removed because PostgreSQL text/JSON cannot contain them.

The postcode B-tree narrows candidates; Python matches only uncached candidates.
This version intentionally prioritizes the requested scoring contract. It does not
claim indexed text search, a web API, or measured concurrent throughput. The Python
CLI opens one connection per invocation; a future web API should use a bounded pool.
Queries are parameterized, limited to 100 results and have a 30-second timeout.

## Per-service score cache

Run `python -m app.postgres init` to install `db/service_cache.sql`. The migration
removes the old derived fit cache and its authority synchronization trigger. Hospital
and postal records, including authority, are preserved. No data reload is needed.

`healthcare.facility_service_scores` uses `(facility_id, service)` as its primary key.
It stores three match booleans and a stored service score (0, 2, 4 or 6). There is no
specialty, authority, fit score or version column. Zero matches are cached too.
Services are normalized by lowercasing and collapsing whitespace; synonyms and
translations are not inferred.

Python `search` batch-loads cache entries, computes missing hospital/service pairs,
and writes them back. Different specialties reuse the same service entries.
Specialty is always matched against the current hospital specialties, contributing
0 or 10 points. For multiple services, individual scores are summed. Each input service can
contribute up to 6 points; duplicate normalized inputs are counted only once.

Response fields:

- `service_score`: sum of per-service scores, 0 to 6 times the unique service count.
- `specialty_score`: freshly calculated specialty score, 0 or 10.
- `raw_score`: specialty score plus summed service scores.
- `max_raw_score`: query-specific maximum.
- `match_score_100`: raw score divided by that maximum, scaled to 100.
- `authority`: current value from the hospital row.
- `final_score`: `authority * match_score_100`.
- `specialty_details` and `service_details`: per-input matches, service scores and cache hits.
- `cache_hit`: all requested service entries were already cached; null for specialty-only queries.
- `cached_service_count` and `requested_service_count`: partial-hit visibility.

```sh
python -m app.postgres warm-services --service dialysis --service x-ray
python -m app.postgres search --specialty nephrology --service dialysis
```

`warm-services` fills each service separately for all hospitals, or only a supplied
`--postcode`. Ordinary searches also cache misses. Only pagination limits returned
results; it does not limit which candidate scores are evaluated.

Updating authority changes only the hospital record. The next search uses that
current authority without touching cached service scores. Specialty updates also
leave cache entries unchanged. Changing capability, equipment or procedure deletes
that hospital's cached service entries via a database trigger, so the next query
recomputes them. Re-importing unchanged arrays preserves cache entries.

Search transactions acquire shared hospital row locks before reading/writing cache
rows. Data updates cannot race with cache insertion. Concurrent fills use the unique
key and `ON CONFLICT DO NOTHING`. Authority updates may wait for an active search
transaction, but do not synchronize or modify the cache. All application writers
follow parent-before-cache locking order.

If matching rules change, clear the derived service cache during deployment. Old
combinations are no longer stored: table growth is hospitals times distinct queried
service terms. Optional retention can evict old entries without affecting source data.

```sh
TEST_DATABASE_URL="$DATABASE_URL" python -m unittest discover -s tests -v
```

## Validation

```sh
python -m unittest discover -s tests -v
psql -v ON_ERROR_STOP=1 "$DATABASE_URL" -f tests/scoring.sql
```

The Python suite validates real snapshot parsing, proportions and stable assignment.
Database integration tests verify service reuse across specialties, authority independence,
multiple-service summation, specialty caps, percentage scaling, partial hits, zero scores, invalidation and row locking.
The SQL suite verifies the actual database scoring, literal matching, duplicate caps,
blank terms and postcode filtering, using fixtures rolled back after the test.

## Write back authority

```sql
UPDATE healthcare.facilities
SET authority = 0.85, updated_at = now()
WHERE unique_id = 'facility-id';

SELECT f.unique_id, f.name, f.authority
FROM healthcare.facilities f
WHERE EXISTS (
    SELECT 1 FROM healthcare.pincode_offices p
    WHERE p.pincode = f."address_zipOrPostcode" AND p.statename = 'KARNATAKA'
);
```

```sh
python -m app.postgres set-authority --facility-id 'facility-id' --value 0.85
```

The update command rejects values outside [0, 1] and unknown facility IDs.

## Multiple specialties and JSON input

```sh
python -m app.postgres search --city Lucknow --specialty dentistry --specialty generalDentistry --service "toothache consultation" --service "dental care"
python -m app.postgres search --input-json examples/dental_query.json
```

The JSON input uses `location.postcode`, `location.city`, `specialities` (array),
and `service` (array). Location values may be null. Do not combine `--input-json`
with query flags; pagination flags remain available. Output is a JSON array of
ranked hospitals with numeric scores and per-input match details. Existing single
service cache entries remain valid; no reload or cache reset is required for this
aggregation change.
