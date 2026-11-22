import test from 'node:test';
import assert from 'node:assert/strict';
import { facilityScore, sampleFacilities, sortFacilities } from '../src/data/facilities.js';
import { validateFacilities } from '../src/services/search.js';

test('sorts the Figma sample by trust and distance without mutating the input', () => {
  assert.deepEqual(sortFacilities(sampleFacilities, 'trust').map(x => x.id), ['ganga', 'nirmal', 'asha', 'sahyog']);
  assert.deepEqual(sortFacilities(sampleFacilities, 'distance').map(x => x.id), ['nirmal', 'ganga', 'asha', 'sahyog']);
  assert.equal(sampleFacilities[0].id, 'ganga');
});

test('missing scores and distances sort last; real zero remains valid', () => {
  const rows = [{ id: 'missing', name: 'Missing', distanceKm: null, trustScore: null }, { id: 'zero', name: 'Zero', distanceKm: 0, trustScore: 0 }];
  for (const order of ['trust', 'distance']) assert.equal(sortFacilities(rows, order)[0].id, 'zero');
});

test('rejects invalid API records instead of displaying invalid scores', () => {
  const valid = { id: 'test', name: 'Test facility' };
  assert.throws(() => validateFacilities({}));
  assert.throws(() => validateFacilities([{ ...valid, trustScore: 101 }]));
  assert.throws(() => validateFacilities([{ ...valid, distanceKm: -1 }]));
  assert.throws(() => validateFacilities([valid, valid]));
  assert.throws(() => validateFacilities([{ ...valid, area: {} }]));
  const [record] = validateFacilities([{ ...valid, marker: { x: 1, y: 2 } }]);
  assert.equal(record.trustScore, null);
  assert.equal(record.distanceKm, null);
  assert.equal(record.marker, undefined);
});

test('keeps Fit Score separate from trust and accepts geographic coordinates', () => {
  const facilities = validateFacilities([
    { id: 'far', name: 'Farther', fitScore: 85, distanceKm: 7, latitude: 17.4, longitude: 78.5, website: 'example.org' },
    { id: 'pending', name: 'Pending', distanceKm: 1, latitude: 170, longitude: 78, website: 'javascript:alert(1)' },
    { id: 'near', name: 'Nearer', fitScore: 85, distanceKm: 3 },
  ]);
  assert.deepEqual(sortFacilities(facilities, 'fit').map(row => row.id), ['near', 'far', 'pending']);
  assert.deepEqual(sortFacilities(facilities, 'distance').map(row => row.id), ['pending', 'near', 'far']);
  assert.equal(facilityScore(facilities[0], 'fit').text, '85.00/100');
  assert.equal(facilityScore(facilities[0], 'trust').text, 'Unavailable');
  assert.deepEqual(facilities[0].coordinates, { latitude: 17.4, longitude: 78.5 });
  assert.equal(facilities[0].website, 'https://example.org/');
  assert.equal(facilities[1].coordinates, null);
  assert.equal(facilities[1].website, null);
});


test('validates the percentage scale and preserves score details', () => {
  const record = {id: 'score', name: 'Scored', fitScore: 63.64, serviceMatch: 'text_match', scoreBreakdown: {
    authority: 0.7, authoritySource: 'synthetic', specialtyScore: 10, serviceScore: 10,
    rawScore: 20, maxRawScore: 22, matchScore100: 90.91,
    services: [{input: 'x-ray', score: 4}], specialties: [{input: 'radiology', matched: true}]
  }};
  assert.equal(validateFacilities([record])[0].scoreBreakdown.serviceScore, 10);
  assert.equal(validateFacilities([record])[0].serviceMatch, 'text_match');
  assert.throws(() => validateFacilities([{...record, fitScore: 101}]));
  assert.throws(() => validateFacilities([{...record, scoreBreakdown: {...record.scoreBreakdown, authority: 2}}]));
});
