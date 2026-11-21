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
  const server = await createServer({ server: { middlewareMode: true }, appType: 'custom' });
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
    await user.click(screen.getByRole('button', { name: 'CareLens — start a new search' }));
    assert.equal(screen.getByLabelText('How can I help you?').value, 'I need to find a nursing service in 800001');
  } finally { cleanup(); await server.close(); dom.window.close(); }
});
