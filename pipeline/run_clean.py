"""Clean facilities and the India Post reference CSV, leaving the input files untouched."""
import argparse
from collections import Counter, defaultdict
from datetime import date
from hashlib import sha256
import csv
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from audit_helpers import UUID_RE, clean, state, point, km, evidence, export_rows, table

PIN = re.compile(r"[1-9][0-9]{5}")
ROOT = Path(__file__).resolve().parent
AS_OF = "2026-11-21"
ARRAY_FIELDS = ("specialties", "procedure", "capability", "equipment",
                "source_urls", "websites", "phone_numbers", "source_types",
                "source_ids", "affiliationTypeIds", "countries")
CLAIM_ARRAYS = {"specialties", "procedure", "capability", "equipment"}
DISTRICT_ALIASES = {
    "24 paraganas south": "south 24 parganas", "24 parganas south": "south 24 parganas",
    "24 paraganas north": "north 24 parganas", "24 parganas north": "north 24 parganas",
    "kaimur (bhabua)": "kaimur",
}
EXCLUDED_CLAIMS = {"wrong_facility", "claim_text_names_other_facility"}
SUPPORTED_CLAIMS = {"accreditation_supports_service", "official_page_supports"}


def index_post(csv_path, dest):
    fields = ("pincode", "post_office_count", "state_candidates",
              "state_district_candidates", "valid_coordinate_count",
              "state_ambiguous", "district_ambiguous")
    counts = Counter()
    groups = defaultdict(lambda: {"rows": 0, "states": set(), "districts": set(), "points": set()})
    seen = set()
    removed = []
    with (ROOT/"postal_source_decisions.csv").open(encoding="utf-8", newline="") as f:
        overrides = {(r["pincode"], r["officename"]): r for r in csv.DictReader(f)}
    applied = set()
    with csv_path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        with (dest/"pincode_offices_clean.csv").open("w", encoding="utf-8-sig", newline="") as output:
            writer = csv.writer(output)
            writer.writerow([*reader.fieldnames, "source_record", "state_key", "district_key",
                             "coordinate_status"])
            for number, row in enumerate(reader, 1):
                counts["input_rows"] += 1
                key = tuple(row.values())
                if key in seen:
                    counts["exact_duplicates_removed"] += 1
                    removed.append(("postal", number, "", "", row["pincode"], "",
                                    "remove_row", "exact_duplicate", "", "", ""))
                    continue
                seen.add(key)
                pin = re.sub(r"\s+", "", row["pincode"])
                if not PIN.fullmatch(pin):
                    counts["invalid_pins_removed"] += 1
                    removed.append(("postal", number, "", "pincode", row["pincode"], "",
                                    "remove_row", "invalid_pin", "", "", ""))
                    continue
                postal_key = (pin, row["officename"])
                if postal_key in overrides:
                    decision = overrides[postal_key]
                    if (row["statename"], row["district"]) != (decision["expected_state"], decision["expected_district"]):
                        raise ValueError(f"Postal source decision no longer matches {postal_key}")
                    for field, new_value in (("statename", decision["state"]), ("district", decision["district"])):
                        removed.append(("postal", number, "", field, row[field], new_value,
                                        "reference_backfill", "verified_postal_area", decision["source_url"],
                                        "", decision["note"]))
                        row[field] = new_value
                    applied.add(postal_key)
                    counts["reference_rows_corrected"] += 1
                group = groups[pin]
                group["rows"] += 1
                st = state(row["statename"])
                district = " ".join(clean(row["district"]).casefold().split())
                district = DISTRICT_ALIASES.get(district, district)
                if st:
                    group["states"].add(st)
                if st and district:
                    group["districts"].add((st, district))
                pt = point(row["latitude"], row["longitude"])
                if pt:
                    group["points"].add(pt)
                else:
                    counts["coordinate_pairs_unusable"] += 1
                    raw_pair = [clean(row[field]) for field in ("latitude", "longitude")]
                    if any(raw_pair):
                        removed.append(("postal", number, "", "latitude+longitude", json.dumps(raw_pair), "",
                                        "remove_field", "postal_coordinate_pair_unusable", "", "", ""))
                        counts["coordinate_pairs_removed"] += 1
                row = {field: clean(value) for field, value in row.items()}
                row["pincode"] = pin
                row["latitude"], row["longitude"] = pt if pt else ("", "")
                writer.writerow([*row.values(), number, st, district,
                                 "usable" if pt else "unusable"])
                counts["output_rows"] += 1

    def lookup_rows():
        for pin, group in sorted(groups.items()):
            state_n, district_n = len(group["states"]), len(group["districts"])
            counts["state_ambiguous_pins"] += int(state_n > 1)
            counts["district_ambiguous_pins"] += int(district_n > 1)
            yield (pin, group["rows"], json.dumps(sorted(group["states"])),
                   json.dumps(sorted(group["districts"]), ensure_ascii=False), len(group["points"]),
                   int(state_n > 1), int(district_n > 1))

    table(dest/"pincode_lookup.csv", fields, lookup_rows())
    counts["unique_pins"] = len(groups)
    if applied != set(overrides):
        raise ValueError(f"Unapplied postal overrides: {sorted(set(overrides) - applied)}")
    assert counts["input_rows"] == counts["output_rows"] + counts["invalid_pins_removed"] + counts["exact_duplicates_removed"]
    return groups, counts, removed


def build(zip_path, csv_path, dest):
    csv.field_size_limit(16_000_000)
    with ZipFile(zip_path) as z:
        header, records = export_rows(z, "Datathon/facilities.csv")
        prior_pins, prior_claims = evidence(z)
    reference, postal_counts, removed = index_post(csv_path, dest)
    with (ROOT/"source_decisions.csv").open(encoding="utf-8", newline="") as f:
        decisions = defaultdict(list)
        seen_fields = set()
        for decision in csv.DictReader(f):
            key = (decision["id"], decision["field"])
            if key in seen_fields:
                raise ValueError(f"Duplicate hospital source decision: {key}")
            seen_fields.add(key)
            decisions[decision["id"]].append(decision)
    by_id = defaultdict(list)
    counts, field_actions, pin_checks, claim_checks = Counter(), Counter(), Counter(), Counter()
    evidence_rows, services, queue = [], [], []
    for num, (row, start, end) in enumerate(records, 1):
        if not UUID_RE.fullmatch(row["unique_id"]):
            counts["invalid_uuid"] += 1
            removed.append(("hospital", num, "", "unique_id", "", "", "remove_row",
                            "invalid_uuid", "", "", f"Raw physical lines {start}–{end}"))
        else:
            by_id[row["unique_id"].lower()].append((num, row))
    cleaned_cols = [*header, "sanctioned_beds", "name_standardized", "source_record", "pin_status", "postal_state_candidates",
                    "postal_district_candidates", "nearest_post_office_km", "geography_status", "source_backfill_fields"]
    claim_cols = ["unique_id", "source_record", "field", "claim_text", "status"]
    known_states = set().union(*(g["states"] for g in reference.values()))
    applied_ids = set()
    count_output = 0
    with (dest/"facilities_clean.csv").open("w", encoding="utf-8-sig", newline="") as clean_file, \
         (dest/"facility_claims.csv").open("w", encoding="utf-8-sig", newline="") as claims_file:
        hospital_writer, claim_writer = csv.writer(clean_file), csv.writer(claims_file)
        hospital_writer.writerow(cleaned_cols)
        claim_writer.writerow(claim_cols)
        for uid, rows in by_id.items():
            number, original = rows[0]
            if any(r != original for _, r in rows):
                for idx, _ in rows:
                    removed.append(("hospital", idx, uid, "unique_id", uid, "", "remove_row",
                                    "conflicting_uuid", "", "", ""))
                    counts["conflicting_uuid_rows"] += 1
                continue
            for idx, _ in rows[1:]:
                counts["exact_duplicates_removed"] += 1
                removed.append(("hospital", idx, uid, "unique_id", uid, "", "remove_row",
                                "exact_duplicate", "", "", f"Retained logical record {number}"))
            row = {field: clean(val) for field, val in original.items()}
            row["sanctioned_beds"] = ""
            branch = (original["unique_id"], original["name"], original["address_city"], original["address_line1"])
            row["address_zipOrPostcode"] = re.sub(r"\s+", "", row["address_zipOrPostcode"])

            def change(field, value, reason, url="", second="", note=""):
                old = row[field]
                if old == value:
                    return
                field_actions[reason] += 1
                removed.append(("hospital", number, uid, field, original.get(field, old), value,
                                "source_backfill" if value else "remove_field", reason, url, second, note))
                row[field] = value

            repaired = []
            edits = decisions.get(uid, [])
            resulting_location = {field: row[field] for field in ("address_stateOrRegion", "address_zipOrPostcode")}
            edited_location = {edit["field"]: edit["value"] for edit in edits if edit["field"] in resulting_location}
            resulting_location.update(edited_location)
            if any(edited_location.values()):
                pin = resulting_location["address_zipOrPostcode"]
                st = state(resulting_location["address_stateOrRegion"])
                if pin not in reference or st not in reference[pin]["states"]:
                    raise ValueError(f"Source-backed state and PIN conflict for {uid}: {st} / {pin}")
            coordinate_conflict = any(d["status"] == "coordinate_location_conflict" for d in edits)
            for d in edits:
                field, old, new = d["field"], d["expected"], d["value"]
                if row[field] != old:
                    raise ValueError(f"Source decision key changed for {uid} / {field}")
                change(field, new, d["status"], d["source_url"], d["corroborating_url"], d["note"])
                applied_ids.add(uid)
                if new:
                    repaired.append(field)
                elif d["status"] != "coordinate_location_conflict":
                    queue.append((uid, field, d["status"], d["source_url"], d["note"]))
            if coordinate_conflict:
                field_actions["coordinate_locations_withdrawn"] += 1
                queue.append((uid, "coordinates", "coordinate_location_conflict", "",
                              "Original point was withdrawn. Obtain a branch-level location before distance ranking."))
            if row["address_zipOrPostcode"] and not PIN.fullmatch(row["address_zipOrPostcode"]):
                change("address_zipOrPostcode", "", "invalid_pin_format")
            if row["email"].casefold() in ("[email protected]", "[email\u00a0protected]"):
                change("email", "", "masked_email")
            for field in ("yearEstablished", "numberDoctors", "capacity", "area"):
                val = row[field]
                if val and not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", val):
                    change(field, "", "invalid_nonnegative_number")
                elif val and field == "yearEstablished" and (not float(val).is_integer() or not 1 <= float(val) <= int(AS_OF[:4])):
                    change(field, "", "invalid_establishment_year")
            for field in ("recency_of_page_update", "post_metrics_most_recent_social_media_post_date"):
                day = row[field][:10]
                try:
                    parsed_day = date.fromisoformat(day)
                except ValueError:
                    continue
                if parsed_day > date.fromisoformat(AS_OF):
                    change(field, "", "future_page_or_post_date")
            lat, lon = row["latitude"], row["longitude"]
            pt = point(lat, lon)
            if (lat or lon) and not pt:
                for field in ("latitude", "longitude", "coordinates"):
                    change(field, "", "coordinate_pair_unusable")

            verified_for_branch = []
            for field in ARRAY_FIELDS:
                raw_value = row[field]
                if not raw_value:
                    continue
                try:
                    values = json.loads(raw_value)
                except ValueError:
                    values = None
                if not isinstance(values, list):
                    change(field, "", "unparseable_list", note="Original value retained in the change log")
                    continue
                kept = []
                seen_text = set()
                for value in values:
                    if value is None or (isinstance(value, str) and not clean(value)):
                        field_actions["empty_array_items_removed"] += 1
                        continue
                    if not isinstance(value, str) and field in CLAIM_ARRAYS:
                        field_actions["nontext_claim_items_removed"] += 1
                        removed.append(("hospital", number, uid, field, json.dumps(value), "",
                                        "remove_claim", "nontext_claim_item", "", "", ""))
                        continue
                    normalized = clean(value) if isinstance(value, str) else value
                    key = json.dumps(normalized, ensure_ascii=False, sort_keys=True)
                    if key in seen_text:
                        field_actions["exact_array_duplicates_removed"] += 1
                        continue
                    seen_text.add(key)
                    proof = prior_claims.get((branch, field, normalized)) if field in CLAIM_ARRAYS else None
                    status = proof[0] if proof else "dataset_only"
                    if field in CLAIM_ARRAYS:
                        claim_checks[status] += 1
                        claim_writer.writerow([uid, number, field, normalized, status])
                    if proof:
                        evidence_rows.append((uid, field, normalized, *proof))
                    if status in EXCLUDED_CLAIMS:
                        field_actions["wrong_facility_claims_removed"] += 1
                        removed.append(("hospital", number, uid, field, normalized, "", "remove_claim",
                                        status, proof[1], "", proof[2]))
                        continue
                    kept.append(normalized)
                    if status in SUPPORTED_CLAIMS:
                        verified_for_branch.append((field, normalized, *proof))
                if field == "specialties":
                    unique_specialties = {}
                    duplicate_count = 0
                    for specialty in kept:
                        key = specialty.casefold()
                        if key in unique_specialties:
                            duplicate_count += 1
                            removed.append(("hospital", number, uid, field, specialty, unique_specialties[key],
                                            "remove_claim", "specialty_case_duplicate", "", "", ""))
                        else:
                            unique_specialties[key] = specialty
                    if duplicate_count:
                        field_actions["specialty_case_duplicates_removed"] += duplicate_count
                        field_actions["specialty_records_deduplicated"] += 1
                    kept = list(unique_specialties.values())
                row[field] = json.dumps(kept, ensure_ascii=False) if kept else ""
            pin = row["address_zipOrPostcode"]
            p = reference.get(pin)
            st = state(row["address_stateOrRegion"])
            pin_status = "missing_or_removed" if not pin else "not_in_snapshot" if p is None else (
                "ambiguous_state" if len(p["states"]) > 1 else
                "state_unresolved" if not p["states"] or st not in known_states else
                "state_consistent" if st in p["states"] else "state_conflict")
            pin_checks[pin_status] += 1
            distance = min((km(pt, dst) for dst in p["points"]), default=None) if pt and p else None
            if coordinate_conflict:
                geo = "coordinate_location_conflict"
            elif distance is None:
                geo = "distance_unavailable"
            else:
                geo = "review_over_50_km" if distance > 50 else "postal_distance_within_50_km"
            if pin_status in {"not_in_snapshot", "ambiguous_state", "state_conflict"} or geo == "review_over_50_km":
                queue.append((uid, "geography", f"{pin_status} / {geo}", "", "Postal screening only"))
            if branch in prior_pins:
                prior, ref_pin, url, second, note = prior_pins[branch]
                if prior == "reference_sources_disagree" or (ref_pin and ref_pin != pin):
                    queue.append((uid, "address_zipOrPostcode", "prior_external_pin_needs_review", url, f"{ref_pin} {note}".strip()))
            if row["description"]:
                claim_checks["description_unreviewed"] += 1
                claim_writer.writerow([uid, number, "description", row["description"], "dataset_only"])
            for field, claim, status, url, note, reviewed_on in verified_for_branch:
                services.append((uid, row["name"], field, claim, status, url, note, reviewed_on, geo))
            hospital_writer.writerow([*(row[k] for k in [*header,"sanctioned_beds"]), " ".join(row["name"].split()), number, pin_status,
                                       json.dumps(sorted(p["states"]) if p else [], ensure_ascii=False),
                                       json.dumps(sorted(p["districts"]) if p else [], ensure_ascii=False),
                                       round(distance, 1) if distance is not None else "", geo, "|".join(repaired)])
            count_output += 1
    assert applied_ids == set(decisions)
    assert len(records) == count_output + sum(counts.values())
    assert sum(pin_checks.values()) == count_output
    log_cols = ("table", "source_record", "unique_id", "field", "original_value", "cleaned_value",
                "action", "reason", "source_url", "corroborating_url", "note")
    table(dest/"removal_log.csv", log_cols, removed)
    table(dest/"backfills.csv", log_cols, [r for r in removed if r[6] == "source_backfill"])
    table(dest/"postal_backfills.csv", log_cols, [r for r in removed if r[6] == "reference_backfill"])
    table(dest/"review_queue.csv", ("unique_id", "field", "reason", "source_url", "note"), queue)
    table(dest/"reviewed_claim_evidence.csv", ("unique_id","field","claim","status","url","note","reviewed_on"), evidence_rows)
    table(dest/"verified_service_claims.csv", ("unique_id","name","field","claim","status","source_url","note","reviewed_on","geography_status"),services)
    summary = {
        "as_of_date":AS_OF,"hospital_input_rows":len(records),"hospital_output_rows":count_output,
        "hospital_removed_rows":dict(counts),"post":dict(postal_counts),"field_actions":dict(field_actions),
        "pin_checks_after_cleaning":dict(pin_checks),"claims":dict(claim_checks),
        "verified_service_claim_rows":len(services),"review_queue_rows":len(queue),
        "dataset_sha256":{"datathon_zip":hash_file(zip_path),"postal_csv":hash_file(csv_path)},
    }
    (dest/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return summary


def hash_file(path):
    digest = sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--zip", required=True, type=Path)
    cli.add_argument("--postal", required=True, type=Path)
    cli.add_argument("--out", required=True, type=Path)
    args = cli.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=args.out) as directory:
        snapshot = Path(directory)
        result = build(args.zip, args.postal, snapshot)
        for product in snapshot.iterdir():
            product.replace(args.out/product.name)
    print(json.dumps(result, ensure_ascii=False, indent=2))
