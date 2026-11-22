import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import { createServer } from 'vite';
import React from 'react';

test('search results automatically check NABH across pages and show each verified certificate', async () => {
  const dom = new JSDOM('<!doctype html><html><body></body></html>', {url: 'http://localhost', pretendToBeVisual: true});
  for (const key of ['window', 'document', 'navigator', 'HTMLElement', 'Element', 'Node', 'MutationObserver']) {
    Object.defineProperty(globalThis, key, {configurable: true, value: dom.window[key]});
  }
  globalThis.getComputedStyle = dom.window.getComputedStyle;
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  globalThis.ResizeObserver = class { observe() {} disconnect() {} };
  const previousFetch = globalThis.fetch;
  const calls = new Map();
  globalThis.fetch = async (url, options) => {
    assert.equal(url, '/api/nabh/verify');
    const {facilityId} = JSON.parse(options.body);
    assert.equal(calls.has(facilityId), false);
    return new Promise(resolve => {
      calls.set(facilityId, {
        signal: options.signal,
        finish: data => resolve({ok: true, json: async () => data}),
      });
    });
  };
  const {render, within, cleanup, act, waitFor} = await import('@testing-library/react');
  const {default: userEvent} = await import('@testing-library/user-event');
  const screen = within(dom.window.document.body);
  const server = await createServer({server: {middlewareMode: true, ws: false}, appType: 'custom'});
  try {
    const {default: ResultsPage} = await server.ssrLoadModule('/src/components/ResultsPage.jsx');
    const user = userEvent.setup({document: dom.window.document});
    const facilities = [
      {id: 'live-1', name: 'Example Hospital', fitScore: 6},
      {id: 'live-2', name: 'Another Hospital', fitScore: 5},
      ...[3, 4, 5, 6].map(number => ({id: `live-${number}`, name: `Hospital ${number}`, fitScore: 7 - number})),
    ];
    const view = render(React.createElement(React.StrictMode, null,
      React.createElement(ResultsPage, {facilities, illustrative: false, status: 'success'})));
    const card = () => screen.getByRole('button', {name: /Example Hospital, fit score/});
    const nabh = () => within(screen.getByRole('region', {name: 'NABH accreditation'}));
    const close = () => user.click(screen.getByRole('button', {name: 'Close facility details'}));
    await waitFor(() => assert.deepEqual([...calls.keys()], ['live-1', 'live-2']));
    assert.ok(screen.getByText('NABH checks · 0 of 6 complete'));

    await user.click(card());
    assert.ok(nabh().getByText(/Checking official NABH records/));
    assert.equal(nabh().queryByRole('button'), null);
    await close();
    assert.equal(calls.get('live-1').signal.aborted, false);

    await act(async () => calls.get('live-2').finish({status: 'verified', certificateUrls: ['javascript:alert(1)']}));
    await act(async () => calls.get('live-1').finish({status: 'verified', certificateUrls: ['https://portal.nabh.co/cert.pdf'], reason: 'Branch matched.'}));
    assert.deepEqual([...calls.keys()], ['live-1', 'live-2', 'live-3', 'live-4']);
    assert.ok(screen.getByText('NABH checks · 2 of 6 complete'));
    assert.match(card().getAttribute('aria-label'), /verified NABH certificate/);
    const cardStar = within(card()).getByTitle('Verified NABH certificate');
    assert.equal(cardStar.textContent, '🌟');
    assert.equal(cardStar.parentElement.textContent, '🌟1.');
    assert.match(cardStar.closest('.facility-name').textContent, /^🌟1\. Example Hospital$/);

    await user.click(card());
    assert.ok(nabh().getByText('Verified'));
    assert.equal(nabh().getByRole('link', {name: /View certificate PDF/}).href, 'https://portal.nabh.co/cert.pdf');
    assert.ok(nabh().getByLabelText('First page of the NABH certificate'));
    assert.ok(nabh().getByText('Certificate preview unavailable.'));
    const detailStar = within(screen.getByRole('dialog')).getByTitle('Verified NABH certificate');
    assert.equal(detailStar.textContent, '🌟');
    assert.equal(detailStar.nextSibling.textContent, 'Example Hospital');
    await close();
    const otherCard = screen.getByRole('button', {name: /Another Hospital, fit score/});
    assert.equal(within(otherCard).queryByTitle('Verified NABH certificate'), null);
    await user.click(otherCard);
    assert.ok(nabh().getByText('Unable to verify'));
    assert.equal(nabh().queryByRole('link', {name: /View certificate PDF/}), null);
    assert.equal(nabh().queryByLabelText('First page of the NABH certificate'), null);
    await close();

    await act(async () => {
      for (const id of ['live-3', 'live-4']) {
        calls.get(id).finish({status: 'unverified', reason: 'No trustworthy certificate.'});
      }
    });
    assert.deepEqual([...calls.keys()], ['live-1', 'live-2', 'live-3', 'live-4', 'live-5', 'live-6']);
    assert.equal(screen.queryByRole('button', {name: /Hospital 5, fit score/}), null);
    view.unmount();
    assert.equal(calls.get('live-5').signal.aborted, true);
    assert.equal(calls.get('live-6').signal.aborted, true);
  } finally {
    cleanup(); await server.close(); globalThis.fetch = previousFetch; dom.window.close();
  }
});
