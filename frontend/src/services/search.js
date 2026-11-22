import { sampleFacilities } from '../data/facilities.js';

const endpoint = import.meta.env?.VITE_FACILITIES_API_URL ?? '/api/search';
export const usesIllustrativeData = !endpoint;

function coordinates(record) {
  const { latitude, longitude } = record ?? {};
  if (!Number.isFinite(latitude) || Math.abs(latitude) > 90 ||
      !Number.isFinite(longitude) || Math.abs(longitude) > 180) return null;
  return { latitude, longitude };
}

function websiteUrl(value) {
  if (typeof value !== 'string' || !value.trim()) return null;
  try {
    const candidate = value.trim();
    const url = new URL(/^[a-z][a-z0-9+.-]*:/i.test(candidate) ? candidate : `https://${candidate}`);
    if (['http:', 'https:'].includes(url.protocol) && url.hostname.includes('.') && !url.username && !url.password) {
      return url.href;
    }
  } catch {
    return null;
  }
  return null;
}

export function validateFacilities(data) {
  if (!Array.isArray(data)) throw new Error('The server did not return a facilities array.');
  const ids = new Set();
  return data.map((item) => {
    if (!item || typeof item.id !== 'string' || !item.id || ids.has(item.id) || typeof item.name !== 'string' || !item.name.trim()) {
      throw new Error('The server returned an invalid facility record.');
    }
    ids.add(item.id);
    for (const key of ['area', 'postalCode', 'type', 'operatorType', 'address']) {
      if (item[key] != null && typeof item[key] !== 'string') throw new Error(`Invalid ${key} in facility data.`);
    }
    const score = item.trustScore;
    const fit = item.fitScore;
    const distance = item.distanceKm;
    const evidence = item.serviceEvidence;
    if (score != null && (!Number.isFinite(score) || score < 0 || score > 100)) throw new Error('Invalid trust score.');
    if (fit != null && (!Number.isFinite(fit) || fit < 0 || fit > 100)) throw new Error('Invalid Fit Score.');
    const breakdown = item.scoreBreakdown;
    if (breakdown != null) {
      const values = ['authority', 'specialtyScore', 'serviceScore', 'rawScore', 'maxRawScore', 'matchScore100'];
      if (values.some(key => !Number.isFinite(breakdown[key])) ||
          breakdown.authority < 0 || breakdown.authority > 1 ||
          ![0, 10].includes(breakdown.specialtyScore) || breakdown.serviceScore < 0 ||
          breakdown.maxRawScore <= 0 || breakdown.rawScore < 0 || breakdown.rawScore > breakdown.maxRawScore ||
          breakdown.matchScore100 < 0 || breakdown.matchScore100 > 100 ||
          !Array.isArray(breakdown.services) || !Array.isArray(breakdown.specialties) ||
          breakdown.services.some(s => typeof s.input !== 'string' || !Number.isFinite(s.score) || s.score < 0 || s.score > 6) ||
          breakdown.specialties.some(s => typeof s.input !== 'string' || typeof s.matched !== 'boolean')) {
        throw new Error('Invalid score breakdown.');
      }
    }
    if (distance != null && (!Number.isFinite(distance) || distance < 0)) throw new Error('Invalid distance.');
    if (evidence != null && (typeof evidence.field !== 'string' || typeof evidence.text !== 'string')) {
      throw new Error('Invalid service evidence.');
    }
    return {
      id: item.id, name: item.name, type: item.type ?? 'Type unavailable',
      area: item.area ?? 'Address unavailable', postalCode: item.postalCode ?? '',
      operatorType: item.operatorType ?? null, address: item.address ?? null,
      website: websiteUrl(item.website), coordinates: coordinates(item),
      distanceKm: distance ?? null, trustScore: score ?? null, fitScore: fit ?? null,
      scoreBreakdown: breakdown ?? null,
      featured: item.featured === true, serviceEvidence: evidence ?? null,
      serviceMatch: ['listed_in_dataset', 'related_specialty_only', 'text_match'].includes(item.serviceMatch) ? item.serviceMatch : null,
    };
  });
}

export async function searchFacilities(query, { signal } = {}) {
  if (!endpoint) return { facilities: sampleFacilities, illustrative: true };
  const response = await fetch(endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(typeof query === 'string' ? { query } : { intent: query }),
    signal,
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const details = data?.error;
    const message = typeof details === 'string' ? details
      : details?.clarification_question || details?.message || `Search failed (${response.status}). Please try again.`;
    const error = new Error(message);
    error.code = details?.code;
    error.clarification = typeof details?.clarification_question === 'string' ? details.clarification_question : null;
    throw error;
  }
  const location = coordinates(data?.queryLocation);
  return {
    facilities: validateFacilities(data?.facilities), illustrative: false,
    radiusKm: Number.isFinite(data?.radiusKm) && data.radiusKm > 0 ? data.radiusKm : null,
    queryLocation: location && {
      ...location,
      label: typeof data.queryLocation.label === 'string' ? data.queryLocation.label : null,
      approximate: data.queryLocation.approximate === true,
    },
  };
}
