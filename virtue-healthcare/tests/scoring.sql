-- Run with psql -v ON_ERROR_STOP=1 "$DATABASE_URL" -f tests/scoring.sql.
-- All fixtures are rolled back.
BEGIN;
INSERT INTO healthcare.facilities (
    unique_id, name, "address_zipOrPostcode", specialties, capability, equipment, procedure,
    postcode_address_cordination_unmatch, url_domain_invalid, authority, raw_record
) VALUES
 ('test:full', 'Full Match', 'TEST_PIN', ARRAY['Nephrology'],
  ARRAY['Dialysis care'], ARRAY['Dialysis machine'], ARRAY['Dialysis'], 0, 0, 1.0, '{}'),
 ('test:penalty', 'Penalized Match', 'TEST_PIN', ARRAY['Nephrology'],
  ARRAY['Dialysis care'], ARRAY['Dialysis machine'], ARRAY['Dialysis'], 1, 1, 0.2, '{}'),
 ('test:other', 'Other Postcode', 'OTHER_PIN', ARRAY['Nephrology'],
  '{}', '{}', '{}', 0, 1, 0.5, '{}');

DO $$
DECLARE r record; n integer;
BEGIN
    SELECT * INTO r FROM healthcare.search_facilities(
        'TEST_PIN', 'nephrology', ARRAY['dialysis', 'dialysis', 'machine'])
    WHERE unique_id = 'test:full';
    IF r.final_score IS DISTINCT FROM 16::numeric THEN
        RAISE EXCEPTION 'Full score or duplicate-term cap failed';
    END IF;
    SELECT * INTO r FROM healthcare.search_facilities(
        'TEST_PIN', 'NEPHROLOGY', ARRAY['dialysis'])
    WHERE unique_id = 'test:penalty';
    IF r.authority IS DISTINCT FROM 0.2::numeric OR r.final_score IS DISTINCT FROM 3.2::numeric THEN
        RAISE EXCEPTION 'Authority penalties failed';
    END IF;
    SELECT count(*) INTO n FROM healthcare.search_facilities('TEST_PIN', NULL, ARRAY['%']);
    IF n <> 0 THEN RAISE EXCEPTION 'Wildcard input was not literal'; END IF;
    SELECT count(*) INTO n FROM healthcare.search_facilities('TEST_PIN', '   ', ARRAY['']);
    IF n <> 0 THEN RAISE EXCEPTION 'Blank input matched'; END IF;
    SELECT count(*) INTO n FROM healthcare.search_facilities('TEST_PIN', 'nephrology', '{}');
    IF n <> 2 THEN RAISE EXCEPTION 'Postcode filtering failed'; END IF;
    UPDATE healthcare.facilities SET authority = 0.875 WHERE unique_id = 'test:penalty';
    SELECT * INTO r FROM healthcare.search_facilities('TEST_PIN', 'nephrology', ARRAY['dialysis'])
    WHERE unique_id = 'test:penalty';
    IF r.final_score IS DISTINCT FROM 14::numeric THEN
        RAISE EXCEPTION 'Persisted authority override was not used';
    END IF;
    UPDATE healthcare.facilities SET url_domain_invalid = 0 WHERE unique_id = 'test:penalty';
    SELECT authority INTO r FROM healthcare.facilities WHERE unique_id = 'test:penalty';
    IF r.authority IS DISTINCT FROM 0.875::numeric THEN
        RAISE EXCEPTION 'Authority must not auto-update when flags change';
    END IF;
    BEGIN
        UPDATE healthcare.facilities SET authority = 1.1 WHERE unique_id = 'test:penalty';
        RAISE EXCEPTION 'Out-of-range authority was accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;
END;
$$;
ROLLBACK;
