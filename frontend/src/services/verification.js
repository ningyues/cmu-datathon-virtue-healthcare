const endpoint = import.meta.env?.VITE_NABH_API_URL ?? '/api/nabh/verify';

export async function verifyCertification(facilityId, { signal } = {}) {
  const response = await fetch(endpoint, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ facilityId }), signal,
  });
  const data = await response.json().catch(() => null);
  if (!response.ok || !['verified', 'unverified', 'unavailable'].includes(data?.status)) {
    throw new Error('Verification could not be completed. Please try again later.');
  }
  const urls = Array.isArray(data.certificateUrls) ? data.certificateUrls.filter(value => {
    if (typeof value !== 'string') return false;
    try { const url = new URL(value); return url.protocol === 'https:' && !url.username && !url.password; }
    catch { return false; }
  }) : [];
  return { status: data.status === 'verified' && urls.length ? 'verified' : data.status === 'unavailable' ? 'unavailable' : 'unverified',
    certificateUrls: data.status === 'verified' ? urls : [],
    reason: typeof data.reason === 'string' ? data.reason : '' };
}
