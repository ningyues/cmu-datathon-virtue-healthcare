import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import { createServer } from 'vite';
import React from 'react';

test('linked Practo ratings load on cards without opening details; missing links stay unavailable', async () => {
  const dom = new JSDOM('<html><body></body></html>', {url: 'http://localhost', pretendToBeVisual: true});
  for (const key of ['window', 'document', 'navigator', 'HTMLElement', 'Element', 'Node', 'MutationObserver']) {
    Object.defineProperty(globalThis, key, {configurable: true, value: dom.window[key]});
  }
  globalThis.getComputedStyle = dom.window.getComputedStyle;
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  globalThis.ResizeObserver = class { observe() {} disconnect() {} };
  const previousFetch = globalThis.fetch;
  const calls = [];
  const pending = new Map();
  globalThis.fetch = async (url, options) => {
    const payload = JSON.parse(options.body);
    calls.push({url, ...payload});
    if (url === '/api/nabh/verify') return {ok: true, json: async () => ({status: 'unverified', certificateUrls: []})};
    assert.equal(url, '/api/practo/rating');
    return new Promise(resolve => pending.set(payload.facilityId, data => resolve({ok: true, json: async () => data})));
  };
  const {render, within, cleanup, act, waitFor} = await import('@testing-library/react');
  const {default: userEvent} = await import('@testing-library/user-event');
  const screen = within(dom.window.document.body);
  const server = await createServer({server: {middlewareMode: true, ws: false}, appType: 'custom'});
  try {
    const {default: ResultsPage} = await server.ssrLoadModule('/src/components/ResultsPage.jsx');
    const facilities = ['first', 'second', 'third'].map((id, index) => ({id, name: `Hospital ${index + 1}`,
      fitScore: 70 - index, hasPractoLink: index !== 1,
      websiteLinks: index === 0 ? [{index: 0, url: 'https://hospital.example/',
        verification: {status: 'verified', evidenceUrl: 'https://hospital.example/'}}] : []}));
    const user = userEvent.setup({document: dom.window.document});
    render(React.createElement(React.StrictMode, null,
      React.createElement(ResultsPage, {facilities, illustrative: false, status: 'success'})));
    const card = index => screen.getByRole('button', {name: new RegExp(`Hospital ${index}, fit score`)});
    await waitFor(() => assert.equal(calls.filter(call => call.url === '/api/practo/rating').length, 2));
    assert.deepEqual(calls.filter(call => call.url === '/api/practo/rating').map(call => call.facilityId), ['first', 'third']);
    assert.ok(within(card(1)).getByText('Practo rating: Checking…'));
    assert.ok(within(card(2)).getByText('Practo rating: Rating unavailable'));
    assert.equal(calls.filter(call => call.url === '/api/website/verify').length, 0);
    await act(async () => pending.get('first')({status: 'available', score: 4.5, scale: 5,
      ratingCount: null, patientStoryCount: 29, sourceType: 'live_page',
      sourceUrl: 'https://www.practo.com/pune/hospital/example-hospital', reason: 'Read linked Practo page.'}));
    assert.ok(within(card(1)).getByText('4.5/5'));
    await user.click(card(1));
    assert.ok(within(screen.getByRole('region', {name: 'Website verification'})).getByText('Verified'));
    assert.equal(calls.filter(call => call.url === '/api/website/verify').length, 0);
    assert.equal(calls.filter(call => call.url === '/api/practo/rating').length, 2);
    await act(async () => pending.get('third')({status: 'unavailable', score: null, reason: 'Practo blocked access.'}));
    assert.ok(within(card(3)).getByText('Practo rating: Rating unavailable'));
    await user.click(screen.getByRole('button', {name: 'Close facility details'}));
    assert.ok(within(card(1)).getByText('4.5/5'));
    await user.click(card(2));
    assert.equal(calls.filter(call => call.url === '/api/practo/rating' && call.facilityId === 'second').length, 0);
    assert.equal(screen.queryByRole('link', {name: /View Practo source/}), null);
    const {getPractoRating} = await server.ssrLoadModule('/src/services/verification.js');
    for (const sourceUrl of ['https://bad.example/copy', 'https://www.practo.com/pune/doctor/example',
      'https://www.practo.com/pune/hospitals']) {
      const request = getPractoRating('third');
      pending.get('third')({status: 'available', score: 4.5, scale: 5, ratingCount: null, sourceUrl});
      assert.equal((await request).status, 'unavailable');
    }
  } finally { cleanup(); await server.close(); globalThis.fetch = previousFetch; dom.window.close(); }
});
