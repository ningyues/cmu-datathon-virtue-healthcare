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


export async function getPractoRating(facilityId, { signal } = {}) {
  const url = import.meta.env?.VITE_PRACTO_API_URL ?? '/api/practo/rating';
  const response = await fetch(url, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ facilityId }), signal,
  });
  const data = await response.json().catch(() => null);
  const statuses = ['available', 'not_found', 'no_rating', 'needs_review', 'unavailable'];
  if (!response.ok || !statuses.includes(data?.status)) throw new Error('Practo rating is unavailable.');
  let sourceUrl = null;
  if (typeof data.sourceUrl === 'string') {
    try {
      const source = new URL(data.sourceUrl);
      if (source.protocol === 'https:' && ['www.practo.com', 'practo.com'].includes(source.hostname)
        && !source.username && !source.password && !source.port
        && /^\/[^/]+\/(hospital|clinic)\/[^/]+(?:\/[^/]+)*\/?$/.test(source.pathname)) sourceUrl = source.href;
    } catch { /* Ignore invalid source URLs. */ }
  }
  const available = data.status === 'available' && sourceUrl && Number.isFinite(data.score)
    && data.score >= 0 && data.score <= 5 && data.scale === 5
    && (data.ratingCount == null || (Number.isInteger(data.ratingCount) && data.ratingCount > 0))
    && (data.patientStoryCount == null || (Number.isInteger(data.patientStoryCount) && data.patientStoryCount > 0));
  return { status: available ? 'available' : data.status === 'available' ? 'unavailable' : data.status,
    score: available ? data.score : null, ratingCount: available ? data.ratingCount ?? null : null,
    patientStoryCount: available ? data.patientStoryCount ?? null : null,
    sourceType: data.sourceType === 'live_page' ? 'live_page' : null,
    branchVerified: data.branchVerified === true,
    evidenceText: typeof data.evidenceText === 'string' ? data.evidenceText : null,
    scale: 5, sourceUrl, checkedAt: typeof data.checkedAt === 'string' ? data.checkedAt : null,
    reason: typeof data.reason === 'string' ? data.reason : '' };
}
