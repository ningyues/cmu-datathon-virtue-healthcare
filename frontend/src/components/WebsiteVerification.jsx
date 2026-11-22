import { useCallback, useMemo } from 'react';
import useVerificationQueue from '../hooks/useVerificationQueue.js';
import { verifyWebsite } from '../services/verification.js';

function WebsiteCheck({ link, result }) {
  const verified = result?.status === 'verified';
  const tone = verified ? 'verified' : result ? 'unverified' : 'pending';
  return <div className="website-check">
    <a className="website-link" href={link.url} target="_blank" rel="noopener noreferrer">{link.url} ↗</a>
    <div className="website-status" role="status">
      <span className={`verification-badge ${tone}`}>{verified ? 'Verified' : result ? 'Unable to verify' : 'Checking…'}</span>
      {result?.reason && <p>{result.reason}</p>}
      {result?.evidenceUrl && result.evidenceUrl !== link.url && <a href={result.evidenceUrl} target="_blank" rel="noopener noreferrer">Open checked destination ↗</a>}
    </div>
  </div>;
}

export default function WebsiteVerification({ facility, onRatioChange }) {
  const links = facility.websiteLinks;
  const linkIndices = useMemo(() => links?.map(link => link.index), [links]);
  const check = useCallback(async (index, options) => {
    const result = await verifyWebsite(facility.id, index, options);
    if (!options.signal.aborted && result.urlDomainVerifiedRatio !== undefined) {
      onRatioChange(result.urlDomainVerifiedRatio);
    }
    return result;
  }, [facility.id, onRatioChange]);
  const results = useVerificationQueue(linkIndices, check);
  const [primary, ...others] = links ?? [];

  return <section className="detail-section" aria-labelledby="website-heading">
    <h3 id="website-heading">Website verification</h3>
    {primary ? <>
      <WebsiteCheck link={primary} result={results.get(primary.index)} />
      {others.length > 0 && <details className="other-websites">
        <summary>More dataset links ({others.length})</summary>
        {others.map(link => <WebsiteCheck key={link.index} link={link} result={results.get(link.index)} />)}
      </details>}
    </> : <div className="website-status">
      {facility.website && <a className="website-link" href={facility.website} target="_blank" rel="noopener noreferrer">{facility.website} ↗</a>}
      <span className="verification-badge unverified">Unable to verify</span>
      <p>{facility.website ? 'Verification is unavailable for this link.' : 'No usable website was listed in the dataset.'}</p>
    </div>}
  </section>;
}
