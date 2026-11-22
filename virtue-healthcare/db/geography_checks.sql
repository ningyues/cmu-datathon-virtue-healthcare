BEGIN;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='healthcare'
                   AND table_name='facilities' AND column_name='authority_calculation_mode') THEN
        ALTER TABLE healthcare.facilities ADD COLUMN authority_calculation_mode text NOT NULL DEFAULT 'formula'
            CHECK (authority_calculation_mode IN ('formula', 'manual'));
        UPDATE healthcare.facilities SET authority_calculation_mode = 'manual'
        WHERE authority <> 1 - 0.3 * coalesce(postcode_address_cordination_unmatch, 0) - 0.5 * url_domain_invalid;
    END IF;
END $$;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS geography_check_status text NOT NULL DEFAULT 'not_checked'
    CHECK (geography_check_status IN ('not_checked', 'matched', 'mismatch', 'unknown'));
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS geography_check_reasons text[] NOT NULL DEFAULT '{}';
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS geography_check_source text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS geography_checked_at timestamptz;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS reverse_geocoded_postcode text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS reverse_geocoded_city text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS reverse_geocoded_state text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS address_coordinate_distance_km double precision;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS geocoding_precision text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS geography_check_evidence jsonb NOT NULL DEFAULT '{}';

CREATE TABLE IF NOT EXISTS healthcare.geocoding_cache (
    cache_key text PRIMARY KEY,
    provider text NOT NULL,
    response jsonb NOT NULL,
    fetched_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS healthcare.geography_check_audit (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    facility_id text NOT NULL,
    checked_at timestamptz NOT NULL DEFAULT now(),
    input_snapshot jsonb NOT NULL,
    result jsonb NOT NULL,
    old_flag smallint,
    new_flag smallint,
    old_authority numeric(5,4),
    new_authority numeric(5,4)
);

-- Retire decisions made under previous policies, keeping their original evidence in the audit.
INSERT INTO healthcare.geography_check_audit
    (facility_id, input_snapshot, result, old_flag, new_flag, old_authority, new_authority)
SELECT unique_id, to_jsonb(f), '{"policy":"address_postcode_distance_conflicts_only","reason":"policy_changed"}'::jsonb,
       postcode_address_cordination_unmatch, 0, authority,
       CASE WHEN authority_calculation_mode='formula' THEN least(1, greatest(0, authority + 0.3 * coalesce(postcode_address_cordination_unmatch, 0))) ELSE authority END
FROM healthcare.facilities f
WHERE geography_check_status <> 'not_checked'
  AND geography_check_evidence->>'policy' IS DISTINCT FROM 'address_postcode_distance_conflicts_only';
UPDATE healthcare.facilities
SET geography_check_status='not_checked', geography_check_reasons=ARRAY['policy_changed'],
    geography_checked_at=NULL, geography_check_source=NULL, geography_check_evidence='{}',
    reverse_geocoded_postcode=NULL, reverse_geocoded_city=NULL, reverse_geocoded_state=NULL,
    address_coordinate_distance_km=NULL, geocoding_precision=NULL,
    postcode_address_cordination_unmatch=0,
    authority=CASE WHEN authority_calculation_mode='formula' THEN least(1, greatest(0, authority + 0.3 * coalesce(postcode_address_cordination_unmatch, 0))) ELSE authority END
WHERE geography_check_status <> 'not_checked'
  AND geography_check_evidence->>'policy' IS DISTINCT FROM 'address_postcode_distance_conflicts_only';

-- Only a confirmed geographic conflict carries a penalty.
INSERT INTO healthcare.geography_check_audit
    (facility_id, input_snapshot, result, old_flag, new_flag, old_authority, new_authority)
SELECT unique_id, to_jsonb(f), '{"policy":"address_postcode_distance_conflicts_only"}'::jsonb,
       postcode_address_cordination_unmatch,
       CASE WHEN geography_check_status='mismatch' THEN 1 ELSE 0 END, authority,
       CASE WHEN authority_calculation_mode='formula'
            THEN least(1, greatest(0, authority + 0.3 * coalesce(postcode_address_cordination_unmatch, 0)
                 - 0.3 * CASE WHEN geography_check_status='mismatch' THEN 1 ELSE 0 END)) ELSE authority END
FROM healthcare.facilities f
WHERE postcode_address_cordination_unmatch IS DISTINCT FROM
      CASE WHEN geography_check_status='mismatch' THEN 1 ELSE 0 END;
UPDATE healthcare.facilities
SET postcode_address_cordination_unmatch=CASE WHEN geography_check_status='mismatch' THEN 1 ELSE 0 END,
    authority=CASE WHEN authority_calculation_mode='formula'
        THEN least(1, greatest(0, authority + 0.3 * coalesce(postcode_address_cordination_unmatch, 0)
             - 0.3 * CASE WHEN geography_check_status='mismatch' THEN 1 ELSE 0 END)) ELSE authority END
WHERE postcode_address_cordination_unmatch IS DISTINCT FROM
      CASE WHEN geography_check_status='mismatch' THEN 1 ELSE 0 END;
ALTER TABLE healthcare.facilities ALTER COLUMN postcode_address_cordination_unmatch SET DEFAULT 0;
ALTER TABLE healthcare.facilities ALTER COLUMN postcode_address_cordination_unmatch SET NOT NULL;

CREATE OR REPLACE FUNCTION healthcare.invalidate_geography_check()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF ROW(NEW.address_line1, NEW.address_line2, NEW.address_line3,
           NEW.address_city, NEW."address_stateOrRegion", NEW."address_zipOrPostcode",
           NEW.latitude, NEW.longitude)
       IS DISTINCT FROM
       ROW(OLD.address_line1, OLD.address_line2, OLD.address_line3,
           OLD.address_city, OLD."address_stateOrRegion", OLD."address_zipOrPostcode",
           OLD.latitude, OLD.longitude) THEN
        NEW.geography_check_status := 'not_checked';
        NEW.geography_check_reasons := ARRAY['source_data_changed'];
        NEW.geography_checked_at := NULL;
        NEW.geography_check_source := NULL;
        NEW.reverse_geocoded_postcode := NULL;
        NEW.reverse_geocoded_city := NULL;
        NEW.reverse_geocoded_state := NULL;
        NEW.address_coordinate_distance_km := NULL;
        NEW.geocoding_precision := NULL;
        NEW.geography_check_evidence := '{}';
        NEW.postcode_address_cordination_unmatch := 0;
        IF NEW.authority_calculation_mode = 'formula' THEN
            NEW.authority := least(1, greatest(0, NEW.authority + 0.3 * coalesce(OLD.postcode_address_cordination_unmatch, 0)));
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS invalidate_geography_check ON healthcare.facilities;
CREATE TRIGGER invalidate_geography_check BEFORE UPDATE OF address_line1, address_line2,
    address_line3, address_city, "address_stateOrRegion", "address_zipOrPostcode", latitude, longitude
ON healthcare.facilities FOR EACH ROW EXECUTE FUNCTION healthcare.invalidate_geography_check();
COMMIT;
