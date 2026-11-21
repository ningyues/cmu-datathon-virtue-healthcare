import test from 'node:test';
import assert from 'node:assert/strict';
import { sampleFacilities, sortFacilities } from '../src/data/facilities.js';
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
