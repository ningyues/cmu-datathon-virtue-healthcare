"""Python scoring with a specialty-independent service cache."""
from decimal import Decimal, ROUND_HALF_UP

SERVICE_FIELDS = ('capability', 'equipment', 'procedure')


def normalize(value):
    return ' '.join((value or '').lower().split())


def normalize_query(specialty, services):
    if isinstance(specialty, str):
        specialty = [specialty]
    specialty = sorted({normalize(term) for term in (specialty or []) if normalize(term)})
    terms = sorted({normalize(term) for term in services if normalize(term)})
    if not specialty and not terms:
        raise ValueError('Provide a specialty or service')
    return specialty, terms


def score_breakdown(authority, specialty_matched, specialty_count, service_scores):
    maximum = (10 if specialty_count else 0) + 6 * len(service_scores)
    if not maximum:
        raise ValueError('Provide a specialty or service')
    specialty_score = 10 if specialty_matched else 0
    service_score = sum(service_scores)
    raw_score = specialty_score + service_score
    match_score_100 = Decimal(raw_score) * 100 / maximum
    return dict(specialty_score=specialty_score, service_score=service_score,
                raw_score=raw_score, max_raw_score=maximum,
                match_score_100=match_score_100,
                final_score=Decimal(str(authority)) * match_score_100)


def matches_field(items, term):
    return bool(term) and any(term in normalize(item) for item in items)


def calculate_service_score(hospital, service):
    service = normalize(service)
    matches = {field: matches_field(hospital[field], service) for field in SERVICE_FIELDS}
    return 2 * sum(matches.values()), matches


def search_facilities(conn, postcode=None, specialty=None, services=(), limit=20, offset=0, city=None,
                      candidate_ids=None):
    specialty, terms = normalize_query(specialty, services)
    postcode = (postcode or '').strip() or None
    city = normalize(city) or None
    results = []
    with conn.transaction():
        # Parent locks prevent service-data changes racing with cache insertion.
        hospitals = conn.execute('''SELECT unique_id, name,
            "address_zipOrPostcode" AS postcode, address_city AS city, specialties, capability, equipment,
            procedure, authority, postcode_address_cordination_unmatch,
            url_domain_invalid, flags_origin
            FROM healthcare.facilities
            WHERE (%s::text IS NULL OR "address_zipOrPostcode" = %s)
              AND (%s::text IS NULL OR healthcare.normalize_text(address_city) = %s)
              AND (%s::text[] IS NULL OR unique_id = ANY(%s::text[]))
            ORDER BY unique_id FOR SHARE''',
            (postcode, postcode, city, city, candidate_ids, candidate_ids)).fetchall()
        if candidate_ids is not None and set(candidate_ids) - {h['unique_id'] for h in hospitals}:
            raise ValueError('Scoring database is missing candidate hospitals. Reload the snapshot.')
        if not hospitals:
            return []
        ids = [h['unique_id'] for h in hospitals]
        cached = {}
        if terms:
            cached = {(r['facility_id'], r['service']): r for r in conn.execute('''
                SELECT facility_id, service, service_score,
                       capability_match, equipment_match, procedure_match
                FROM healthcare.facility_service_scores
                WHERE service = ANY(%s) AND facility_id = ANY(%s)
            ''', (terms, ids)).fetchall()}
        missing = []
        for hospital in hospitals:
            combined = {field: False for field in SERVICE_FIELDS}
            hits = 0
            service_details = []
            for service in terms:
                entry = cached.get((hospital['unique_id'], service))
                cache_hit = entry is not None
                if entry is None:
                    score, matches = calculate_service_score(hospital, service)
                    entry = {field + '_match': value for field, value in matches.items()}
                    entry['service_score'] = score
                    missing.append((hospital['unique_id'], service,
                                    *(matches[field] for field in SERVICE_FIELDS)))
                else:
                    hits += 1
                for field in SERVICE_FIELDS:
                    combined[field] |= entry[field + '_match']
                service_details.append(dict(input=service, cache_hit=cache_hit,
                    score=entry['service_score'],
                    matches={field: entry[field + '_match'] for field in SERVICE_FIELDS}))
            specialty_details = [dict(input=term,
                matched=matches_field(hospital['specialties'], term)) for term in specialty]
            specialty_match = any(item['matched'] for item in specialty_details)
            scores = score_breakdown(hospital['authority'], specialty_match, len(specialty),
                                     [item['score'] for item in service_details])
            if scores['raw_score'] > 0:
                result = {k: v for k, v in hospital.items()
                          if k not in SERVICE_FIELDS and k != 'specialties'}
                result.update(**scores, specialty_matched=specialty_match,
                              specialty_details=specialty_details, service_details=service_details,
                              cache_hit=(hits == len(terms)) if terms else None,
                              cached_service_count=hits, requested_service_count=len(terms))
                result.update({field + '_match': hit for field, hit in combined.items()})
                results.append(result)
        if missing:
            with conn.cursor() as cursor:
                cursor.executemany('''INSERT INTO healthcare.facility_service_scores
                    (facility_id, service, capability_match, equipment_match, procedure_match)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (facility_id, service) DO NOTHING''', missing)
    # Rank before rounding to avoid changing the order of near-equal scores.
    results.sort(key=lambda r: (-r['final_score'], -r['raw_score'], r['unique_id']))
    offset = max(0, offset)
    page = results[offset:] if limit is None else results[offset:offset + max(1, min(limit, 100))]
    for result in page:
        for key in ('match_score_100', 'final_score'):
            result[key] = result[key].quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return page
