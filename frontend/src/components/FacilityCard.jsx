import { distanceLabel, facilityScore } from '../data/facilities.js';

export default function FacilityCard({ facility, rank, selected, onSelect, scoreKind, hasNabhCertificate }) {
  const score = facilityScore(facility, scoreKind);
  return (
    <button type="button" className={`facility-card ${selected ? 'is-selected' : ''}`} onClick={() => onSelect(facility)} aria-label={`${facility.name}, ${score.label.toLowerCase()} ${score.text}, ${distanceLabel(facility)}${hasNabhCertificate ? ', verified NABH certificate' : ''}. Open details.`}>
      <span className="facility-info">
        <span className="facility-name">
          <span className="facility-rank">
            {(facility.featured || hasNabhCertificate) && <span className="featured-star" aria-hidden="true" title={hasNabhCertificate ? 'Verified NABH certificate' : undefined}>🌟</span>}{rank}.
          </span>{' '}{facility.name}
        </span>
        <span className="facility-meta">{facility.type} · <strong>{distanceLabel(facility)}</strong><br />{facility.area}{facility.postalCode && ` · ${facility.postalCode}`}</span>
      </span>
      <span className="card-score"><strong className={score.missing ? 'score-unavailable' : ''}>{score.text}</strong><small>{score.label}</small></span>
      <span className="card-chevron" aria-hidden="true">›</span>
    </button>
  );
}
