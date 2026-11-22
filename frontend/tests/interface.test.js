import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import { createServer } from 'vite';
import React from 'react';

test('search validation, results, distance sorting, drawer keyboard controls, and return to search', async () => {
  const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'http://localhost', pretendToBeVisual: true });
  for (const key of ['window', 'document', 'navigator', 'HTMLElement', 'Element', 'Node', 'MutationObserver']) {
    Object.defineProperty(globalThis, key, { configurable: true, value: dom.window[key] });
  }
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
    await user.click(screen.getByRole('button', { name: 'View details →' }));
    assert.match(screen.getByText(/Illustrative data from the design/).textContent, /not been supplied/);
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
  globalThis.fetch = async (_url, options) => {
    assert.equal(JSON.parse(options.body).query, 'dialysis in Lucknow');
    return {ok: true, json: async () => ({facilities: [
      {id: 'near', name: 'Nearby Hospital', fitScore: 40, distanceKm: 1},
      {id: 'best', name: 'Best Match Hospital', fitScore: 70, distanceKm: 5,
       serviceMatch: 'text_match', scoreBreakdown: {authority: 0.7, authoritySource: 'synthetic',
       specialtyScore: 10, serviceScore: 6, rawScore: 16, maxRawScore: 16, matchScore100: 100,
       specialties: [{input: 'nephrology', matched: true}], services: [{input: 'dialysis', score: 6}]}}
    ]})};
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
    await user.type(screen.getByLabelText('How can I help you?'), 'dialysis in Lucknow');
    await user.click(screen.getByRole('button', {name: 'Send ↑'}));
    await screen.findByText('2 facilities');
    assert.match(screen.getAllByRole('button', {name: /fit score/})[0].textContent, /1\. Best Match/);
    await user.click(screen.getByRole('button', {name: /Best Match Hospital, fit score/}));
    assert.ok(screen.getByText(/Authority: 0.70/));
    assert.ok(screen.getByText('dialysis: 6/6'));
    assert.equal(screen.queryByText(/Simulated data/), null);
    await user.click(screen.getByRole('button', {name: 'Close facility details'}));
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
  globalThis.fetch = async (_url, options) => {
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
