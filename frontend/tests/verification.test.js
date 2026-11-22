import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import { createServer } from 'vite';
import React from 'react';

test('facility details verify on demand, prevent duplicates, link PDFs only on success, and retry failures', async () => {
  const dom = new JSDOM('<!doctype html><html><body></body></html>', {url: 'http://localhost', pretendToBeVisual: true});
  for (const key of ['window', 'document', 'navigator', 'HTMLElement', 'Element', 'Node', 'MutationObserver']) {
    Object.defineProperty(globalThis, key, {configurable: true, value: dom.window[key]});
  }
  globalThis.getComputedStyle = dom.window.getComputedStyle;
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  const previousFetch = globalThis.fetch;
  let finish;
  const calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push({url, options});
    return new Promise(resolve => { finish = data => resolve({ok: true, json: async () => data}); });
  };
  const {render, within, cleanup, act} = await import('@testing-library/react');
  const {default: userEvent} = await import('@testing-library/user-event');
  const screen = within(dom.window.document.body);
  const server = await createServer({server: {middlewareMode: true, ws: false}, appType: 'custom'});
  try {
    const {default: DetailDrawer} = await server.ssrLoadModule('/src/components/DetailDrawer.jsx');
    const user = userEvent.setup({document: dom.window.document});
    const view = render(React.createElement(DetailDrawer, {facility: {id: 'live-1', name: 'Example Hospital', area: 'Pune', postalCode: '412105'}, onClose: () => {}, illustrative: false}));
    assert.equal(calls.length, 0);
    await user.click(screen.getByRole('button', {name: 'NABH certification verify'}));
    assert.equal(calls.length, 1);
    assert.equal(calls[0].url, '/api/nabh/verify');
    assert.deepEqual(JSON.parse(calls[0].options.body), {facilityId: 'live-1'});
    assert.equal(screen.getByRole('button', {name: 'Verifying NABH certification…'}).disabled, true);
    await act(async () => finish({status: 'verified', certificateUrls: ['https://portal.nabh.co/cert.pdf'], reason: 'Branch matched.'}));
    assert.ok(screen.getByText('successfully verified!'));
    assert.equal(screen.getByRole('link', {name: /View certificate PDF/}).href, 'https://portal.nabh.co/cert.pdf');
    await user.click(screen.getByRole('button', {name: 'NABH certification verify'}));
    assert.equal(screen.queryByRole('link', {name: /View certificate PDF/}), null);
    await act(async () => finish({status: 'unverified', certificateUrls: ['https://portal.nabh.co/unverified.pdf'], reason: 'No trustworthy certificate.'}));
    assert.ok(screen.getByText("can't be verified"));
    assert.equal(screen.queryByRole('link', {name: /View certificate PDF/}), null);
    await user.click(screen.getByRole('button', {name: 'NABH certification verify'}));
    await act(async () => finish({status: 'verified', certificateUrls: ['javascript:alert(1)']}));
    assert.ok(screen.getByText("can't be verified"));
    assert.equal(screen.queryByRole('link', {name: /View certificate PDF/}), null);
    await user.click(screen.getByRole('button', {name: 'NABH certification verify'}));
    view.unmount();
    assert.equal(calls.at(-1).options.signal.aborted, true);
  } finally {
    cleanup(); await server.close(); globalThis.fetch = previousFetch; dom.window.close();
  }
});
