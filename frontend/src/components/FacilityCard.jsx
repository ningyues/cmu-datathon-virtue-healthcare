import { distanceLabel, scoreLabel } from '../data/facilities.js';

export default function FacilityCard({ facility, rank, selected, onSelect }) {
  return (
    <button type="button" className={`facility-card ${selected ? 'is-selected' : ''}`} onClick={() => onSelect(facility)} aria-label={`${facility.name}, trust score ${scoreLabel(facility)}, ${distanceLabel(facility)}. Open details.`}>
      <span className="facility-info">
        <span className="facility-name">{rank}. {facility.name}{facility.featured && <span className="featured-star"> ★</span>}</span>
        <span className="facility-meta">{facility.type} · <strong>{distanceLabel(facility)}</strong><br />{facility.area}{facility.postalCode && ` · ${facility.postalCode}`}</span>
      </span>
      <span className="card-score"><strong className={facility.trustScore == null ? 'score-unavailable' : ''}>{scoreLabel(facility)}</strong><small>Trust score</small></span>
      <span className="card-chevron" aria-hidden="true">›</span>
    </button>
  );
}
