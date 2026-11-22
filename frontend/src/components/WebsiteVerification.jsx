function WebsiteCheck({ link, result }) {
  const match = result?.facilityMatch;
  const verified = result?.status === 'verified' && match?.status === 'verified';
  const tone = verified ? 'verified' : match || (result && result.status !== 'verified') ? 'unverified' : 'pending';
  const label = verified ? 'Verified · Hospital match' : tone === 'pending' ? 'Pending'
    : result?.status === 'verified' ? 'Hospital match unconfirmed' : 'Unable to verify';
  const source = match?.evidenceUrl ?? result?.evidenceUrl;
  return <div className="website-check">
    <a className="website-link" href={link.url} target="_blank" rel="noopener noreferrer">{link.url} ↗</a>
    <div className="website-status" role="status">
      <span className={`verification-badge ${tone}`}>{label}</span>
      {verified ? <p>{match.nameEvidence} · {match.addressEvidence}</p>
        : result?.status === 'verified' ? <p>{match?.reason ?? 'Link reachable. Hospital match pending.'}</p>
          : result?.reason && <p>{result.reason}</p>}
      {source && source !== link.url && <a href={source} target="_blank" rel="noopener noreferrer">Open checked destination ↗</a>}
    </div>
  </div>;
}

export default function WebsiteVerification({ facility }) {
  const links = facility.websiteLinks ?? [];
  const verifiedCount = links.filter(({ verification }) => verification?.status === 'verified'
    && verification.facilityMatch?.status === 'verified').length;
  const [primary, ...others] = links;

  return <section className="detail-section" aria-labelledby="website-heading">
    <div className="website-verification-heading">
      <h3 id="website-heading">Website verification</h3>
      {links.length > 0 && <output className="website-portion">
        {verifiedCount}/{links.length} hospital links verified
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
