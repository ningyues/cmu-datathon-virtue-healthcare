"""Move completed website checks between local databases."""

import gzip
from pathlib import Path
from tempfile import NamedTemporaryFile


WEBSITE_CHECKS_FILENAME = 'website_reachability.csv.gz'
WEBSITE_MATCHES_FILENAME = 'website_facility_matches.csv.gz'
WEBSITE_INPUT_HASH = '''encode(sha256(convert_to(
    jsonb_build_array(f."officialWebsite", f."websites")::text, 'UTF8')), 'hex')'''
FACILITY_MATCH_INPUT_HASH = '''encode(sha256(convert_to(jsonb_build_array(
    f.name, f.name_standardized, f.address_line1, f.address_line2, f.address_line3,
    f.address_city, f."address_zipOrPostcode", f."officialWebsite", f."websites")::text, 'UTF8')), 'hex')'''
REACHABLE = "(result = 'true'::jsonb OR COALESCE(result->>'status' = 'verified', false))"


def export_csv(conn, path, query):
    output = NamedTemporaryFile(dir=path.parent, delete=False)
    temporary = Path(output.name)
    try:
        with output, gzip.GzipFile(filename='', fileobj=output, mode='wb', mtime=0) as compressed:
            with conn.cursor().copy(f'COPY ({query}) TO STDOUT WITH (FORMAT csv, HEADER true)') as copy:
                for block in copy:
                    compressed.write(block)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def export_website_checks(conn, path):
    """Export scores and outcomes for listed URLs without redirect destinations."""
    export_csv(conn, path, f'''
        SELECT f.unique_id, {WEBSITE_INPUT_HASH} AS website_inputs_sha256,
               f.url_domain_invalid AS reachable_ratio, checks.reachable_by_url
        FROM healthcare.facilities AS f
        CROSS JOIN LATERAL (
            SELECT jsonb_object_agg(url, {REACHABLE}) AS reachable_by_url
            FROM jsonb_each(f.website_verification_results) AS check_result(url, result)
        ) AS checks
        WHERE f.url_domain_invalid IS NOT NULL AND checks.reachable_by_url IS NOT NULL
        ORDER BY f.unique_id
    ''')


def load_csv(conn, path, copy_command):
    with gzip.open(path, 'rb') as source, conn.cursor().copy(copy_command) as copy:
        while block := source.read(1024 * 1024):
            copy.write(block)


def load_website_checks(conn, path):
    """Fill missing scores for facilities with the same website inputs."""
    conn.execute('''CREATE TEMP TABLE incoming_website_checks (
        unique_id text PRIMARY KEY,
        website_inputs_sha256 text NOT NULL,
        reachable_ratio numeric NOT NULL CHECK (reachable_ratio BETWEEN 0 AND 1),
        reachable_by_url jsonb NOT NULL CHECK (
            jsonb_typeof(reachable_by_url) = 'object' AND reachable_by_url <> '{}'::jsonb)
    ) ON COMMIT DROP''')
    load_csv(conn, path, 'COPY incoming_website_checks FROM STDIN WITH (FORMAT csv, HEADER MATCH)')
    # A complete local result stays in place. Keep any local outcomes from an unfinished check.
    return conn.execute(f'''
        UPDATE healthcare.facilities AS f
           SET website_verification_results = s.reachable_by_url || f.website_verification_results,
               url_domain_invalid = CASE WHEN f.website_verification_results = '{{}}'::jsonb
                   THEN s.reachable_ratio
                   ELSE (SELECT count(*) FILTER (WHERE {REACHABLE})::numeric / count(*)
                         FROM jsonb_each(s.reachable_by_url || f.website_verification_results)
                         AS check_result(url, result))
               END
          FROM incoming_website_checks AS s
         WHERE f.unique_id = s.unique_id
           AND f.url_domain_invalid IS NULL
           AND {WEBSITE_INPUT_HASH} = s.website_inputs_sha256
    ''').rowcount


def export_website_matches(conn, path):
    """Export match status and evidence for original dataset links."""
    export_csv(conn, path, f'''
        SELECT f.unique_id, {FACILITY_MATCH_INPUT_HASH} AS match_inputs_sha256, checks.matches
        FROM healthcare.facilities AS f
        CROSS JOIN LATERAL (
            SELECT jsonb_object_agg(url, jsonb_strip_nulls(jsonb_build_object(
                'status', evidence->>'status', 'checkedAt', evidence->>'checkedAt',
                'evidenceUrl', CASE WHEN evidence->>'status' = 'verified' THEN url END,
                'nameEvidence', evidence->>'nameEvidence', 'addressEvidence', evidence->>'addressEvidence',
                'reason', evidence->>'reason'
            ))) AS matches
            FROM jsonb_each(f.website_facility_matches) AS check_result(url, evidence)
            WHERE evidence->>'status' IN ('verified', 'unverified', 'unavailable')
        ) AS checks
        WHERE f.website_facility_matches <> '{{}}'::jsonb AND checks.matches IS NOT NULL
        ORDER BY f.unique_id
    ''')


def load_website_matches(conn, path):
    """Fill missing hospital matches for the same facility and reachable links."""
    conn.execute('''CREATE TEMP TABLE incoming_website_matches (
        unique_id text PRIMARY KEY,
        match_inputs_sha256 text NOT NULL,
        matches jsonb NOT NULL CHECK (jsonb_typeof(matches) = 'object' AND matches <> '{}'::jsonb)
    ) ON COMMIT DROP''')
    load_csv(conn, path, 'COPY incoming_website_matches FROM STDIN WITH (FORMAT csv, HEADER MATCH)')
    return conn.execute(f'''
        WITH matched_facilities AS (
            SELECT f.unique_id, jsonb_object_agg(entry.url, entry.evidence) AS matches
              FROM healthcare.facilities AS f
              JOIN incoming_website_matches AS s USING (unique_id)
              CROSS JOIN LATERAL jsonb_each(s.matches) AS entry(url, evidence)
              CROSS JOIN LATERAL (SELECT f.website_verification_results -> entry.url AS result) AS reachability
             WHERE {FACILITY_MATCH_INPUT_HASH} = s.match_inputs_sha256
               AND {REACHABLE}
               AND NOT (f.website_facility_matches ? entry.url)
             GROUP BY f.unique_id
        )
        UPDATE healthcare.facilities AS f
           SET website_facility_matches = s.matches || f.website_facility_matches
          FROM matched_facilities AS s
         WHERE f.unique_id = s.unique_id
    ''').rowcount
