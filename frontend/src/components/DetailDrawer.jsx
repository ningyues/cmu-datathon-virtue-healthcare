import { useEffect, useRef, useState } from 'react';
import { distanceLabel, scoreLabel } from '../data/facilities.js';

export default function DetailDrawer({ facility, onClose, illustrative }) {
  const panel = useRef(null);
  const closeButton = useRef(null);
  const [expanded, setExpanded] = useState(false);
  useEffect(() => {
    const previousFocus = document.activeElement;
    closeButton.current?.focus();
    function handleKey(event) {
      if (event.key === 'Escape') onClose();
      if (event.key === 'Tab') {
        const focusable = panel.current?.querySelectorAll('button:not([disabled]), a[href], input, [tabindex="0"]');
        if (!focusable?.length) return;
        const first = focusable[0], last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    }
    document.addEventListener('keydown', handleKey);
    return () => { document.removeEventListener('keydown', handleKey); if (previousFocus?.isConnected) previousFocus.focus(); };
  }, [onClose]);

  return (
    <>
      <button className="map-dimmer" type="button" onClick={onClose} tabIndex={-1} aria-hidden="true" />
      <section ref={panel} className="detail-drawer" role="dialog" aria-modal="true" aria-labelledby="detail-name">
        <div className="drawer-heading"><h2 id="detail-name">{facility.name}{facility.featured && <span className="featured-star"> ★</span>}</h2><button ref={closeButton} type="button" className="close-button" onClick={onClose} aria-label="Close facility details">×</button></div>
        <div className="trust-display"><h3>Trust score</h3><strong className={facility.trustScore == null ? 'score-unavailable' : ''}>{scoreLabel(facility)}</strong></div>
        <div className="hospital-information"><p>{facility.area}</p><p>{facility.postalCode}</p><p>{distanceLabel(facility)}</p><p>{facility.type}</p></div>
        <div className="score-breakdown">
          {['Data completeness', 'Verification', 'Consistency'].map((label) => <div className="breakdown-row" key={label}><h3>{label}</h3><div className="unmeasured-track" aria-hidden="true" /><p>Proposed category · Not quantified</p></div>)}
        </div>
        {expanded && <p className="evidence-note" id="evidence-note">{illustrative ? 'Illustrative data from the design. Supporting source records and a scoring methodology have not been supplied.' : 'Supporting source records and a score breakdown were not provided with this result.'}</p>}
        <button className="primary-button detail-action" type="button" onClick={() => setExpanded(!expanded)} aria-expanded={expanded} aria-controls="evidence-note">{expanded ? 'Hide details ↑' : 'View details →'}</button>
      </section>
    </>
  );
}
