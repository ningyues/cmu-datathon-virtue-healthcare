import { useEffect, useRef, useState } from 'react';
import NabhVerification from './NabhVerification.jsx';
import WebsiteVerification from './WebsiteVerification.jsx';
import { distanceLabel, facilityScore } from '../data/facilities.js';

const urlRatioFormat = new Intl.NumberFormat('en', { style: 'percent', maximumFractionDigits: 1 });

function ScoreCalculation({ breakdown, websiteRatio, hasWebsiteLinks }) {
  const urlRatioLabel = websiteRatio == null
    ? (hasWebsiteLinks ? 'Pending' : 'No listed URLs')
    : urlRatioFormat.format(websiteRatio);
  return <section className="detail-section score-breakdown" aria-labelledby="score-calculation-heading">
    <h3 id="score-calculation-heading">Score calculation</h3>
    <p className="score-formula">Fit Score = authority × match percentage</p>
    <div className="score-grid">
      <div className="score-subsection">
        <h4>Authority</h4>
        <p className="score-metric">Authority: {breakdown.authority.toFixed(2)}</p>
        <div className="authority-reasons" aria-label="Authority score explanation">
          <p>URL domain verification · {urlRatioLabel}</p>
          {breakdown.addressPostcodeCoordinatesMismatch && <p className="authority-warning">Address, postcode and coordinates mismatch (−0.30)</p>}
          {breakdown.authoritySource === 'synthetic' && <p className="detail-note">The imported Authority score starts from simulated flags.</p>}
        </div>
      </div>
      <div className="score-subsection">
        <h4>Match percentage</h4>
        <p className="score-metric">{breakdown.matchScore100.toFixed(2)}%</p>
        <dl className="detail-values score-values">
          <div><dt>Specialty match</dt><dd>{breakdown.specialtyScore}/10</dd></div>
          <div><dt>Service points</dt><dd>{breakdown.serviceScore}</dd></div>
          <div><dt>Total points</dt><dd>{breakdown.rawScore}/{breakdown.maxRawScore}</dd></div>
        </dl>
      </div>
    </div>
    {breakdown.services.length > 0 && <div className="score-subsection service-points">
      <h4>Service points</h4>
      <ul className="service-scores">{breakdown.services.map(service => <li key={service.input}>
        <strong>{service.input}: {service.score}/6</strong>
        {service.matches && <span className="detail-note">{['procedure', 'equipment', 'capability']
          .filter(field => typeof service.matches[field] === 'boolean')
          .map(field => `${field} ${service.matches[field] ? '+2' : '+0'}`).join(' · ')}</span>}
      </li>)}</ul>
    </div>}
    <p className="detail-note">Service availability is unverified.</p>
  </section>;
}

export default function DetailDrawer({ facility, onClose, illustrative, scoreKind, nabhResult }) {
  const panel = useRef(null);
  const closeButton = useRef(null);
  const score = facilityScore(facility, scoreKind);
  const [websiteRatio, setWebsiteRatio] = useState(facility.scoreBreakdown?.urlDomainVerifiedRatio ?? null);
  const hasNabhCertificate = nabhResult?.status === 'verified';
  useEffect(() => {
    const previousFocus = document.activeElement;
    closeButton.current?.focus();
    function handleKey(event) {
      if (event.key === 'Escape') onClose();
      if (event.key === 'Tab') {
        const candidates = panel.current?.querySelectorAll('button:not([disabled]), a[href], input, summary, [tabindex="0"]');
        const focusable = Array.from(candidates ?? []).filter(element => {
          const collapsed = element.closest('details:not([open])');
          return !collapsed || element === collapsed.querySelector('summary');
        });
        if (!focusable.length) return;
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
      <button className="drawer-backdrop" type="button" onClick={onClose} tabIndex={-1} aria-hidden="true" />
      <section ref={panel} className="detail-drawer" role="dialog" aria-modal="true" aria-labelledby="detail-name">
        <div className="drawer-heading">
          <h2 id="detail-name">
            {(facility.featured || hasNabhCertificate) && <span className="featured-star" aria-hidden="true" title={hasNabhCertificate ? 'Verified NABH certificate' : undefined}>🌟</span>}{facility.name}
          </h2>
          <button ref={closeButton} type="button" className="close-button" onClick={onClose} aria-label="Close facility details">×</button>
        </div>
        <section className="trust-display" aria-label={score.label}><h3>{score.label}</h3><strong className={score.missing ? 'score-unavailable' : ''}>{score.text}</strong></section>
        {facility.scoreBreakdown && <ScoreCalculation breakdown={facility.scoreBreakdown}
          websiteRatio={websiteRatio} hasWebsiteLinks={Boolean(facility.websiteLinks?.length)} />}
        <section className="detail-section hospital-information" aria-labelledby="facility-details-heading">
          <h3 id="facility-details-heading">Facility details</h3>
          <dl className="detail-values">
            <div><dt>Address</dt><dd>{facility.address && <>{facility.address}<br /></>}{facility.area}{facility.postalCode && ` · ${facility.postalCode}`}</dd></div>
            <div><dt>Distance</dt><dd>{distanceLabel(facility)}</dd></div>
            <div><dt>Facility type</dt><dd>{[facility.type, facility.operatorType].filter(Boolean).join(' · ')}</dd></div>
          </dl>
          {facility.serviceEvidence && <p className="detail-note">Dataset service claim ({facility.serviceEvidence.field}) · {facility.serviceEvidence.text}</p>}
        </section>
        {!illustrative && <WebsiteVerification key={facility.id} facility={facility} onRatioChange={setWebsiteRatio} />}
        <section className="detail-section" aria-labelledby="nabh-heading">
          <h3 id="nabh-heading">NABH accreditation</h3>
          <NabhVerification illustrative={illustrative} result={nabhResult} />
        </section>
        {illustrative && <div className="detail-section score-breakdown">
          {['Data completeness', 'Verification', 'Consistency'].map((label) => <div className="breakdown-row" key={label}><h3>{label}</h3><div className="unmeasured-track" aria-hidden="true" /><p>Proposed category · Not quantified</p></div>)}
        </div>}

      </section>
    </>
  );
}
