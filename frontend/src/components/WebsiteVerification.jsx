function WebsiteCheck({ link, result }) {
  const verified = result?.status === 'verified';
  const tone = verified ? 'verified' : result ? 'unverified' : 'pending';
  return <div className="website-check">
    <a className="website-link" href={link.url} target="_blank" rel="noopener noreferrer">{link.url} ↗</a>
    <div className="website-status" role="status">
      <span className={`verification-badge ${tone}`}>{verified ? 'Verified' : result ? 'Unable to verify' : 'Pending'}</span>
      {result?.reason && <p>{result.reason}</p>}
      {result?.evidenceUrl && result.evidenceUrl !== link.url && <a href={result.evidenceUrl} target="_blank" rel="noopener noreferrer">Open checked destination ↗</a>}
    </div>
  </div>;
}

export default function WebsiteVerification({ facility, ratioLabel }) {
  const links = facility.websiteLinks ?? [];
  const verifiedCount = links.filter(link => link.verification?.status === 'verified').length;
  const [primary, ...others] = links;

  return <section className="detail-section" aria-labelledby="website-heading">
    <div className="website-verification-heading">
      <h3 id="website-heading">Website verification</h3>
      {links.length > 0 && <output className="website-portion">
        {verifiedCount}/{links.length} verified{ratioLabel && ` · ${ratioLabel}`}
      </output>}
    </div>
    {primary ? <>
      <WebsiteCheck link={primary} result={primary.verification} />
      {others.length > 0 && <details className="other-websites">
        <summary>More dataset links ({others.length})</summary>
        {others.map(link => <WebsiteCheck key={link.index} link={link} result={link.verification} />)}
      </details>}
    </> : <div className="website-status">
      {facility.website && <a className="website-link" href={facility.website} target="_blank" rel="noopener noreferrer">{facility.website} ↗</a>}
      <span className="verification-badge unverified">Unable to verify</span>
      <p>{facility.website ? 'Verification is unavailable for this link.' : 'No usable website was listed in the dataset.'}</p>
    </div>}
  </section>;
}
