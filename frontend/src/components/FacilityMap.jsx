import { useEffect, useRef, useState } from 'react';
import LiveFacilityMap from './LiveFacilityMap.jsx';

function IllustrativeMap({ facilities, queryLocation, radiusKm, selectedId, onSelect, illustrative, hasDetail }) {
  const container = useRef(null);
  const [scale, setScale] = useState(1);
  useEffect(() => {
    if (!illustrative) return;
    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      setScale(Math.min(width / 708, height / 598));
    });
    if (container.current) observer.observe(container.current);
    return () => observer.disconnect();
  }, [illustrative]);
  const label = illustrative ? 'Illustrative facility map, not for navigation'
    : queryLocation ? 'Facility locations relative to the search origin' : 'Map unavailable';
  return (
    <section ref={container} className="facility-map" aria-label={label}>
      {illustrative ? <div className="map-canvas" style={{ transform: `translate(-50%, -50%) scale(${scale})` }}>
        <img className="map-artwork" src={`${import.meta.env.BASE_URL}assets/map.svg`} alt="" />
        {hasDetail && <><p className="map-caption-top">Example locations only</p><p className="map-caption-bottom">Illustrative map · Not for navigation</p></>}
        {facilities.filter((facility) => facility.marker).map((facility) => (
          <button type="button" key={facility.id} className={`map-marker ${selectedId === facility.id ? 'is-selected' : ''}`} style={{ left: facility.marker.x, top: facility.marker.y }} onClick={() => onSelect(facility)} aria-label={`Open ${facility.name}`}>
            {facility.marker.label}
            <span className="facility-tooltip map-marker-tooltip" aria-hidden="true">{facility.name}</span>
          </button>
        ))}
      </div> : null}
    </section>
  );
}

export default function FacilityMap(props) {
  return props.illustrative ? <IllustrativeMap {...props} /> : <LiveFacilityMap {...props} />;
}
