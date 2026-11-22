import { useCallback, useMemo, useRef, useEffect, useState } from 'react';
import RangeControl from './RangeControl.jsx';
import Navigation from './Navigation.jsx';
import FacilityCard from './FacilityCard.jsx';
import FacilityMap from './FacilityMap.jsx';
import DetailDrawer from './DetailDrawer.jsx';
import { sortFacilities } from '../data/facilities.js';
import useVerificationQueue from '../hooks/useVerificationQueue.js';
import { getPractoRating, verifyCertification } from '../services/verification.js';

export default function ResultsPage({ facilities, illustrative, queryLocation, radiusKm, intent, status, error, onHome, onRetry, onRangeChange }) {
  const [showPagination, setShowPagination] = useState(false);
  const resultsGrid = useRef(null);
  const [page, setPage] = useState(1);
  const pageSize = 4;
  const [sortChoice, setSortChoice] = useState(null);
  const [activeId, setActiveId] = useState(null);
  const [detail, setDetail] = useState(null);
  const practoIds = useMemo(() => status === 'success' && !illustrative
    ? facilities.filter(facility => facility.hasPractoLink).map(facility => facility.id) : null,
  [facilities, illustrative, status]);
  const practoResults = useVerificationQueue(practoIds, getPractoRating, 2);
  const practoResult = facility => illustrative ? undefined : !facility.hasPractoLink
    ? {status: 'unavailable', reason: 'No Practo hospital or clinic link is present in the dataset.'}
    : practoResults.get(facility.id) ?? {status: 'loading'};
  const nabhIds = useMemo(() => status === 'success' && !illustrative
    ? facilities.map(facility => facility.id) : null, [facilities, illustrative, status]);
  const nabhResults = useVerificationQueue(nabhIds, verifyCertification, 2);
  const heading = useRef(null);
  const hasFitScores = facilities.some((facility) => facility.fitScore != null);
  const hasTrustScores = illustrative || facilities.some((facility) => facility.trustScore != null);
  const defaultSort = hasTrustScores && !hasFitScores ? 'trust' : 'fit';
  const sortBy = sortChoice ?? defaultSort;
  const scoreKind = sortBy === 'distance' ? defaultSort : sortBy;
  const sorted = useMemo(() => sortFacilities(facilities, sortBy), [facilities, sortBy]);
  const pageCount = Math.max(1, Math.ceil(sorted.length / pageSize));
  const currentPage = Math.min(page, pageCount);
  const offset = (currentPage - 1) * pageSize;
  const visible = sorted.slice(offset, offset + pageSize);
  const pageNumbers = [...new Set([1, currentPage - 1, currentPage, currentPage + 1, pageCount])]
    .filter(number => number >= 1 && number <= pageCount).sort((a, b) => a - b);
  useEffect(() => { setPage(1); setActiveId(null); setDetail(null); }, [facilities, sortBy]);
  useEffect(() => { heading.current?.focus(); }, []);
  useEffect(() => {
    setShowPagination(false);
    const updatePagination = () => {
      const bottom = resultsGrid.current?.getBoundingClientRect().bottom ?? Infinity;
      setShowPagination(window.scrollY > 0 && bottom <= window.innerHeight + 160);
    };
    window.addEventListener('scroll', updatePagination, { passive: true });
    window.addEventListener('resize', updatePagination);
    return () => {
      window.removeEventListener('scroll', updatePagination);
      window.removeEventListener('resize', updatePagination);
    };
  }, [facilities, sortBy, status]);
  const closeDetail = useCallback(() => setDetail(null), []);
  const selectFacility = (facility) => { setPage(Math.floor(sorted.findIndex(item => item.id === facility.id) / pageSize) + 1); setActiveId(facility.id); setDetail(facility); };
  const selectedId = activeId ?? visible[0]?.id;

  return (
    <div className="results-page">
      <div className="results-layout">
        <div inert={detail ? true : undefined}><Navigation onHome={onHome} /></div>
        <main className="results-main">
          <div ref={resultsGrid} className="results-grid" inert={detail ? true : undefined}>
            <section className="results-list-panel" aria-label="Healthcare facilities">
              <button className="back-to-search" type="button" onClick={onHome}>
                <span aria-hidden="true">←</span> Back to search
              </button>
              <div className="results-toolbar">
                <div>
                  <h1 ref={heading} tabIndex={-1}>Search results</h1>
                  <p className="result-count" aria-live="polite">{status === 'loading' ? 'Finding facilities…' : `${facilities.length} ${facilities.length === 1 ? 'facility' : 'facilities'}${illustrative ? ' · Illustrative data' : ''}`}</p>
                  {queryLocation?.label && <p className="result-count">{radiusKm ? `Within ${radiusKm.toFixed(1)} km of ` : ''}{queryLocation.label}</p>}
                  {!!nabhIds?.length && <p className="result-count">NABH checks · {nabhResults.size} of {nabhIds.length} complete</p>}
                </div>
                <label className="sort-control">Sort by<select value={sortBy} onChange={(event) => setSortChoice(event.target.value)} disabled={status !== 'success' || facilities.length === 0}>
                  {!illustrative && <option value="fit">{hasFitScores ? 'Highest Fit Score' : 'Best match'}</option>}
                  {hasTrustScores && <option value="trust">Highest trust score</option>}
                  <option value="distance">Nearest distance</option>
                </select></label>
              </div>
              {!illustrative && intent && <RangeControl radiusKm={radiusKm ?? intent.range} onRangeChange={onRangeChange} />}
              <div className="facility-list" aria-busy={status === 'loading'}>
                {status === 'loading' && <div className="state-card" role="status"><h2>Finding facilities…</h2><p>Please wait while information is retrieved.</p><div className="loading-line" /></div>}
                {status === 'error' && <div className="state-card" role="alert"><h2>Unable to load results</h2><p>{error || 'Try another service or enter your location manually.'}</p><button className="primary-button" type="button" onClick={onRetry}>Try again</button></div>}
                {status === 'success' && sorted.length === 0 && <div className="state-card"><h2>No matching facilities</h2><p>Try another service or enter your location manually.</p><button type="button" className="primary-button" onClick={onHome}>New search</button></div>}
                {status === 'success' && visible.map((facility, index) => <FacilityCard key={facility.id} facility={facility} rank={offset + index + 1} selected={selectedId === facility.id} onSelect={selectFacility} scoreKind={scoreKind} hasNabhCertificate={nabhResults.get(facility.id)?.status === 'verified'} practoResult={practoResult(facility)} />)}
              </div>
            </section>
            <div className={`map-column${status === 'success' && visible.length > 0 ? ' map-column-aligned' : ''}`}>
              <FacilityMap facilities={sorted} status={status} queryLocation={queryLocation} radiusKm={radiusKm} selectedId={selectedId} onSelect={selectFacility} illustrative={illustrative} hasDetail={Boolean(detail)} />
            </div>
          </div>
          {showPagination && status === 'success' && sorted.length > 0 && <nav className="results-pagination" aria-label="Results pages" inert={detail ? true : undefined}>
            <p aria-live="polite">Showing {offset + 1}–{Math.min(offset + pageSize, sorted.length)} of {sorted.length} facilities</p>
            <div className="pagination-buttons">
              <button type="button" disabled={currentPage === 1} onClick={() => { setPage(currentPage - 1); setActiveId(null); }}>← Previous</button>
              {pageNumbers.map((number, index) => <span className="pagination-item" key={number}>
                {index > 0 && number - pageNumbers[index - 1] > 1 && <span aria-hidden="true">…</span>}
                <button type="button" aria-label={`Page ${number}`} aria-current={number === currentPage ? 'page' : undefined} onClick={() => { setPage(number); setActiveId(null); }}>{number}</button>
              </span>)}
              <button type="button" disabled={currentPage === pageCount} onClick={() => { setPage(currentPage + 1); setActiveId(null); }}>Next →</button>
            </div>
          </nav>}
          {detail && <DetailDrawer key={detail.id} facility={detail} onClose={closeDetail} illustrative={illustrative} scoreKind={scoreKind} nabhResult={nabhResults.get(detail.id)} />}
        </main>
      </div>
    </div>
  );
}
