const endpoint = import.meta.env?.VITE_NABH_API_URL ?? '/api/nabh/verify';
const websiteEndpoint = import.meta.env?.VITE_WEBSITE_VERIFICATION_API_URL ?? '/api/website/verify';

async function verificationRequest(url, payload, signal) {
  const response = await fetch(url, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload), signal,
  });
  const data = await response.json().catch(() => null);
  if (!response.ok || !['verified', 'unverified', 'unavailable'].includes(data?.status)) {
    throw new Error('Verification could not be completed. Please try again later.');
  }
  return data;
}

function safeEvidenceUrl(value, protocols) {
  if (typeof value !== 'string') return false;
  try {
    const url = new URL(value);
    return protocols.includes(url.protocol) && !url.username && !url.password;
  } catch { return false; }
}

export async function verifyCertification(facilityId, { signal } = {}) {
  const data = await verificationRequest(endpoint, { facilityId }, signal);
  const urls = Array.isArray(data.certificateUrls) ? data.certificateUrls.filter(value => safeEvidenceUrl(value, ['https:'])) : [];
  return { status: data.status === 'verified' && urls.length ? 'verified' : data.status === 'unavailable' ? 'unavailable' : 'unverified',
    certificateUrls: data.status === 'verified' ? urls : [],
    reason: typeof data.reason === 'string' ? data.reason : '' };
}

export async function verifyWebsite(facilityId, websiteIndex, { signal } = {}) {
  const data = await verificationRequest(websiteEndpoint, { facilityId, websiteIndex }, signal);
  const evidenceUrl = data.status === 'verified' && safeEvidenceUrl(data.evidenceUrl, ['https:', 'http:'])
    ? data.evidenceUrl : null;
  const ratio = data.urlDomainVerifiedRatio;
  return {
    status: evidenceUrl ? 'verified' : data.status === 'unavailable' ? 'unavailable' : 'unverified',
    evidenceUrl,
    reason: typeof data.reason === 'string' ? data.reason : '',
    urlDomainVerifiedRatio: ratio === null || (Number.isFinite(ratio) && ratio >= 0 && ratio <= 1) ? ratio : undefined,
  };
}
