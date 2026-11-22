# Persisted geography checks

Run from the repository root. Configure `DATABASE_URL` in your shell and put
`GEOAPIFY_API_KEY` in the Git-ignored `agents/.env` file. Never commit credentials.

```sh
python -m app.geography_check --city Hyderabad --limit 10 --max-requests 20
python -m app.geography_check --city Hyderabad --limit 10 --max-requests 20 --apply
```

The first command previews decisions. It installs the database migration and caches
provider responses, but does not persist the preview's individual geography decisions.
The migration retires decisions from previous policies, retaining their original
values and evidence in `healthcare.geography_check_audit`. These rows become
`not_checked` with flag 0 until recomputed. Formula-managed authority is updated;
manual overrides are preserved.
The second command writes decisions to `healthcare.facilities`. Cached responses are
reused for 30 days. Already-checked records are skipped; use `--force` to recheck them.
Use repeated `--facility-id` options for a targeted batch. No batch runs automatically
from the web search endpoint.

## Rules

- Query only stored address lines, city, state and postcode, restricted to India.
  Hospital names are neither appended to the query nor compared with returned names.
- Use building, amenity and street address candidates with provider confidence >= 0.60.
  Rank by provider confidence, not by agreement with the values being validated.
- Equally strong candidates (confidence difference <= 0.02) with distinct locations
  (over 250 metres apart) or postcodes are ambiguous: flag 0, status unknown.
- A returned postcode differing from the stored postcode after trimming whitespace
  is a confirmed conflict: flag 1. Missing postcode alone is not a conflict.
- Haversine distance over 1 km between the stored and returned coordinates is a
  conflict: flag 1. Configure this tolerance with `--distance-limit-km`.
- City centroids and other coarse results cannot establish address distance conflicts.
- No results, missing evidence, ambiguity and unchecked records have flag 0.
  This is the business default of valid, not a claim of verified accuracy.
- Invalid source coordinates are a local conflict. Swapped coordinates are flagged
  without changing the source data.
- Reverse queries are not issued. Full address-query responses and decision reasons
  are retained in evidence and the audit. This checks geographic consistency only,
  not whether a named hospital actually occupies the address.
- Transient network/HTTP errors retry up to five attempts with exponential backoff.
  Failed records remain unchecked; three consecutive exhausted records stop the batch.
  Authentication failures stop immediately; HTTP 429 stops after bounded retries.
  Error logs include safe error codes, never credentials.
- Previous decisions are reset by the migration. No batch automatically restarts.

## SQL writeback

`virtue-healthcare/db/geography_checks.sql` adds fields to the original facilities
 table, including status, reasons, provider, check time, reverse-geocoded address,
forward-address distance, precision and evidence. The original coordinate fields
are never rewritten. `postcode_address_cordination_unmatch` is NOT NULL with a default of 0:

| Status | Flag | Location deduction |
| --- | --- | --- |
| matched | 0 | 0 |
| mismatch | 1 | 0.30 |
| unknown / not_checked | 0 | 0 |

Only confirmed geographic conflicts have flag 1 (invalid). All other results have flag 0 (valid).
Diagnostic status and reasons remain available separately.

Geography writeback adjusts stored authority by `0.3 * (old_flag - new_flag)`,
clamped to [0, 1], preserving other score components. Manual overrides are unchanged.
The browser scorer separately uses `1 - 0.3 * flag - 0.5 * (1 - reachable_url_share)`.
The upstream column `url_domain_invalid` now holds that share, not an invalid flag.
A missing share leaves browser scores pending. This job does not check domain ownership.
No service cache updates are needed: query scoring reads the latest hospital authority.

The migration identifies pre-existing manual overrides by comparing authority to
its previous flag formula. Values that differ are marked `manual`; equal values are
classified as `formula`, because historical intent cannot be inferred. Explicitly
mark any other overrides before running checks:

```sql
UPDATE healthcare.facilities SET authority_calculation_mode='manual'
WHERE unique_id='facility-id';
```

`python -m app.postgres set-authority` in the backend directory also marks overrides
as manual. Geographic results never replace manually managed authority.

Every write locks the current hospital row and compares its source fields with the
checked snapshot. Changed input is rejected as `stale_input`. Source address or
coordinate updates invalidate the previous result through a trigger. Formula-managed
location deductions are removed until a new check identifies a conflict; manual authority is retained.
Every applied check has an audit record with before/after flags and scores.

## Inspect results

```sql
SELECT unique_id, name, postcode_address_cordination_unmatch,
       geography_check_status, geography_check_reasons,
       address_coordinate_distance_km, authority, authority_calculation_mode
FROM healthcare.facilities
WHERE geography_checked_at IS NOT NULL
ORDER BY geography_checked_at DESC;
```

## Tests and provider documentation

```sh
TEST_DATABASE_URL="$DATABASE_URL" python -m unittest app.test_geography_check -v
```

Tests cover coordinate swaps, distances, uncertain/ambiguous results, atomic writeback,
manual authority, source invalidation and stale-input rejection. Most tests use local
provider fixtures and incur no API usage.

Geoapify documentation: https://apidocs.geoapify.com/docs/geocoding/
Reverse geocoding: https://apidocs.geoapify.com/docs/geocoding/reverse-geocoding/
Quotas: https://www.geoapify.com/pricing/
The free plan currently allows 3,000 credits/day; forward and reverse requests normally
consume one credit each. Other account usage shares the quota. The checker is single
process, throttled to under four requests/second, and defaults to at most 100 requests.
Displayed provider-derived results include Geoapify and OpenStreetMap attribution.
