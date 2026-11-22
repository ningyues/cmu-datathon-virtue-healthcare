// Illustrative records transcribed from the Figma design. These are not verified providers.
export const sampleFacilities = [
  { id: 'ganga', name: 'Ganga Community Hospital', type: 'Charitable hospital', area: 'Gandhi Maidan, Patna', postalCode: '800001', distanceKm: 3.2, trustScore: 92, featured: true, marker: { label: 'A', x: 360, y: 210 } },
  { id: 'nirmal', name: 'Nirmal Care Hospital', type: 'Private hospital', area: 'Raja Bazar, Patna', postalCode: '800014', distanceKm: 2.1, trustScore: 86, marker: { label: 'B', x: 150, y: 390 } },
  { id: 'asha', name: 'Asha Multispeciality Centre', type: 'Private hospital', area: 'Kankarbagh, Patna', postalCode: '800020', distanceKm: 6.8, trustScore: 78, marker: { label: 'C', x: 520, y: 350 } },
  // The fourth card has no marker in the supplied design; don't invent a location.
  { id: 'sahyog', name: 'Sahyog District Care Centre', type: 'Community facility', area: 'Danapur, Bihar', postalCode: '801503', distanceKm: 11.4, trustScore: 54 },
];

export function sortFacilities(facilities, sortBy) {
  return [...facilities].sort((a, b) => {
    const distanceDifference = (a.distanceKm ?? Infinity) - (b.distanceKm ?? Infinity);
    if (sortBy === 'fit') {
      if (a.fitScore == null && b.fitScore == null) return 0;
      return (b.fitScore ?? -Infinity) - (a.fitScore ?? -Infinity) || distanceDifference || a.name.localeCompare(b.name);
    }
    if (sortBy === 'trust' && a.trustScore == null && b.trustScore == null) return 0;
    const difference = sortBy === 'distance' ? distanceDifference : (b.trustScore ?? -Infinity) - (a.trustScore ?? -Infinity);
    return (Number.isNaN(difference) ? 0 : difference) || a.name.localeCompare(b.name);
  });
}

export const distanceLabel = (facility) => facility.distanceKm == null ? 'Distance unavailable' : `${Number(facility.distanceKm.toFixed(1))} km`;

export function facilityScore(facility, kind) {
  if (kind === 'fit') {
    return { label: 'Fit Score', text: facility.fitScore == null ? 'Pending' : `${facility.fitScore.toFixed(2)}/100`, missing: facility.fitScore == null };
  }
  return { label: 'Trust score', text: facility.trustScore == null ? 'Unavailable' : `${facility.trustScore}/100`, missing: facility.trustScore == null };
}
