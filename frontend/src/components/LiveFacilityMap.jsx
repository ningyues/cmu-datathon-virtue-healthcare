import { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
const validCoordinates = (lat, lon) => Number.isFinite(lat) && Math.abs(lat) <= 90 && Number.isFinite(lon) && Math.abs(lon) <= 180;

export default function LiveFacilityMap({ facilities, selectedId, onSelect, queryLocation: center, status }) {
  const container = useRef(null);
  const map = useRef(null);
  const markers = useRef(new Map());
  const select = useRef(onSelect);
  select.current = onSelect;
  const [tileError, setTileError] = useState(false);
  useEffect(() => {
    // Include the mainland and islands; constrain navigation to the India region.
    const indiaBounds = L.latLngBounds([6, 68], [37.5, 98]);
    const instance = L.map(container.current, {
      zoomSnap: 0.25,
      maxBounds: indiaBounds.pad(0.15),
      maxBoundsViscosity: 1,
    }).fitBounds(indiaBounds);
    const updateSize = () => {
      instance.invalidateSize();
      if (instance.getSize().x && instance.getSize().y) instance.setMinZoom(instance.getBoundsZoom(indiaBounds));
    };
    updateSize();
    map.current = instance;
    const tiles = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      noWrap: true,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(instance);
    tiles.on('tileerror', () => setTileError(true));
    tiles.on('tileload', () => setTileError(false));
    const observer = new ResizeObserver(updateSize);
    observer.observe(container.current);
    return () => { observer.disconnect(); instance.remove(); map.current = null; };
  }, []);
  useEffect(() => {
    const instance = map.current;
    const group = L.layerGroup().addTo(instance);
    markers.current.clear();
    const bounds = [];
    if (center) {
      const point = [center.latitude, center.longitude];
      bounds.push(point);
      const icon = L.divIcon({ className: 'search-origin', iconSize: [18, 18], iconAnchor: [9, 9] });
      const label = document.createElement('span');
      label.textContent = `Search location: ${center.label}`;
      L.marker(point, { icon, title: 'Search location' }).bindTooltip(label).addTo(group);
    }
    facilities.forEach((facility, index) => {
      if (!validCoordinates(facility.coordinates?.latitude, facility.coordinates?.longitude)) return;
      const point = [facility.coordinates?.latitude, facility.coordinates?.longitude];
      bounds.push(point);
      const icon = L.divIcon({ className: 'facility-pin', html: `<span>${index + 1}</span>`, iconSize: [38, 38], iconAnchor: [19, 19] });
      const label = document.createElement('span');
      label.textContent = facility.name;
      const marker = L.marker(point, { icon, keyboard: true })
        .bindTooltip(label, { offset: [19, 0], opacity: 1, className: 'facility-tooltip' })
        .addTo(group);
      marker.getElement().setAttribute('aria-label', `Open ${facility.name}`);
      marker.on('click', () => select.current(facility));
      markers.current.set(facility.id, marker);
    });
    if (bounds.length) instance.fitBounds(bounds, { padding: [40, 40], maxZoom: 14 });
    return () => group.remove();
  }, [facilities, center]);
  useEffect(() => {
    markers.current.forEach((marker, id) => {
      marker.getElement()?.classList.toggle('is-selected', id === selectedId);
      marker.setZIndexOffset(id === selectedId ? 1000 : 0);
    });
  }, [selectedId, facilities]);
  const missing = facilities.filter(f => !validCoordinates(f.coordinates?.latitude, f.coordinates?.longitude)).length;
  return <section className="facility-map" aria-label="Healthcare facility map of India">
    <div ref={container} className="live-map" />
    {(status === 'loading' || tileError || missing > 0) && <p className="map-notice" role="status">{status === 'loading' ? 'Finding your location…' : tileError ? 'Map tiles unavailable. Facility results remain available in the list.' : `${missing} facilities have no map coordinates.`}</p>}
  </section>;
}
