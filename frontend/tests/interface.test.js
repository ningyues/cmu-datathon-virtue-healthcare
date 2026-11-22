import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import { createServer } from 'vite';
import React from 'react';

test('search validation, results, distance sorting, drawer keyboard controls, and return to search', async () => {
  const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'http://localhost', pretendToBeVisual: true });
  for (const key of ['window', 'document', 'navigator', 'HTMLElement', 'HTMLLabelElement', 'Element', 'Node', 'MutationObserver']) {
    Object.defineProperty(globalThis, key, { configurable: true, value: dom.window[key] });
  }
  dom.window.scrollTo = () => {};
  globalThis.getComputedStyle = dom.window.getComputedStyle;
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  globalThis.ResizeObserver = class { observe() {} disconnect() {} };
  const { render, screen, cleanup } = await import('@testing-library/react');
  const { default: userEvent } = await import('@testing-library/user-event');
  const server = await createServer({
    define: { 'import.meta.env.VITE_FACILITIES_API_URL': JSON.stringify('') },
    server: { middlewareMode: true, ws: false },
    appType: 'custom',
  });
  try {
    const { default: App } = await server.ssrLoadModule('/src/App.jsx');
    const user = userEvent.setup({ document: dom.window.document });
    render(React.createElement(App));
    await user.click(screen.getByRole('button', { name: 'Send ↑' }));
    assert.match(screen.getByRole('alert').textContent, /Enter the care/);
    const query = screen.getByLabelText('How can I help you?');
    await user.type(query, 'I need to find a nursing service in 800001');
    await user.click(screen.getByRole('button', { name: 'Send ↑' }));
    await screen.findByRole('heading', { name: 'Search results' });
    assert.ok(screen.getByText('4 facilities · Illustrative data'));
    await user.selectOptions(screen.getByLabelText('Sort by'), 'distance');
    assert.match(screen.getAllByRole('button', { name: /trust score/ })[0].textContent, /1\. Nirmal/);
    await user.click(screen.getByRole('button', { name: /Nirmal Care Hospital, trust score/ }));
    assert.ok(screen.getByRole('dialog', { name: 'Nirmal Care Hospital' }));
    const close = screen.getByRole('button', { name: 'Close facility details' });
    assert.equal(dom.window.document.activeElement, close);
    assert.equal(screen.queryByRole('button', { name: 'View details →' }), null);
    await user.keyboard('{Escape}');
    assert.equal(screen.queryByRole('dialog'), null);
    assert.match(dom.window.document.activeElement.getAttribute('aria-label'), /Nirmal/);
    await user.click(screen.getByRole('button', { name: 'Open Asha Multispeciality Centre' }));
    assert.ok(screen.getByRole('dialog', { name: 'Asha Multispeciality Centre' }));
    await user.click(screen.getByRole('button', { name: 'Close facility details' }));
    await user.click(screen.getByRole('button', { name: 'Back to search' }));
    assert.equal(screen.getByLabelText('How can I help you?').value, 'I need to find a nursing service in 800001');
    assert.equal(screen.queryByRole('heading', { name: 'Search results' }), null);
    await user.click(screen.getByRole('button', { name: 'Send ↑' }));
    await screen.findByRole('heading', { name: 'Search results' });
    await user.click(screen.getByRole('button', { name: 'CareLens — start a new search' }));
    assert.equal(screen.getByLabelText('How can I help you?').value, 'I need to find a nursing service in 800001');
    cleanup();
    const { default: FacilityMap } = await server.ssrLoadModule('/src/components/FacilityMap.jsx');
    let selected = null;
    const facility = { id: 'live', name: 'Hyderabad Clinic', coordinates: { latitude: 17.44, longitude: 78.49 } };
    const props = { facilities: [facility], queryLocation: { latitude: 17.43, longitude: 78.48, label: 'Hyderabad' }, selectedId: 'live', onSelect: f => { selected = f; }, illustrative: false, status: 'success' };
    const live = render(React.createElement(FacilityMap, props));
    assert.ok(screen.getByRole('region', { name: 'Healthcare facility map of India' }));
    assert.ok(document.querySelector('img.leaflet-tile').src.includes('tile.openstreetmap.org'));
    const marker = screen.getByRole('button', { name: 'Open Hyderabad Clinic' });
    assert.ok(marker.classList.contains('is-selected'));
    await user.click(marker);
    assert.equal(selected.id, 'live');
    live.rerender(React.createElement(FacilityMap, { ...props, facilities: [{ id: 'missing', name: 'Unknown' }], queryLocation: null }));
    assert.equal(screen.queryByRole('button', { name: 'Open Hyderabad Clinic' }), null);
    assert.ok(screen.getByText('1 facilities have no map coordinates.'));
  } finally { cleanup(); await server.close(); dom.window.close(); }
});

test('live search ranks Fit Scores and shows the scoring breakdown', async () => {
  const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'http://localhost', pretendToBeVisual: true });
  for (const key of ['window', 'document', 'navigator', 'HTMLElement', 'Element', 'Node', 'MutationObserver']) {
    Object.defineProperty(globalThis, key, { configurable: true, value: dom.window[key] });
  }
  globalThis.getComputedStyle = dom.window.getComputedStyle;
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  globalThis.ResizeObserver = class { observe() {} disconnect() {} };
  const previousFetch = globalThis.fetch;
  const websiteCalls = [];
  globalThis.fetch = async (url, options) => {
    if (url === '/api/nabh/verify') return {ok: true, json: async () => ({status: 'unverified'})};
    if (url === '/api/website/verify') {
      const { facilityId, websiteIndex } = JSON.parse(options.body);
      assert.equal(facilityId, 'best');
      assert.ok([0, 1].includes(websiteIndex));
      websiteCalls.push(websiteIndex);
      return {ok: true, json: async () => websiteIndex === 0
        ? {status: 'verified', reason: 'The link opens successfully.', evidenceUrl: 'https://hospital.example.com/contact', urlDomainVerifiedRatio: null}
        : {status: 'unavailable', reason: 'The page could not be reached.', evidenceUrl: null, urlDomainVerifiedRatio: 0.5}};
    }
    assert.equal(JSON.parse(options.body).query, 'dialysis in Lucknow');
    return {ok: true, json: async () => ({facilities: [
      {id: 'near', name: 'Nearby Hospital', fitScore: 10, distanceKm: 1},
      {id: 'best', name: 'Best Match Hospital', fitScore: 20, distanceKm: 5,
       websiteUrls: ['https://hospital.example.com/', 'https://directory.example.org/listing'],
       serviceMatch: 'text_match', scoreBreakdown: {authority: 0.2, addressPostcodeCoordinatesMismatch: true, urlDomainVerifiedRatio: null, authoritySource: 'synthetic',
       specialtyScore: 10, serviceScore: 6, rawScore: 16, maxRawScore: 16, matchScore100: 100,
       specialties: [{input: 'nephrology', matched: true}], services: [{input: 'dialysis', score: 6}]}}
    ]})};
  };
  const { render, within, cleanup, waitFor } = await import('@testing-library/react');
  const screen = within(dom.window.document.body);
  const { default: userEvent } = await import('@testing-library/user-event');
  const server = await createServer({
    define: { 'import.meta.env.VITE_FACILITIES_API_URL': JSON.stringify('/api/search') },
    server: { middlewareMode: true, ws: false }, appType: 'custom',
  });
  try {
    const { default: App } = await server.ssrLoadModule('/src/App.jsx');
    const user = userEvent.setup({ document: dom.window.document });
    render(React.createElement(App));
    await user.type(screen.getByLabelText('How can I help you?'), 'dialysis in Lucknow');
    await user.click(screen.getByRole('button', {name: 'Send ↑'}));
    await screen.findByText('2 facilities');
    assert.match(screen.getAllByRole('button', {name: /fit score/})[0].textContent, /1\. Best Match/);
    await user.click(screen.getByRole('button', {name: /Best Match Hospital, fit score/}));
    assert.ok(screen.getByText(/Authority: 0.20/));
    assert.ok(screen.getByText('dialysis: 6/6'));
    assert.ok(screen.getByText(/Address, postcode and coordinates mismatch/));
    assert.ok(screen.getByText(/simulated flags/));
    assert.ok(screen.getByRole('region', {name: 'Score calculation'}));
    assert.ok(screen.getByRole('region', {name: 'Facility details'}));
    assert.ok(screen.getByRole('region', {name: 'NABH accreditation'}));
    const websites = within(screen.getByRole('region', {name: 'Website verification'}));
    assert.ok(await websites.findByText('Verified'));
    assert.equal(websites.getByRole('link', {name: /Open checked destination/}).getAttribute('href'), 'https://hospital.example.com/contact');
    await waitFor(() => assert.deepEqual(websiteCalls, [0, 1]));
    assert.ok(await screen.findByText('URL domain verification · 50%'));
    assert.equal(websites.queryByRole('button'), null);
    await user.click(websites.getByText('More dataset links (1)'));
    assert.ok(await websites.findByText('Unable to verify'));
    assert.equal(websites.getByRole('link', {name: /directory\.example\.org\/listing/}).getAttribute('href'), 'https://directory.example.org/listing');
    await user.click(dom.window.document.querySelector('.drawer-backdrop'));
    assert.equal(screen.queryByRole('dialog'), null);
    await user.selectOptions(screen.getByLabelText('Sort by'), 'distance');
    assert.match(screen.getAllByRole('button', {name: /fit score/})[0].textContent, /1\. Nearby Hospital/);
  } finally {
    cleanup(); await server.close(); globalThis.fetch = previousFetch; dom.window.close();
  }
});

test('agent clarification preserves the query and lets the user refine and resubmit', async () => {
  const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'http://localhost', pretendToBeVisual: true });
  for (const key of ['window', 'document', 'navigator', 'HTMLElement', 'Element', 'Node', 'MutationObserver']) {
    Object.defineProperty(globalThis, key, { configurable: true, value: dom.window[key] });
  }
  globalThis.getComputedStyle = dom.window.getComputedStyle;
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  globalThis.ResizeObserver = class { observe() {} disconnect() {} };
  const previousFetch = globalThis.fetch;
  const queries = [];
  globalThis.fetch = async (url, options) => {
    if (url === '/api/nabh/verify') return {ok: true, json: async () => ({status: 'unverified'})};
    queries.push(JSON.parse(options.body).query);
    return queries.length === 1
      ? {ok: false, status: 422, json: async () => ({error: {code: 'location_required',
          message: 'A city or explicit postcode is required.',
          clarification_question: 'Which city or postcode should I search in?'}})}
      : {ok: true, json: async () => ({facilities: [{id: 'match', name: 'Lucknow Hospital', fitScore: 70}]})};
  };
  const { render, within, cleanup } = await import('@testing-library/react');
  const screen = within(dom.window.document.body);
  const { default: userEvent } = await import('@testing-library/user-event');
  const server = await createServer({
    define: { 'import.meta.env.VITE_FACILITIES_API_URL': JSON.stringify('/api/search') },
    server: { middlewareMode: true, ws: false }, appType: 'custom',
  });
  try {
    const { default: App } = await server.ssrLoadModule('/src/App.jsx');
    const user = userEvent.setup({ document: dom.window.document });
    render(React.createElement(App));
    await user.type(screen.getByLabelText('How can I help you?'), 'I need dialysis near me');
    await user.click(screen.getByRole('button', {name: 'Send ↑'}));
    await screen.findByText('Which city or postcode should I search in?');
    assert.equal(screen.getByLabelText('How can I help you?').value, 'I need dialysis near me');
    assert.equal(screen.queryByText('No matching facilities'), null);
    await user.clear(screen.getByLabelText('How can I help you?'));
    await user.type(screen.getByLabelText('How can I help you?'), 'I need dialysis in Lucknow');
    await user.click(screen.getByRole('button', {name: 'Send ↑'}));
    await screen.findByText('1 facility');
    assert.deepEqual(queries, ['I need dialysis near me', 'I need dialysis in Lucknow']);
    assert.ok(screen.getByRole('button', {name: /Lucknow Hospital, fit score/}));
  } finally {
    cleanup(); await server.close(); globalThis.fetch = previousFetch; dom.window.close();
  }
});
