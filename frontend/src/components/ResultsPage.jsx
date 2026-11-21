import { useCallback, useMemo, useRef, useEffect, useState } from 'react';
import Navigation from './Navigation.jsx';
import FacilityCard from './FacilityCard.jsx';
import FacilityMap from './FacilityMap.jsx';
import DetailDrawer from './DetailDrawer.jsx';
import { sortFacilities } from '../data/facilities.js';

export default function ResultsPage({ facilities, illustrative, status, error, onHome, onRetry }) {
  const [sortBy, setSortBy] = useState('trust');
  const [activeId, setActiveId] = useState(null);
  const [detail, setDetail] = useState(null);
  const heading = useRef(null);
  const sorted = useMemo(() => sortFacilities(facilities, sortBy), [facilities, sortBy]);
  useEffect(() => { heading.current?.focus(); }, []);
  const closeDetail = useCallback(() => setDetail(null), []);
  const selectFacility = (facility) => { setActiveId(facility.id); setDetail(facility); };
  const selectedId = activeId ?? facilities[0]?.id;

  return (
    <div className="results-page">
      <div className="results-layout">
        <div inert={detail ? true : undefined}><Navigation onHome={onHome} /></div>
        <main className="results-main">
          <div className="results-grid" inert={detail ? true : undefined}>
            <section className="results-list-panel" aria-label="Healthcare facilities">
              <div className="results-toolbar">
                <div><h1 ref={heading} tabIndex={-1}>Search results</h1><p className="result-count" aria-live="polite">{status === 'loading' ? 'Finding facilities…' : `${facilities.length} ${facilities.length === 1 ? 'facility' : 'facilities'}${illustrative ? ' · Illustrative data' : ''}`}</p></div>
                <label className="sort-control">Sort by<select value={sortBy} onChange={(event) => setSortBy(event.target.value)} disabled={status !== 'success' || facilities.length === 0}><option value="trust">Highest trust score</option><option value="distance">Nearest distance</option></select></label>
              </div>
              <div className="facility-list" aria-busy={status === 'loading'}>
                {status === 'loading' && <div className="state-card" role="status"><h2>Finding facilities…</h2><p>Please wait while information is retrieved.</p><div className="loading-line" /></div>}
                {status === 'error' && <div className="state-card" role="alert"><h2>Unable to load results</h2><p>{error || 'Try another service or enter your location manually.'}</p><button className="primary-button" type="button" onClick={onRetry}>Try again</button></div>}
                {status === 'success' && sorted.length === 0 && <div className="state-card"><h2>No matching facilities</h2><p>Try another service or enter your location manually.</p><button type="button" className="primary-button" onClick={onHome}>New search</button></div>}
                {status === 'success' && sorted.map((facility, index) => <FacilityCard key={facility.id} facility={facility} rank={index + 1} selected={selectedId === facility.id} onSelect={selectFacility} />)}
              </div>
            </section>
            <div className="map-column"><FacilityMap facilities={facilities} selectedId={selectedId} onSelect={selectFacility} illustrative={illustrative} hasDetail={Boolean(detail)} /></div>
          </div>
          {detail && <DetailDrawer key={detail.id} facility={detail} onClose={closeDetail} illustrative={illustrative} />}
        </main>
      </div>
    </div>
  );
}
