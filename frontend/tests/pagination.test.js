import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import { createServer } from 'vite';
import React from 'react';

test('four cards per page retain global ranks, sorting, and all map markers', async () => {
  const dom = new JSDOM('<html><body></body></html>', { url: 'http://localhost', pretendToBeVisual: true });
  for (const key of ['window', 'document', 'navigator', 'HTMLElement', 'HTMLLabelElement', 'Element', 'Node', 'MutationObserver']) {
    Object.defineProperty(globalThis, key, { configurable: true, value: dom.window[key] });
  }
  dom.window.scrollTo = () => {};
  globalThis.getComputedStyle = dom.window.getComputedStyle;
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  globalThis.ResizeObserver = class { observe() {} disconnect() {} };
  const { render, screen, cleanup, fireEvent } = await import('@testing-library/react');
  const { default: userEvent } = await import('@testing-library/user-event');
  const server = await createServer({ server: { middlewareMode: true, ws: false }, appType: 'custom' });
  try {
    const { default: ResultsPage } = await server.ssrLoadModule('/src/components/ResultsPage.jsx');
    const facilities = Array.from({ length: 9 }, (_, i) => ({ id: String(i), name: `Hospital ${i + 1}`, trustScore: 90 - i, distanceKm: 9 - i, marker: { x: i * 20, y: 30, label: String(i + 1) } }));
    const props = { facilities, illustrative: true, status: 'success', onHome() {}, onRetry() {} };
    const view = render(React.createElement(ResultsPage, props));
    const user = userEvent.setup({ document: dom.window.document });
    assert.equal(screen.getAllByRole('button', { name: /trust score/ }).length, 4);
    assert.equal(screen.getAllByRole('button', { name: /^Open Hospital/ }).length, 9);
    assert.equal(screen.queryByRole('navigation', { name: 'Results pages' }), null);
    Object.defineProperty(dom.window, 'scrollY', { configurable: true, value: 100 });
    fireEvent.scroll(dom.window);
    assert.ok(screen.getByRole('button', { name: '← Previous' }).disabled);
    await user.click(screen.getByRole('button', { name: 'Next →' }));
    assert.ok(screen.getByText('5. Hospital 5'));
    assert.ok(screen.getByText('Showing 5–8 of 9 facilities'));
    await user.click(screen.getByRole('button', { name: 'Next →' }));
    assert.equal(screen.getAllByRole('button', { name: /trust score/ }).length, 1);
    assert.ok(screen.getByRole('button', { name: 'Next →' }).disabled);
    await user.selectOptions(screen.getByLabelText('Sort by'), 'distance');
    assert.ok(screen.getByText('1. Hospital 9'));
    fireEvent.scroll(dom.window);
    assert.ok(screen.getByText('Showing 1–4 of 9 facilities'));
    await user.click(screen.getByRole('button', { name: 'Open Hospital 1' }));
    assert.ok(screen.getByRole('dialog', { name: 'Hospital 1' }));
    await user.click(screen.getByRole('button', { name: 'Close facility details' }));
    assert.ok(screen.getByText('9. Hospital 1'));
    view.rerender(React.createElement(ResultsPage, { ...props, facilities: facilities.slice(0, 2) }));
    fireEvent.scroll(dom.window);
    assert.ok(screen.getByText('Showing 1–2 of 2 facilities'));
    Object.defineProperty(dom.window, 'scrollY', { configurable: true, value: 0 });
    fireEvent.scroll(dom.window);
    assert.equal(screen.queryByRole('navigation', { name: 'Results pages' }), null);
    view.rerender(React.createElement(ResultsPage, { ...props, facilities: [] }));
    assert.equal(screen.queryByRole('navigation', { name: 'Results pages' }), null);
  } finally { cleanup(); await server.close(); dom.window.close(); }
});
