# Data Cleaning Log

**November 21, 2026 · v2, after source-backed corrections**

This run used `Datathon/facilities.csv` from `Datathon.zip` and the uploaded India Post directory CSV. The facility table went from **10,088 to 9,989 records**. The postal table went from **165,627 to 165,625 office records** and produced a lookup table with **19,586 unique Postal Index Numbers (PINs)**. This log covers the facility and postal tables. NFHS-5 has yet to be cleaned.

## Trace a change

| What to check | Where to look |
|---|---|
| Why a facility record or field changed | Find the `unique_id` or `source_record` in [removal_log.csv](removal_log.csv). Check `field`, `original_value`, `cleaned_value`, `reason`, and the source URL. |
| Which values were backfilled from evidence | Use [backfills.csv](backfills.csv) for facilities and [postal_backfills.csv](postal_backfills.csv) for postal offices. Each row records one field change. |
| Which issues are still open | Filter [review_queue.csv](review_queue.csv) by `unique_id` or `reason`. A facility record can have more than one issue. |
| Cleaned tables and run totals | [Facility table](../processed/facilities_clean.csv.gz), [postal office table](../processed/pincode_offices_clean.csv.gz), [PIN lookup](../processed/pincode_lookup.csv), and [summary.json](summary.json). |
| How to reproduce the changes | [Cleaning pipeline](../../pipeline/run_clean.py), [validation helpers](../../pipeline/audit_helpers.py), [facility correction rules](../../pipeline/source_decisions.csv), and [postal correction rules](../../pipeline/postal_source_decisions.csv). |

## Facility records and fields

| Issue or change | Rule and outcome | Count |
|---|---|---:|
| Invalid UUID | Quarantined records with an invalid UUID format and retained their source row numbers. | 88 records |
| Exact duplicate records | Kept one copy where records with the same UUID were identical. | 11 duplicates removed |
| Invalid PIN format | Removed whitespace, then cleared PINs that did not have six digits starting with 1–9. | 76 fields cleared |
| Masked email placeholder | Cleared the literal `[email protected]` placeholder. | 355 fields cleared |
| Invalid establishment year | Cleared all three `yearEstablished` values of `0`. | 3 fields cleared |
| Page update date after the run cutoff | Cleared the date `2027-07-20` because it falls after the `2026-11-21` cutoff. | 1 field cleared |
| Empty list entries | Removed blank and null entries from lists such as specialties, procedures, equipment, and source URLs. | 19,877 entries removed |
| Duplicate list entries | Removed identical entries within the same field of the same facility record. | 698,437 entries removed |
| Service or equipment attributed to the wrong facility | Removed the claims from the affected fields and retained the original wording in the evidence table. | 17 claims removed |
| Mixed branch information | Cleared PIN `110002` from the Aravind record because it combines information from different locations. The intended branch is still under review. | 1 field cleared |
| Conflicting source addresses | Wockhardt Nagpur's own pages list different PINs. Cleared the original `400078` and left the exact branch PIN open for review. | 1 field cleared |
| Bed count definition conflict | Cleared HCG Manavata's original `capacity=275`. Its certificate supports **75 sanctioned beds**, which were entered in `sanctioned_beds`. | 1 conflict |
| Source-backed backfills | Updated 22 state fields, 6 PINs, 5 cities, 1 official website, and 1 sanctioned bed count. This run added 30 of those updates. | 35 cumulative field updates |

Each correction is keyed to a facility UUID, field, and expected original value. When a state or PIN changes, the pipeline checks the resulting state–PIN pair against the postal reference. Facility directories and official websites support branch-specific details. The postal directory supports postal geography.

### Why 39 facility records have blank coordinates

| Category | How it was determined | Outcome |
|---|---|---|
| Missing from the source | Both latitude and longitude were `null` in the original `facilities.csv`. | 30 records remain blank. |
| Outside the coordinate screening bounds | `audit_helpers.py` requires finite numbers between 6°N and 38°N and between 68°E and 98°E. All six original pairs were numeric and outside these bounds. For example, Sanjivani's original longitude was −38.262634°. | Cleared latitude, longitude, and coordinate JSON for 6 records, totaling 18 fields. |
| Original point in the wrong city or state | Used geoBoundaries to locate the point within state and district boundaries and OpenStreetMap's Nominatim to identify the nearby address. Matched the original street or building number against a branch-specific source. | Cleared latitude, longitude, and coordinate JSON for 3 records, totaling 9 fields. Kept the supported branch addresses. Entrance coordinates are pending verification. |

The remaining **9,950 records** have paired coordinates that passed the screening bounds. Branch-level distance calculations still depend on confirming that a point matches the facility address.

| Facility | Original coordinates and location | Branch evidence |
|---|---|---|
| Srinivasa Nursing Home | `16.956158, 82.233063`, near Kakinada, Andhra Pradesh | The state medical education department lists the matching Netaji Chowk and TNGO’s Road address in Adilabad, Telangana. [Telangana private hospital directory, record 196](https://dme.telangana.gov.in/open_record_view.php?ID=196) |
| Omega Hospital | `17.413784, 78.424454`, near Jubilee Hills, Hyderabad | The certificate lists the matching Plot 4, Chinnagadili site in Visakhapatnam, Andhra Pradesh 530040. [NABH certificate H-2021-0883](https://portal.nabh.co/Documents/AccreditedList/Hospitals/H-2021-0883_5th%20Edition.pdf) |
| CARE Hospitals | `17.385582, 78.473969`, near Abids, Hyderabad | The Ramnagar branch page matches the original 10-50-11/5, AS Raja Complex, Waltair Main Road address in Visakhapatnam, Andhra Pradesh 530002. [CARE Hospitals contact page](https://www.carehospitals.com/contact-us) |

The [geographic review workbook](https://chatgpt.com/library?file_id=libfile_fde3_f-40417fe3a72c8191a2dc99865b6c6aba_54d4642f0dc48191b791749dc3fe1375&account_id=personal) records the original points and proposed branch locations. Map data © OpenStreetMap contributors. [geoBoundaries ADM1](https://www.geoboundaries.org/api/current/gbOpen/IND/ADM1/) · [geoBoundaries ADM2](https://www.geoboundaries.org/api/current/gbOpen/IND/ADM2/) · [Nominatim reverse geocoding](https://nominatim.org/release-docs/latest/api/Reverse/) · [OpenStreetMap attribution and licensing](https://www.openstreetmap.org/copyright)

## Postal reference and open geographic issues

| Check | Rule and outcome | Count |
|---|---|---:|
| Exact duplicate postal office records | Kept one copy of each identical row. | 2 duplicates removed |
| Unusable postal office coordinates | Of 14,617 unusable pairs, 2,617 had at least one nonempty original value that was cleared. Both coordinate fields in the other 12,000 records were missing or contained missing-value placeholders. All affected office records were retained. | 14,617 records |
| Incorrect state and district for PIN `799001` | Corrected four Agartala Division office records from `TELANGANA / Nirmal` to `TRIPURA / West Tripura`. Facility records already listing Tripura can retain their state and PIN. [West Tripura district government postal listing](https://westtripura.nic.in/public-utility/agartala-postal-ho/) | 4 postal office records, 8 fields updated |
| PIN with multiple candidate states or districts | Built a lookup with one row per PIN and retained all candidates. District ambiguity counts distinct state–district pairs. | 52 PINs with multiple states, 1,258 with multiple state–district pairs |
| More than 50 km from the nearest postal office for the same PIN | Flagged these distance outliers for review. The postal office location and facility entrance are checked independently. | 1,291 facility records |
| Distance unavailable | Left the distance blank when the facility coordinates, PIN, or usable postal office point were missing. Three confirmed wrong points have a dedicated coordinate-conflict status. | 323 unavailable distances, 3 coordinate conflicts |

After the backfills, **9,342 facility records** agree with the postal reference on PIN and state. The remaining record counts are **31** with a state conflict, **205** whose PIN is absent from the postal snapshot, **314** with an unresolved state, **15** with multiple candidate states for their PIN, and **82** whose PIN is missing or was removed. State conflicts fell from **57 to 31**. The [review queue](review_queue.csv) contains **1,558 issues** across **1,548 facility UUIDs**.

## Evidence status for service claims

- **17 claims were attributed to the wrong facility.** In 16 cases, the original entry explicitly named a different institution. A source check confirmed the attribution error in the other entry. [Reviewed claim evidence](reviewed_claim_evidence.csv)
- **6 individual claims have source support.** Accreditation scopes support five and a facility page supports one. In one additional case, the source supports the service and leaves ownership of the equipment unverified. [Verified service claims](verified_service_claims.csv) · [Reviewed claim evidence](reviewed_claim_evidence.csv)
- **549,825 claims from array fields** rely on the source dataset alone. Another **9,989 facility descriptions** have yet to be verified individually. The app should show the evidence status for each claim and verify facility names, full addresses, coordinates, and links at the branch level.
