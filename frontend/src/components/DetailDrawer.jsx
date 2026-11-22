import { useEffect, useRef, useState } from 'react';
import NabhVerification from './NabhVerification.jsx';
import { distanceLabel, facilityScore } from '../data/facilities.js';

export default function DetailDrawer({ facility, onClose, illustrative, scoreKind }) {
  const panel = useRef(null);
  const closeButton = useRef(null);
  const [expanded, setExpanded] = useState(false);
  const score = facilityScore(facility, scoreKind);
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
        <div className="trust-display"><h3>{score.label}</h3><strong className={score.missing ? 'score-unavailable' : ''}>{score.text}</strong></div>
        {facility.scoreBreakdown && <div className="score-breakdown" aria-label="Fit Score breakdown">
          <p>Authority: {facility.scoreBreakdown.authority.toFixed(2)}</p>
          <p>Specialty match: {facility.scoreBreakdown.specialtyScore}/10</p>
          <p>Services: {facility.scoreBreakdown.serviceScore} points</p>
          <ul>{facility.scoreBreakdown.services.map(service => <li key={service.input}>{service.input}: {service.score}/6</li>)}</ul>
          <p>Match: {facility.scoreBreakdown.rawScore}/{facility.scoreBreakdown.maxRawScore} = {facility.scoreBreakdown.matchScore100.toFixed(2)}%</p>
          <p>Fit Score = authority × match percentage.</p>
          <p>Text matching does not verify current service availability.</p>
        </div>}
        <div className="hospital-information">
          {facility.address && <p>{facility.address}</p>}
          <p>{facility.area}{facility.postalCode && ` · ${facility.postalCode}`}</p>
          <p>{distanceLabel(facility)}</p>
          <p>{[facility.type, facility.operatorType].filter(Boolean).join(' · ')}</p>
          {facility.website && <a href={facility.website} target="_blank" rel="noopener noreferrer">Website listed in dataset ↗</a>}
        </div>
        <NabhVerification key={facility.id} facility={facility} illustrative={illustrative} />
        {illustrative && <div className="score-breakdown">
          {['Data completeness', 'Verification', 'Consistency'].map((label) => <div className="breakdown-row" key={label}><h3>{label}</h3><div className="unmeasured-track" aria-hidden="true" /><p>Proposed category · Not quantified</p></div>)}
        </div>}
        {expanded && <p className="evidence-note" id="evidence-note">{illustrative
          ? 'Illustrative data from the design. Supporting source records and a scoring methodology have not been supplied.'
          : facility.serviceEvidence
            ? <>Dataset claim ({facility.serviceEvidence.field}) · {facility.serviceEvidence.text}. Service availability is unverified.</>
            : 'No dataset service claim was supplied for this facility.'}</p>}
        <button className="primary-button detail-action" type="button" onClick={() => setExpanded(!expanded)} aria-expanded={expanded} aria-controls="evidence-note">{expanded ? 'Hide details ↑' : 'View details →'}</button>
      </section>
    </>
  );
}
