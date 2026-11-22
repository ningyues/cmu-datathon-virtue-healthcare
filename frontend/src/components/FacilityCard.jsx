import { distanceLabel, facilityScore } from '../data/facilities.js';

export default function FacilityCard({ facility, rank, selected, onSelect, scoreKind }) {
  const score = facilityScore(facility, scoreKind);
  return (
    <button type="button" className={`facility-card ${selected ? 'is-selected' : ''}`} onClick={() => onSelect(facility)} aria-label={`${facility.name}, ${score.label.toLowerCase()} ${score.text}, ${distanceLabel(facility)}. Open details.`}>
      <span className="facility-info">
        <span className="facility-name">{rank}. {facility.name}{facility.featured && <span className="featured-star"> ★</span>}</span>
        <span className="facility-meta">{facility.type} · <strong>{distanceLabel(facility)}</strong><br />{facility.area}{facility.postalCode && ` · ${facility.postalCode}`}</span>
        {facility.serviceMatch && <span className="facility-meta">{facility.serviceMatch === 'listed_in_dataset' ? 'Dataset service claim' : facility.serviceMatch === 'text_match' ? 'Service text match' : 'Related specialty only'}</span>}
      </span>
      <span className="card-score"><strong className={score.missing ? 'score-unavailable' : ''}>{score.text}</strong><small>{score.label}</small></span>
      <span className="card-chevron" aria-hidden="true">›</span>
    </button>
  );
}
