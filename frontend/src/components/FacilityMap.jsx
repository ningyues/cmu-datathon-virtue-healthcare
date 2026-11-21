import { useEffect, useRef, useState } from 'react';

function LocationPlot({ facilities, origin, radiusKm, selectedId, onSelect }) {
  const kmPerDegree = 111.2;
  const kmPerLongitude = kmPerDegree * Math.cos(origin.latitude * Math.PI / 180);
  const points = facilities.filter((facility) => facility.coordinates).map((facility) => ({
    facility,
    east: (facility.coordinates.longitude - origin.longitude) * kmPerLongitude,
    north: (facility.coordinates.latitude - origin.latitude) * kmPerDegree,
  }));
  const extent = Math.max(radiusKm ?? 0, 1, ...points.map(({ east, north }) => Math.max(Math.abs(east), Math.abs(north))));

  return <>
    <h2 className="map-caption-top">Facility locations</h2>
    <div className="location-plot">
      <span className="plot-origin" role="img" aria-label="Search origin" title={origin.label ?? 'Search origin'} />
      {points.map(({ facility, east, north }) => (
        <button key={facility.id} type="button" className={`plot-marker ${selectedId === facility.id ? 'is-selected' : ''}`}
          style={{ left: `${50 + east / extent * 44}%`, top: `${50 - north / extent * 44}%` }}
          onClick={() => onSelect(facility)} aria-label={`Open ${facility.name}`} title={facility.name}
          tabIndex={selectedId === facility.id ? 0 : -1} />
      ))}
    </div>
    <p className="map-caption-bottom">Gold dot marks the search origin · Coordinates only</p>
  </>;
}

export default function FacilityMap({ facilities, queryLocation, radiusKm, selectedId, onSelect, illustrative, hasDetail }) {
  const container = useRef(null);
  const [scale, setScale] = useState(1);
  useEffect(() => {
    if (!illustrative) return;
    const observer = new ResizeObserver(([entry]) => setScale(entry.contentRect.width / 708));
    if (container.current) observer.observe(container.current);
    return () => observer.disconnect();
  }, [illustrative]);
  const label = illustrative ? 'Illustrative facility map, not for navigation'
    : queryLocation ? 'Facility locations relative to the search origin' : 'Map unavailable';
  return (
    <section ref={container} className="facility-map" aria-label={label}>
      {illustrative ? <div className="map-canvas" style={{ transform: `scale(${scale})` }}>
        <img className="map-artwork" src={`${import.meta.env.BASE_URL}assets/map.svg`} alt="" />
        {hasDetail && <><p className="map-caption-top">Example locations only</p><p className="map-caption-bottom">Illustrative map · Not for navigation</p></>}
        {facilities.filter((facility) => facility.marker).map((facility) => (
          <button type="button" key={facility.id} className={`map-marker ${selectedId === facility.id ? 'is-selected' : ''}`} style={{ left: facility.marker.x, top: facility.marker.y }} onClick={() => onSelect(facility)} aria-label={`Open ${facility.name}`}>
            {facility.marker.label}
          </button>
        ))}
      </div> : queryLocation
        ? <LocationPlot facilities={facilities} origin={queryLocation} radiusKm={radiusKm} selectedId={selectedId} onSelect={onSelect} />
        : <div className="map-unavailable"><h2>Map unavailable</h2><p>Search location will appear here.</p></div>}
    </section>
  );
}
