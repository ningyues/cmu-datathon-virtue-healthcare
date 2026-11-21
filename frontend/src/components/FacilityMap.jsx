import { useEffect, useRef, useState } from 'react';

export default function FacilityMap({ facilities, selectedId, onSelect, illustrative, hasDetail }) {
  const container = useRef(null);
  const [scale, setScale] = useState(1);
  useEffect(() => {
    const observer = new ResizeObserver(([entry]) => setScale(entry.contentRect.width / 708));
    if (container.current) observer.observe(container.current);
    return () => observer.disconnect();
  }, []);
  return (
    <section ref={container} className="facility-map" aria-label={illustrative ? 'Illustrative facility map, not for navigation' : 'Map unavailable'}>
      {illustrative ? <div className="map-canvas" style={{ transform: `scale(${scale})` }}>
        <img className="map-artwork" src={`${import.meta.env.BASE_URL}assets/map.svg`} alt="" />
        {hasDetail && <><p className="map-caption-top">Example locations only</p><p className="map-caption-bottom">Illustrative map · Not for navigation</p></>}
        {facilities.filter((facility) => facility.marker).map((facility) => (
          <button type="button" key={facility.id} className={`map-marker ${selectedId === facility.id ? 'is-selected' : ''}`} style={{ left: facility.marker.x, top: facility.marker.y }} onClick={() => onSelect(facility)} aria-label={`Open ${facility.name}`}>
            {facility.marker.label}
          </button>
        ))}
      </div> : <div className="map-unavailable"><h2>Map unavailable</h2><p>Live map locations are not connected yet.</p></div>}
    </section>
  );
}
