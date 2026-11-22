import { useEffect, useRef, useState } from 'react';

export default function RangeControl({ radiusKm, onRangeChange }) {
  const [draft, setDraft] = useState(radiusKm);
  const submitted = useRef(radiusKm);
  const max = Math.max(200, Math.ceil(radiusKm));
  const min = Math.min(1, radiusKm);
  useEffect(() => { setDraft(radiusKm); submitted.current = radiusKm; }, [radiusKm]);

  function commit(event) {
    const range = Number(event.currentTarget.value);
    if (range === submitted.current) return;
    submitted.current = range;
    onRangeChange?.(range);
  }

  return <div className="range-control">
    <div className="range-heading"><label htmlFor="search-range">Search radius</label><output htmlFor="search-range">{Number(draft.toFixed(2))} km</output></div>
    <input id="search-range" type="range" min={min} max={max} step="any" value={draft}
      aria-valuetext={`${Number(draft.toFixed(2))} kilometers`} aria-describedby="range-hint"
      onChange={event => setDraft(Number(event.target.value))}
      onPointerUp={commit} onBlur={commit}
      onKeyUp={event => { if (['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End', 'PageUp', 'PageDown'].includes(event.key)) commit(event); }} />
    <div className="range-limits" aria-hidden="true"><span>{min} km</span><span>{max} km</span></div>
    <p id="range-hint">Release the slider to update nearby facilities.</p>
  </div>;
}
