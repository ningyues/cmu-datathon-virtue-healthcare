BEGIN;
CREATE SCHEMA IF NOT EXISTS healthcare;

CREATE TABLE IF NOT EXISTS healthcare.facilities (
    "unique_id" text PRIMARY KEY,
    "source_types" text,
    "source_ids" text,
    "source_content_id" text,
    "name" text,
    "organization_type" text,
    "content_table_id" text,
    "phone_numbers" text,
    "officialPhone" text,
    "email" text,
    "websites" text,
    "officialWebsite" text,
    "yearEstablished" text,
    "acceptsVolunteers" text,
    "facebookLink" text,
    "address_line1" text,
    "address_line2" text,
    "address_line3" text,
    "address_city" text,
    "address_stateOrRegion" text,
    "address_zipOrPostcode" text,
    "address_country" text,
    "address_countryCode" text,
    "countries" text,
    "facilityTypeId" text,
    "operatorTypeId" text,
    "affiliationTypeIds" text,
    "description" text,
    "area" text,
    "numberDoctors" text,
    "capacity" text,
    "specialties" text[] NOT NULL DEFAULT '{}',
    "procedure" text[] NOT NULL DEFAULT '{}',
    "equipment" text[] NOT NULL DEFAULT '{}',
    "capability" text[] NOT NULL DEFAULT '{}',
    "recency_of_page_update" text,
    "distinct_social_media_presence_count" text,
    "affiliated_staff_presence" text,
    "custom_logo_presence" text,
    "number_of_facts_about_the_organization" text,
    "post_metrics_most_recent_social_media_post_date" text,
    "post_metrics_post_count" text,
    "engagement_metrics_n_followers" text,
    "engagement_metrics_n_likes" text,
    "engagement_metrics_n_engagements" text,
    "source" text,
    "coordinates" text,
    "latitude" double precision,
    "longitude" double precision,
    "cluster_id" text,
    "source_urls" text,
    "sanctioned_beds" text,
    "name_standardized" text,
    "source_record" bigint,
    "pin_status" text,
    "postal_state_candidates" text,
    "postal_district_candidates" text,
    "nearest_post_office_km" text,
    "geography_status" text,
    "source_backfill_fields" text,
    postcode_address_cordination_unmatch smallint NOT NULL CHECK (postcode_address_cordination_unmatch IN (0, 1)),
    url_domain_invalid numeric,
    website_verification_results jsonb NOT NULL DEFAULT '{}',
    authority numeric(5,4) NOT NULL CHECK (authority BETWEEN 0 AND 1),
    flags_origin text NOT NULL DEFAULT 'synthetic',
    raw_record jsonb NOT NULL DEFAULT '{}',
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- Upgrade the earlier partial schema without deleting existing records or scores.
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "unique_id" text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "source_types" text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "source_ids" text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "source_content_id" text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "name" text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "organization_type" text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "content_table_id" text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "phone_numbers" text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "officialPhone" text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "email" text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "websites" text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "officialWebsite" text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "yearEstablished" text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "acceptsVolunteers" text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "facebookLink" text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "address_line1" text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "address_line2" text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "address_line3" text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "address_city" text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "address_stateOrRegion" text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "address_zipOrPostcode" text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "address_country" text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "address_countryCode" text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "countries" text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "facilityTypeId" text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "operatorTypeId" text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "affiliationTypeIds" text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "description" text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "area" text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "numberDoctors" text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "capacity" text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "specialties" text[] NOT NULL DEFAULT '{}';
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "procedure" text[] NOT NULL DEFAULT '{}';
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "equipment" text[] NOT NULL DEFAULT '{}';
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "capability" text[] NOT NULL DEFAULT '{}';
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "recency_of_page_update" text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "distinct_social_media_presence_count" text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "affiliated_staff_presence" text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "custom_logo_presence" text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "number_of_facts_about_the_organization" text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "post_metrics_most_recent_social_media_post_date" text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "post_metrics_post_count" text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "engagement_metrics_n_followers" text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "engagement_metrics_n_likes" text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "engagement_metrics_n_engagements" text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "source" text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "coordinates" text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "latitude" double precision;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "longitude" double precision;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "cluster_id" text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "source_urls" text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "sanctioned_beds" text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "name_standardized" text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "source_record" bigint;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "pin_status" text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "postal_state_candidates" text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "postal_district_candidates" text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "nearest_post_office_km" text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "geography_status" text;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS "source_backfill_fields" text;
ALTER TABLE healthcare.facilities ALTER COLUMN authority DROP EXPRESSION IF EXISTS;
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_attribute
               WHERE attrelid = 'healthcare.facilities'::regclass
                 AND attname = 'authority'
                 AND format_type(atttypid, atttypmod) <> 'numeric(5,4)') THEN
        ALTER TABLE healthcare.facilities ALTER COLUMN authority TYPE numeric(5,4);
    END IF;
END $$;
ALTER TABLE healthcare.facilities ALTER COLUMN raw_record SET DEFAULT '{}';
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS url_domain_invalid numeric;
ALTER TABLE healthcare.facilities ADD COLUMN IF NOT EXISTS website_verification_results jsonb NOT NULL DEFAULT '{}';
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_attribute
               WHERE attrelid = 'healthcare.facilities'::regclass
                 AND attname = 'url_domain_invalid' AND atttypid = 'smallint'::regtype) THEN
        DROP FUNCTION IF EXISTS healthcare.search_facilities(text, text, text[], integer, integer);
        -- The old seeded 0/1 values contain no website evidence.
        ALTER TABLE healthcare.facilities
            DROP CONSTRAINT IF EXISTS facilities_url_domain_invalid_check,
            ALTER COLUMN url_domain_invalid DROP DEFAULT,
            ALTER COLUMN url_domain_invalid DROP NOT NULL,
            ALTER COLUMN url_domain_invalid TYPE numeric USING NULL::numeric;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'healthcare.facilities'::regclass
                   AND conname = 'url_verified_ratio_range') THEN
        ALTER TABLE healthcare.facilities ADD CONSTRAINT url_verified_ratio_range
            CHECK (url_domain_invalid BETWEEN 0 AND 1);
    END IF;
END $$;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'healthcare.facilities'::regclass
                   AND conname = 'authority_range') THEN
        ALTER TABLE healthcare.facilities ADD CONSTRAINT authority_range CHECK (authority BETWEEN 0 AND 1);
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS facilities_address_postcode_idx
    ON healthcare.facilities("address_zipOrPostcode");

CREATE TABLE IF NOT EXISTS healthcare.pincode_offices (
    "circlename" text,
    "regionname" text,
    "divisionname" text,
    "officename" text,
    "pincode" text,
    "officetype" text,
    "delivery" text,
    "district" text,
    "statename" text,
    "latitude" double precision,
    "longitude" double precision,
    "source_record" bigint PRIMARY KEY,
    "state_key" text,
    "district_key" text,
    "coordinate_status" text
);
CREATE INDEX IF NOT EXISTS pincode_offices_pin_idx ON healthcare.pincode_offices(pincode);

CREATE OR REPLACE FUNCTION healthcare.normalize_text(value text)
RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT lower(trim(regexp_replace(
        coalesce(value, ''), '[[:space:]]+', ' ', 'g'
    )));
$$;

-- Match literal substrings within individual array items, case-insensitively.
-- Percent and underscore characters are literals, not SQL wildcards.
CREATE OR REPLACE FUNCTION healthcare.field_matches(items text[], terms text[])
RETURNS boolean LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT EXISTS (
        SELECT 1
        FROM unnest(items) AS item(value)
        CROSS JOIN unnest(terms) AS term(value)
        WHERE healthcare.normalize_text(term.value) <> ''
          AND strpos(healthcare.normalize_text(item.value),
                     healthcare.normalize_text(term.value)) > 0
    );
$$;

CREATE OR REPLACE FUNCTION healthcare.search_facilities(
    p_postcode text DEFAULT NULL,
    p_specialty text DEFAULT NULL,
    p_services text[] DEFAULT '{}',
    p_limit integer DEFAULT 20,
    p_offset integer DEFAULT 0
)
RETURNS TABLE (
    unique_id text, name text, postcode text,
    specialty_match boolean, capability_match boolean,
    equipment_match boolean, procedure_match boolean,
    service_score integer, authority numeric, final_score numeric,
    postcode_address_cordination_unmatch smallint,
    url_domain_invalid numeric, flags_origin text
)
LANGUAGE sql STABLE AS $$
    WITH matches AS (
        SELECT f.*,
            healthcare.field_matches(f.specialties, ARRAY[p_specialty]) AS sm,
            healthcare.field_matches(f.capability, p_services) AS cm,
            healthcare.field_matches(f.equipment, p_services) AS em,
            healthcare.field_matches(f.procedure, p_services) AS pm
        FROM healthcare.facilities f
        WHERE nullif(trim(p_postcode), '') IS NULL
           OR f."address_zipOrPostcode" = trim(p_postcode)
    ), scored AS (
        SELECT m.*, (10 * sm::integer + 2 * cm::integer
                   + 2 * em::integer + 2 * pm::integer) AS points
        FROM matches m
    )
    SELECT s.unique_id, s.name, s."address_zipOrPostcode",
           s.sm, s.cm, s.em, s.pm, s.points,
           s.authority, s.points * s.authority,
           s.postcode_address_cordination_unmatch,
           s.url_domain_invalid, s.flags_origin
    FROM scored s
    WHERE s.points > 0
    ORDER BY s.points * s.authority DESC, s.points DESC, s.unique_id
    LIMIT greatest(1, least(coalesce(p_limit, 20), 100))
    OFFSET greatest(0, coalesce(p_offset, 0));
$$;
COMMIT;
