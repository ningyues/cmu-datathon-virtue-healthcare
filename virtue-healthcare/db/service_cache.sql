BEGIN;
-- Serialize migration with readers and updates using the parent-first lock order.
LOCK TABLE healthcare.facilities IN SHARE ROW EXCLUSIVE MODE;
DROP TRIGGER IF EXISTS synchronize_fit_cache ON healthcare.facilities;
DROP FUNCTION IF EXISTS healthcare.synchronize_fit_cache();
-- The previous combined-query cache is derived data and cannot seed per-service scores.
DROP TABLE IF EXISTS healthcare.facility_service_fit;

CREATE TABLE IF NOT EXISTS healthcare.facility_service_scores (
    facility_id text NOT NULL REFERENCES healthcare.facilities(unique_id) ON DELETE CASCADE,
    service text NOT NULL CHECK (length(trim(service)) > 0),
    capability_match boolean NOT NULL,
    equipment_match boolean NOT NULL,
    procedure_match boolean NOT NULL,
    service_score integer GENERATED ALWAYS AS (
        2 * capability_match::integer + 2 * equipment_match::integer
        + 2 * procedure_match::integer
    ) STORED,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (facility_id, service)
);

CREATE OR REPLACE FUNCTION healthcare.invalidate_service_cache()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.capability IS DISTINCT FROM OLD.capability
       OR NEW.equipment IS DISTINCT FROM OLD.equipment
       OR NEW.procedure IS DISTINCT FROM OLD.procedure THEN
        DELETE FROM healthcare.facility_service_scores WHERE facility_id = NEW.unique_id;
    END IF;
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS invalidate_service_cache ON healthcare.facilities;
CREATE TRIGGER invalidate_service_cache
AFTER UPDATE OF capability, equipment, procedure
ON healthcare.facilities FOR EACH ROW EXECUTE FUNCTION healthcare.invalidate_service_cache();
COMMIT;
