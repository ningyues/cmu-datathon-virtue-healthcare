import { sampleFacilities } from '../data/facilities.js';

export function validateFacilities(data) {
  if (!Array.isArray(data)) throw new Error('The server did not return a facilities array.');
  const ids = new Set();
  return data.map((item) => {
    if (!item || typeof item.id !== 'string' || !item.id || ids.has(item.id) || typeof item.name !== 'string' || !item.name.trim()) {
      throw new Error('The server returned an invalid facility record.');
    }
    ids.add(item.id);
    for (const key of ['area', 'postalCode', 'type']) {
      if (item[key] != null && typeof item[key] !== 'string') throw new Error(`Invalid ${key} in facility data.`);
    }
    const score = item.trustScore;
    const distance = item.distanceKm;
    if (score != null && (!Number.isFinite(score) || score < 0 || score > 100)) throw new Error('Invalid trust score.');
    if (distance != null && (!Number.isFinite(distance) || distance < 0)) throw new Error('Invalid distance.');
    // Real records are never placed at the illustrative map's pixel coordinates.
    return { id: item.id, name: item.name, type: item.type ?? 'Type unavailable', area: item.area ?? 'Address unavailable', postalCode: item.postalCode ?? '', distanceKm: distance ?? null, trustScore: score ?? null, featured: item.featured === true };
  });
}

export async function searchFacilities(query, { signal } = {}) {
  const endpoint = import.meta.env?.VITE_FACILITIES_API_URL;
  if (!endpoint) return { facilities: sampleFacilities, illustrative: true };
  const response = await fetch(endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query }),
    signal,
  });
  if (!response.ok) throw new Error(`Search failed (${response.status}). Please try again.`);
  const data = await response.json();
  return { facilities: validateFacilities(data.facilities), illustrative: false };
}
