import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import { createServer } from 'vite';
import React from 'react';

test('radius slider reuses intent, commits on release or keyboard, and retries the selected range', async () => {
  const dom = new JSDOM('<html><body></body></html>', {url: 'http://localhost', pretendToBeVisual: true});
  for (const key of ['window', 'document', 'navigator', 'HTMLElement', 'HTMLLabelElement', 'Element', 'Node', 'MutationObserver']) {
    Object.defineProperty(globalThis, key, {configurable: true, value: dom.window[key]});
  }
  globalThis.getComputedStyle = dom.window.getComputedStyle;
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  globalThis.ResizeObserver = class { observe() {} disconnect() {} };
  const previousFetch = globalThis.fetch;
  const requests = [];
  const intent = {location: {city: 'Lucknow', postcode: null}, specialities: ['nephrology'], service: ['dialysis'], range: 30};
  globalThis.fetch = async (url, options) => {
    if (url === '/api/nabh/verify') return {ok: true, json: async () => ({status: 'unverified'})};
    const payload = JSON.parse(options.body);
    requests.push(payload);
    if (requests.length === 2) return {ok: false, status: 503, json: async () => ({error: 'Search temporarily unavailable.'})};
    const radius = payload.intent?.range ?? 30;
    return {ok: true, json: async () => ({intent: {...intent, range: radius}, radiusKm: radius,
      facilities: [{id: 'near', name: 'Nearby Hospital', distanceKm: 1, fitScore: 70},
        ...(radius >= 20 ? [{id: 'far', name: 'Farther Hospital', distanceKm: 15, fitScore: 60}] : [])]})};
  };
  const {render, within, cleanup, fireEvent} = await import('@testing-library/react');
  const {default: userEvent} = await import('@testing-library/user-event');
  const screen = within(dom.window.document.body);
  const server = await createServer({define: {'import.meta.env.VITE_FACILITIES_API_URL': JSON.stringify('/api/search')},
    server: {middlewareMode: true, ws: false}, appType: 'custom'});
  try {
    const {default: App} = await server.ssrLoadModule('/src/App.jsx');
    const user = userEvent.setup({document: dom.window.document});
    render(React.createElement(App));
    await user.type(screen.getByLabelText('How can I help you?'), 'dialysis in Lucknow');
    await user.click(screen.getByRole('button', {name: 'Send ↑'}));
    await screen.findByText('2 facilities');
    const slider = screen.getByRole('slider', {name: 'Search radius'});
    assert.equal(slider.value, '30');
    for (const value of ['25', '10', '5']) fireEvent.change(slider, {target: {value}});
    assert.equal(requests.length, 1);
    assert.ok(screen.getByText('5 km'));
    fireEvent.pointerUp(slider);
    await screen.findByText('Search temporarily unavailable.');
    assert.deepEqual(requests[1], {intent: {...intent, range: 5}});
    assert.equal(screen.getByRole('slider', {name: 'Search radius'}).value, '5');
    await user.click(screen.getByRole('button', {name: 'Try again'}));
    await screen.findByText('1 facility');
    assert.deepEqual(requests[2], requests[1]);
    fireEvent.change(slider, {target: {value: '20'}});
    fireEvent.keyUp(slider, {key: 'ArrowRight'});
    await screen.findByText('2 facilities');
    assert.deepEqual(requests[3], {intent: {...intent, range: 20}});
    fireEvent.blur(slider);
    assert.equal(requests.length, 4);
    await user.click(screen.getByRole('button', {name: 'Back to search'}));
    assert.equal(screen.getByLabelText('How can I help you?').value, 'dialysis in Lucknow');
  } finally {
    cleanup(); await server.close(); globalThis.fetch = previousFetch; dom.window.close();
  }
});
